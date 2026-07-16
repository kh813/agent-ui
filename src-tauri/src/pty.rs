use portable_pty::{native_pty_system, CommandBuilder, PtySize};
use regex::Regex;
use serde::Serialize;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
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

fn is_development_mode(path: &Path) -> bool {
    path.components().any(|c| c.as_os_str() == "target")
}

fn find_dev_project_root(mut path: PathBuf) -> Option<PathBuf> {
    while let Some(parent) = path.parent() {
        if parent.join("src-tauri").exists() {
            return Some(parent.to_path_buf());
        }
        path = parent.to_path_buf();
    }
    None
}

// Peels the OS-specific bundle/exe structure down to the immediate
// container directory, then reports whether that container is an `app/`
// wrapper folder (the old layout: a parent project's installer, e.g.
// agent-deck's install_agent_ui.py, placed agent-ui.app/agent-ui.exe
// directly inside app/, one level below the real project root) or the
// project root itself (the newer layout: the bundle/exe sits directly at
// the project root, with supporting binaries/scripts/venv as an `app/`
// sibling rather than a container). Both resolve_project_root and
// resolve_app_bundle_dir need this same peel, differing only in what they
// return once they know which layout they're looking at — see 2026-07-16's
// fix for agent-deck's root-declutter request (exe/.app moved out of app/
// to the project root; app/ kept as the sibling holding bin/, venv, etc.).
fn peel_to_container(mut path: PathBuf) -> (PathBuf, bool) {
    #[cfg(target_os = "macos")]
    {
        // Traverse up 4 times to get from the raw Mach-O binary out to the
        // folder containing the .app bundle itself:
        // 1. Contents/MacOS/agent-ui -> Contents/MacOS
        // 2. Contents/MacOS -> Contents
        // 3. Contents -> agent-ui.app
        // 4. agent-ui.app -> container (either an app/ wrapper, or the
        //    project root itself if the bundle sits directly there)
        for _ in 0..4 {
            if let Some(parent) = path.parent() {
                path = parent.to_path_buf();
            }
        }
    }

    #[cfg(not(target_os = "macos"))]
    {
        // exe's immediate parent is either an app/ wrapper, or the project
        // root itself if the exe sits directly there.
        if let Some(parent) = path.parent() {
            path = parent.to_path_buf();
        }
    }

    let is_app_wrapper = path
        .file_name()
        .map(|name| name == "app")
        .unwrap_or(false);
    (path, is_app_wrapper)
}

pub(crate) fn resolve_project_root(path: PathBuf) -> PathBuf {
    if is_development_mode(&path) {
        if let Some(dev_root) = find_dev_project_root(path.clone()) {
            return dev_root;
        }
    }

    let (container, is_app_wrapper) = peel_to_container(path);
    if is_app_wrapper {
        // Old layout: container IS app/, so the project root is one more
        // level up.
        container
            .parent()
            .map(|p| p.to_path_buf())
            .unwrap_or(container)
    } else {
        // New layout: the bundle/exe sits directly at the project root, so
        // the container we already peeled down to IS the project root.
        container
    }
}

// Resolve the directory holding supporting binaries/scripts (bin/, the
// bundled Python runtime, venv, etc.) — NOT the project root one level
// further up that resolve_project_root returns in the old layout, nor the
// same directory as the exe/bundle itself in the new layout. This is where
// a sibling `./bin/<agent>` portable install lives (agent.rs's
// detect_agent_internal step 0), which for a macOS .app bundle is NOT simply
// the raw binary's own parent directory (Contents/MacOS/) — that naive
// computation was the bug this function originally fixed.
pub(crate) fn resolve_app_bundle_dir(path: PathBuf) -> PathBuf {
    if is_development_mode(&path) {
        if let Some(dev_root) = find_dev_project_root(path.clone()) {
            return dev_root;
        }
    }

    let (container, is_app_wrapper) = peel_to_container(path);
    if is_app_wrapper {
        // Old layout: container already IS the app/ wrapper we want.
        container
    } else {
        // New layout: the bundle/exe sits at the project root, so the
        // supporting-files directory is the app/ sibling next to it.
        container.join("app")
    }
}

pub(crate) fn get_default_cwd() -> PathBuf {
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

    // Add local bin directories to PATH so that command-line tools like marp or agy
    // are directly accessible inside the PTY shell.
    let mut path_env = std::env::var("PATH").unwrap_or_default();
    let path_sep = if cfg!(target_os = "windows") { ";" } else { ":" };

    #[cfg(target_os = "macos")]
    {
        for path in &["/opt/homebrew/bin", "/usr/local/bin"] {
            if !path_env.contains(path) {
                path_env = format!("{}{}{}", path, path_sep, path_env);
            }
        }
    }

    if let Ok(exe_path) = std::env::current_exe() {
        let exe_dir = resolve_app_bundle_dir(exe_path.clone());
        let proj_dir = resolve_project_root(exe_path);
        
        let mut local_paths = Vec::new();
        local_paths.push(exe_dir.join("bin"));
        local_paths.push(exe_dir.join("app").join("bin"));
        local_paths.push(proj_dir.join("bin"));
        local_paths.push(proj_dir.join("app").join("bin"));

        for local_path in local_paths {
            let path_str = local_path.to_string_lossy().to_string();
            if !path_env.contains(&path_str) {
                path_env = format!("{}{}{}", path_str, path_sep, path_env);
            }
        }
    }
    cmd.env("PATH", path_env);

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

#[tauri::command]
pub fn get_app_bundle_dir() -> Result<String, String> {
    if let Ok(exe_path) = std::env::current_exe() {
        Ok(resolve_app_bundle_dir(exe_path).to_string_lossy().to_string())
    } else {
        Err("Failed to get current executable path".to_string())
    }
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
        // Old layout: a parent project's installer (e.g. agent-deck's
        // install_agent_ui.py) placed the bundle/exe inside an app/ wrapper.
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

    #[test]
    fn test_resolve_project_root_direct_at_root() {
        // New layout (2026-07-16): the bundle/exe sits directly at the
        // project root, with supporting binaries/scripts/venv under an app/
        // sibling instead of app/ being the bundle's own container.
        #[cfg(target_os = "macos")]
        {
            let mock_exe = PathBuf::from("/Users/test/agent-deck/agent-deck.app/Contents/MacOS/agent-ui");
            let resolved = resolve_project_root(mock_exe);
            assert_eq!(resolved, PathBuf::from("/Users/test/agent-deck"));
        }

        #[cfg(not(target_os = "macos"))]
        {
            let mock_exe = if cfg!(target_os = "windows") {
                PathBuf::from("C:\\Users\\test\\agent-deck\\agent-deck.exe")
            } else {
                PathBuf::from("/home/test/agent-deck/agent-deck.exe")
            };
            let resolved = resolve_project_root(mock_exe);

            let expected = if cfg!(target_os = "windows") {
                PathBuf::from("C:\\Users\\test\\agent-deck")
            } else {
                PathBuf::from("/home/test/agent-deck")
            };
            assert_eq!(resolved, expected);
        }
    }

    #[test]
    fn test_resolve_app_bundle_dir_hierarchy() {
        // Old layout: app/ is the bundle's own container.
        #[cfg(target_os = "macos")]
        {
            let mock_exe = PathBuf::from("/Users/test/agent-deck/app/agent-ui.app/Contents/MacOS/agent-ui");
            let resolved = resolve_app_bundle_dir(mock_exe);
            // One level shallower than resolve_project_root: the wrapper
            // folder containing the .app bundle, not the project root above it.
            assert_eq!(resolved, PathBuf::from("/Users/test/agent-deck/app"));
        }

        #[cfg(not(target_os = "macos"))]
        {
            let mock_exe = if cfg!(target_os = "windows") {
                PathBuf::from("C:\\Users\\test\\agent-deck\\app\\agent-ui.exe")
            } else {
                PathBuf::from("/home/test/agent-deck/app/agent-ui.exe")
            };
            let resolved = resolve_app_bundle_dir(mock_exe);

            let expected = if cfg!(target_os = "windows") {
                PathBuf::from("C:\\Users\\test\\agent-deck\\app")
            } else {
                PathBuf::from("/home/test/agent-deck/app")
            };
            assert_eq!(resolved, expected);
        }
    }

    #[test]
    fn test_resolve_app_bundle_dir_direct_at_root() {
        // New layout (2026-07-16): app/ is a SIBLING of the bundle/exe, not
        // its container — resolve_app_bundle_dir must still point at app/,
        // now by appending it rather than stopping one level short.
        #[cfg(target_os = "macos")]
        {
            let mock_exe = PathBuf::from("/Users/test/agent-deck/agent-deck.app/Contents/MacOS/agent-ui");
            let resolved = resolve_app_bundle_dir(mock_exe);
            assert_eq!(resolved, PathBuf::from("/Users/test/agent-deck/app"));
        }

        #[cfg(not(target_os = "macos"))]
        {
            let mock_exe = if cfg!(target_os = "windows") {
                PathBuf::from("C:\\Users\\test\\agent-deck\\agent-deck.exe")
            } else {
                PathBuf::from("/home/test/agent-deck/agent-deck.exe")
            };
            let resolved = resolve_app_bundle_dir(mock_exe);

            let expected = if cfg!(target_os = "windows") {
                PathBuf::from("C:\\Users\\test\\agent-deck\\app")
            } else {
                PathBuf::from("/home/test/agent-deck/app")
            };
            assert_eq!(resolved, expected);
        }
    }

    #[tokio::test]
    async fn test_pty_env_propagation() {
        use tauri::test::mock_app;
        use tauri::Listener;

        let app = mock_app();
        let handle = app.handle().clone();
        let state = PtyState::default();

        // Print target environment variables to verify they propagate properly
        #[cfg(not(target_os = "windows"))]
        let cmd = "sh".to_string();
        #[cfg(not(target_os = "windows"))]
        let args = vec![
            "-c".to_string(),
            "echo TERM=$TERM; echo COLORTERM=$COLORTERM; echo PYTHONIOENCODING=$PYTHONIOENCODING; echo PATH=$PATH".to_string(),
        ];

        #[cfg(target_os = "windows")]
        let cmd = "powershell.exe".to_string();
        #[cfg(target_os = "windows")]
        let args = vec![
            "-Command".to_string(),
            "Write-Output \"TERM=$env:TERM\"; Write-Output \"COLORTERM=$env:COLORTERM\"; Write-Output \"PYTHONIOENCODING=$env:PYTHONIOENCODING\"; Write-Output \"PATH=$env:PATH\"".to_string(),
        ];

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
        let timeout = tokio::time::sleep(tokio::time::Duration::from_secs(5));
        tokio::pin!(timeout);

        loop {
            tokio::select! {
                Some(data) = rx.recv() => {
                    received.push_str(&data);
                    if received.contains("TERM=xterm-256color") 
                        && received.contains("COLORTERM=truecolor") 
                        && received.contains("PYTHONIOENCODING=utf-8")
                        && received.contains("PATH=") {
                        break;
                    }
                }
                _ = &mut timeout => {
                    panic!("Timeout waiting for PTY env. Received: '{}'", received);
                }
            }
        }

        assert!(received.contains("TERM=xterm-256color"));
        assert!(received.contains("COLORTERM=truecolor"));
        assert!(received.contains("PYTHONIOENCODING=utf-8"));
        assert!(received.contains("PATH="));
        
        let stop_res = stop_pty_internal(&state).await;
        assert!(stop_res.is_ok());
    }
}
