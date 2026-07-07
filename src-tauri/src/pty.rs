use portable_pty::{native_pty_system, CommandBuilder, PtySize};
use regex::Regex;
use serde::Serialize;
use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::Arc;
use std::thread;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Emitter, State};
use tauri_plugin_opener::OpenerExt;
use tokio::sync::Mutex;

pub struct PtyState {
    pub session: Arc<Mutex<Option<Box<dyn portable_pty::MasterPty + Send>>>>,
    pub writer: Arc<Mutex<Option<Box<dyn Write + Send>>>>,
    pub child: Arc<Mutex<Option<Box<dyn portable_pty::Child + Send + Sync>>>>,
}

impl Default for PtyState {
    fn default() -> Self {
        Self {
            session: Arc::new(Mutex::new(None)),
            writer: Arc::new(Mutex::new(None)),
            child: Arc::new(Mutex::new(None)),
        }
    }
}

// TEMPORARY: shared path for the raw PTY byte log used to diagnose rendering
// bugs in the upstream CLI's own output. See start_pty_internal (truncates
// it fresh per session) and resize_pty_internal (appends a marker so a
// mid-session resize can be correlated against the byte stream around it -
// suspected of desyncing the upstream CLI's own relative-cursor redraw math
// from what's actually on screen).
fn debug_log_path() -> PathBuf {
    std::env::var("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."))
        .join("agent-ui-pty-debug.log")
}

fn debug_log_marker(text: &str) {
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    if let Ok(mut f) = std::fs::OpenOptions::new().append(true).open(debug_log_path()) {
        use std::io::Write as _;
        let _ = writeln!(f, "\n[agent-ui @ {millis}ms] {text}");
    }
}

#[derive(Serialize, Clone)]
struct PtyOutputPayload {
    // Raw bytes, not a decoded String: a fixed-size PTY read can end in the
    // middle of a multi-byte UTF-8 character, and independently
    // lossy-decoding each chunk would replace both halves of that character
    // with U+FFFD. Sending raw bytes and letting xterm.js's own UTF-8
    // decoder (which correctly buffers a partial trailing sequence across
    // separate `write()` calls) handle it avoids that corruption entirely.
    data: Vec<u8>,
}

#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct PtyPromptPayload {
    pub prompt_type: String, // "confirm" | "path" | "login"
    pub message: String,
    pub options: Option<Vec<String>>,
    pub url: Option<String>,
}

// Strip ANSI helper on backend to parse clean prompt patterns
pub fn strip_ansi_rust(text: &str) -> String {
    let re = Regex::new(r"[\x1b\x9b]\[[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]").unwrap();
    re.replace_all(text, "").to_string()
}

// Detect prompts (y/n, folder path, login oauth url) from text
pub fn detect_prompts(text: &str) -> Option<PtyPromptPayload> {
    // 1. Login/Authentication URL (Google OAuth or device login url)
    let login_re = Regex::new(r"https://[a-zA-Z0-9./?=&_-]*(oauth|auth|device)[a-zA-Z0-9./?=&_-]*").unwrap();
    if let Some(mat) = login_re.find(text) {
        return Some(PtyPromptPayload {
            prompt_type: "login".to_string(),
            message: "Authentication login requested. The URL has been opened in your browser.".to_string(),
            options: None,
            url: Some(mat.as_str().to_string()),
        });
    }

    // 2. Folder Trust Check (Do you trust the contents of this project?)
    if text.contains("Do you trust the contents of this project?") || text.contains("Yes, I trust this folder") {
        return Some(PtyPromptPayload {
            prompt_type: "confirm".to_string(),
            message: "Do you trust the contents of this project? Antigravity CLI requires permission to read, edit, and execute files here.".to_string(),
            options: Some(vec!["Yes, I trust this folder".to_string(), "No, exit".to_string()]),
            url: None,
        });
    }

    // 3. Tool/Command Permission Request Prompt
    if text.contains("Requesting permission for:") || (text.contains("Do you want to proceed?") && !text.contains("[y/N]")) {
        let mut cmd_name = "command".to_string();
        if let Some(caps) = Regex::new(r"permission for:\s*\r?\n?\s*([^\r\n]+)").unwrap().captures(text) {
            cmd_name = caps.get(1).map_or("command".to_string(), |m| m.as_str().trim().to_string());
        }
        return Some(PtyPromptPayload {
            prompt_type: "confirm".to_string(),
            message: format!("Command permission requested for: `{}`. Do you want to proceed?", cmd_name),
            options: Some(vec![
                "Yes".to_string(),
                "Yes, and always allow in this conversation".to_string(),
                "Yes, and always allow (Persist to settings.json)".to_string(),
                "No".to_string(),
            ]),
            url: None,
        });
    }

    // 4. Y/N Confirmation
    // Proceed [y/N], Confirm [yes/no], procedd (y/n), Are you sure? [y/N]
    let confirm_re = Regex::new(r"(?i)(confirm|proceed|are you sure|y/n|yes/no)[\s\S]*?\[([yY]/[nN]|[yY]es/[nN]o)\]").unwrap();
    if confirm_re.is_match(text) {
        return Some(PtyPromptPayload {
            prompt_type: "confirm".to_string(),
            message: "Interactive confirmation requested.".to_string(),
            options: Some(vec!["Yes".to_string(), "No".to_string()]),
            url: None,
        });
    }

    // 4. Path Input prompt
    let path_re = Regex::new(r"(?i)(enter|select|input)\s+[\s\S]*?(path|folder|directory|destination)").unwrap();
    if path_re.is_match(text) {
        return Some(PtyPromptPayload {
            prompt_type: "path".to_string(),
            message: "Folder path input requested.".to_string(),
            options: None,
            url: None,
        });
    }

    None
}

// --- Internal Logic (Generic Runtime support for testing) ---

fn resolve_project_root(mut path: PathBuf) -> PathBuf {
    // On macOS, traverse up to get outside of the .app bundle and wrapper folder
    #[cfg(target_os = "macos")]
    {
        // Traverse up 5 times:
        // 1. Contents/MacOS/agent-ui -> Contents/MacOS
        // 2. Contents/MacOS -> Contents
        // 3. Contents -> agent-ui.app
        // 4. agent-ui.app -> app/ (wrapper folder)
        // 5. app/ -> actual project root
        for _ in 0..5 {
            if let Some(parent) = path.parent() {
                path = parent.to_path_buf();
            }
        }
        return path;
    }

    // On Windows/Linux, traverse up to get outside of the app/ wrapper folder
    #[cfg(not(target_os = "macos"))]
    {
        // exe is placed in <project_root>/app/agent-ui.exe -> traverse up twice
        if let Some(parent) = path.parent().and_then(|p| p.parent()) {
            return parent.to_path_buf();
        }
        if let Some(parent) = path.parent() {
            return parent.to_path_buf();
        }
        path
    }
}

fn get_default_cwd() -> PathBuf {
    if let Ok(exe_path) = std::env::current_exe() {
        return resolve_project_root(exe_path);
    }
    
    // Fallback to home directory without external dirs dependency
    #[cfg(target_os = "windows")]
    {
        if let Ok(home) = std::env::var("USERPROFILE") {
            return PathBuf::from(home);
        }
    }
    if let Ok(home) = std::env::var("HOME") {
        return PathBuf::from(home);
    }
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("/"))
}

pub async fn start_pty_internal<R: tauri::Runtime>(
    command: String,
    args: Vec<String>,
    cwd: Option<String>,
    rows: Option<u16>,
    cols: Option<u16>,
    app: tauri::AppHandle<R>,
    state: &PtyState,
) -> Result<(), String> {
    let _ = stop_pty_internal(state).await;

    // Default to a reasonable size if the frontend didn't report the
    // xterm.js viewport's actual fitted size yet. Whenever this doesn't
    // match what's really being rendered, interactive CLIs that redraw via
    // relative cursor movement (e.g. "up N rows, clear, redraw") can target
    // the wrong row and leave stale content behind instead of overwriting it.
    let rows = rows.unwrap_or(40);
    let cols = cols.unwrap_or(300);

    let pty_system = native_pty_system();

    let pair = pty_system
        .openpty(PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|e| e.to_string())?;

    let mut cmd = CommandBuilder::new(&command);
    cmd.args(args);
    cmd.env("LANG", "en_US.UTF-8");
    cmd.env("LC_ALL", "en_US.UTF-8");
    cmd.env("COLUMNS", cols.to_string());
    cmd.env("LINES", rows.to_string());
    // Ensure the terminal is recognized as a modern UTF-8 capable terminal
    // with 256color/truecolor support. This prevents CLI tools (like agy) from
    // falling back to dumb terminal mode and outputting Unicode characters
    // (like progress spinners) as raw escape sequences like \xxxx.
    cmd.env("TERM", "xterm-256color");
    cmd.env("COLORTERM", "truecolor");
    cmd.env("PYTHONIOENCODING", "utf-8");
    cmd.env("PYTHONUTF8", "1");

    if let Some(cwd_path) = cwd {
        if !cwd_path.is_empty() {
            cmd.cwd(PathBuf::from(cwd_path));
        } else {
            cmd.cwd(get_default_cwd());
        }
    } else {
        cmd.cwd(get_default_cwd());
    }

    let child = pair.slave.spawn_command(cmd).map_err(|e| e.to_string())?;

    let reader = pair.master.try_clone_reader().map_err(|e| e.to_string())?;
    let writer = pair.master.take_writer().map_err(|e| e.to_string())?;

    *state.session.lock().await = Some(pair.master);
    *state.writer.lock().await = Some(writer);
    *state.child.lock().await = Some(child);

    // TEMPORARY: raw PTY byte log for diagnosing rendering bugs in the
    // upstream CLI's own output. Truncated fresh on every session start.
    let debug_log_path = debug_log_path();
    let _ = std::fs::write(&debug_log_path, b"");
    debug_log_marker(&format!("start_pty rows={rows} cols={cols}"));

    let app_clone = app.clone();
    thread::spawn(move || {
        let mut reader = reader;
        let mut buffer = [0u8; 1024];
        loop {
            match reader.read(&mut buffer) {
                Ok(0) => {
                    let _ = app_clone.emit("pty-status", "terminated");
                    break;
                }
                Ok(n) => {
                    if let Ok(mut f) = std::fs::OpenOptions::new().append(true).open(&debug_log_path) {
                        use std::io::Write as _;
                        let _ = f.write_all(&buffer[..n]);
                    }

                    let _ = app_clone.emit("pty-output", PtyOutputPayload { data: buffer[..n].to_vec() });

                    // Lossy-decoding here is fine even if it mangles a
                    // boundary-spanning character: this text is only used
                    // for prompt-pattern matching, not display, so an
                    // occasional stray replacement character has no visible
                    // effect on what the user sees in the terminal.
                    let raw_data = String::from_utf8_lossy(&buffer[..n]).into_owned();

                    // Clean text and check prompt pattern
                    let clean_text = strip_ansi_rust(&raw_data);
                    if let Some(prompt) = detect_prompts(&clean_text) {
                        // If it's a login link, open default OS browser
                        if prompt.prompt_type == "login" {
                            if let Some(ref url) = prompt.url {
                                let _ = app_clone.opener().open_path(url, None::<String>);
                            }
                        }
                        
                        let _ = app_clone.emit("pty-prompt", prompt);
                    }
                }
                Err(_) => {
                    let _ = app_clone.emit("pty-status", "error");
                    break;
                }
            }
        }
    });

    Ok(())
}

pub async fn stop_pty_internal(state: &PtyState) -> Result<(), String> {
    let mut child_guard = state.child.lock().await;
    if let Some(mut child) = child_guard.take() {
        let _ = child.kill();
    }
    
    let mut writer_guard = state.writer.lock().await;
    *writer_guard = None;

    let mut session_guard = state.session.lock().await;
    *session_guard = None;

    Ok(())
}

pub async fn write_to_pty_internal(input: String, state: &PtyState) -> Result<(), String> {
    let mut writer_guard = state.writer.lock().await;
    if let Some(ref mut writer) = *writer_guard {
        writer
            .write_all(input.as_bytes())
            .map_err(|e| e.to_string())?;
        writer.flush().map_err(|e| e.to_string())?;
        Ok(())
    } else {
        Err("PTY session not started or writer not available".to_string())
    }
}

pub async fn resize_pty_internal(rows: u16, cols: u16, state: &PtyState) -> Result<(), String> {
    let session_guard = state.session.lock().await;
    if let Some(ref master) = *session_guard {
        debug_log_marker(&format!("resize_pty rows={rows} cols={cols}"));
        master
            .resize(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .map_err(|e| e.to_string())?;
    }
    Ok(())
}

// --- Tauri Command Wrapper ---

#[tauri::command]
pub async fn start_pty(
    command: String,
    args: Vec<String>,
    cwd: Option<String>,
    rows: Option<u16>,
    cols: Option<u16>,
    app: AppHandle,
    state: State<'_, PtyState>,
) -> Result<(), String> {
    start_pty_internal(command, args, cwd, rows, cols, app, &state).await
}

#[tauri::command]
pub async fn resize_pty(
    rows: u16,
    cols: u16,
    state: State<'_, PtyState>,
) -> Result<(), String> {
    resize_pty_internal(rows, cols, &state).await
}

#[tauri::command]
pub async fn write_to_pty(
    input: String,
    state: State<'_, PtyState>,
) -> Result<(), String> {
    write_to_pty_internal(input, &state).await
}

#[tauri::command]
pub async fn stop_pty(state: State<'_, PtyState>) -> Result<(), String> {
    stop_pty_internal(&state).await
}

// --- Test Code ---

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pty_spawn_and_cwd() {
        let pty_system = native_pty_system();
        let pair = pty_system
            .openpty(PtySize {
                rows: 24,
                cols: 80,
                pixel_width: 0,
                pixel_height: 0,
            })
            .unwrap();

        let target_cwd = std::env::temp_dir();
        
        #[cfg(target_os = "windows")]
        let mut cmd = CommandBuilder::new("cmd.exe");
        #[cfg(target_os = "windows")]
        cmd.args(&["/c", "cd"]);

        #[cfg(not(target_os = "windows"))]
        let mut cmd = CommandBuilder::new("pwd");

        cmd.cwd(target_cwd.clone());

        let mut child = pair.slave.spawn_command(cmd).unwrap();
        let mut reader = pair.master.try_clone_reader().unwrap();

        let mut buffer = [0u8; 1024];
        let n = reader.read(&mut buffer).unwrap();
        let output = String::from_utf8_lossy(&buffer[..n]);
        let _ = child.wait().unwrap();

        println!("PTY Output: {}", output);
        println!("Target CWD: {}", target_cwd.to_string_lossy());
        
        assert!(n > 0);
    }

    #[test]
    fn test_strip_ansi_rust() {
        let text_with_colors = "\x1b[31mRed Text\x1b[0m and \x1b[1;34mBold Blue\x1b[0m";
        let clean = strip_ansi_rust(text_with_colors);
        assert_eq!(clean, "Red Text and Bold Blue");
    }

    #[test]
    fn test_detect_login_url() {
        let raw_output = "To sign in, please open the following URL in your browser:\nhttps://accounts.google.com/o/oauth2/device/auth?user_code=ABCD-EFGH\nWaiting for authentication...";
        let prompt = detect_prompts(raw_output);
        assert!(prompt.is_some());
        let p = prompt.unwrap();
        assert_eq!(p.prompt_type, "login");
        assert_eq!(p.url.unwrap(), "https://accounts.google.com/o/oauth2/device/auth?user_code=ABCD-EFGH");
    }

    #[test]
    fn test_detect_confirm_prompt() {
        let raw_confirm = "Do you want to proceed? [y/N]: ";
        let prompt = detect_prompts(raw_confirm);
        assert!(prompt.is_some());
        let p = prompt.unwrap();
        assert_eq!(p.prompt_type, "confirm");
        assert_eq!(p.options.unwrap(), vec!["Yes".to_string(), "No".to_string()]);
    }

    #[test]
    fn test_detect_path_prompt() {
        let raw_path = "Enter installation directory path: ";
        let prompt = detect_prompts(raw_path);
        assert!(prompt.is_some());
        let p = prompt.unwrap();
        assert_eq!(p.prompt_type, "path");
    }

    #[tokio::test]
    async fn test_start_pty_and_emission() {
        use tauri::test::mock_app;
        use tauri::Listener;

        let app = mock_app();
        let handle = app.handle().clone();
        
        let state = PtyState::default();

        #[cfg(target_os = "windows")]
        let cmd = "cmd.exe".to_string();
        #[cfg(target_os = "windows")]
        let args = vec!["/c".to_string(), "echo integration-test".to_string()];

        #[cfg(not(target_os = "windows"))]
        let cmd = "echo".to_string();
        #[cfg(not(target_os = "windows"))]
        let args = vec!["integration-test".to_string()];

        let (tx, mut rx) = tokio::sync::mpsc::channel(10);
        let tx_clone = tx.clone();
        
        handle.listen("pty-output", move |event| {
            if let Ok(payload) = serde_json::from_str::<serde_json::Value>(event.payload()) {
                if let Some(bytes) = payload.get("data").and_then(|v| v.as_array()) {
                    let data: Vec<u8> = bytes
                        .iter()
                        .filter_map(|b| b.as_u64())
                        .map(|b| b as u8)
                        .collect();
                    let text = String::from_utf8_lossy(&data).into_owned();
                    let _ = tx_clone.try_send(text);
                }
            }
        });

        let start_res = start_pty_internal(cmd, args, None, None, None, handle.clone(), &state).await;
        assert!(start_res.is_ok());

        let mut received = String::new();
        let timeout = tokio::time::sleep(tokio::time::Duration::from_secs(3));
        tokio::pin!(timeout);

        loop {
            tokio::select! {
                Some(data) = rx.recv() => {
                    received.push_str(&data);
                    if received.contains("integration-test") {
                        break;
                    }
                }
                _ = &mut timeout => {
                    panic!("Timeout waiting for PTY event. Received: '{}'", received);
                }
            }
        }

        assert!(received.contains("integration-test"));
        
        let stop_res = stop_pty_internal(&state).await;
        assert!(stop_res.is_ok());
    }

    #[test]
    fn test_get_default_cwd() {
        let cwd = get_default_cwd();
        assert!(!cwd.to_string_lossy().is_empty());
        assert!(cwd.exists());
        assert!(cwd.is_dir());
    }

    #[test]
    fn test_resolve_project_root_hierarchy() {
        #[cfg(target_os = "macos")]
        {
            let mock_exe = PathBuf::from("/Users/test/agent-deck/app/agent-ui.app/Contents/MacOS/agent-ui");
            let resolved = resolve_project_root(mock_exe);
            assert_eq!(resolved, PathBuf::from("/Users/test/agent-deck"));
        }

        #[cfg(not(target_os = "macos"))]
        {
            // Windows mock path (testing with backslashes on windows, forward slashes on linux)
            let mock_exe = if cfg!(target_os = "windows") {
                PathBuf::from("C:\\Users\\test\\agent-deck\\app\\agent-ui.exe")
            } else {
                PathBuf::from("/home/test/agent-deck/app/agent-ui.exe")
            };
            let resolved = resolve_project_root(mock_exe.clone());
            
            let expected = if cfg!(target_os = "windows") {
                PathBuf::from("C:\\Users\\test\\agent-deck")
            } else {
                PathBuf::from("/home/test/agent-deck")
            };
            assert_eq!(resolved, expected);
        }
    }
}
