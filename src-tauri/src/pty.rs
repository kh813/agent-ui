use portable_pty::{native_pty_system, CommandBuilder, PtySize};
use regex::Regex;
use serde::Serialize;
use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::Arc;
use std::thread;
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

#[derive(Serialize, Clone)]
struct PtyOutputPayload {
    data: String,
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

    // 2. Y/N Confirmation
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

    // 3. Path Input prompt
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

pub async fn start_pty_internal<R: tauri::Runtime>(
    command: String,
    args: Vec<String>,
    cwd: Option<String>,
    app: tauri::AppHandle<R>,
    state: &PtyState,
) -> Result<(), String> {
    let _ = stop_pty_internal(state).await;

    let pty_system = native_pty_system();
    
    let pair = pty_system
        .openpty(PtySize {
            rows: 24,
            cols: 80,
            pixel_width: 0,
            pixel_height: 0,
        })
        .map_err(|e| e.to_string())?;

    let mut cmd = CommandBuilder::new(&command);
    cmd.args(args);
    
    if let Some(cwd_path) = cwd {
        if !cwd_path.is_empty() {
            cmd.cwd(PathBuf::from(cwd_path));
        } else {
            if let Ok(exe_path) = std::env::current_exe() {
                if let Some(exe_dir) = exe_path.parent() {
                    cmd.cwd(exe_dir.to_path_buf());
                }
            }
        }
    } else {
        if let Ok(exe_path) = std::env::current_exe() {
            if let Some(exe_dir) = exe_path.parent() {
                cmd.cwd(exe_dir.to_path_buf());
            }
        }
    }

    let child = pair.slave.spawn_command(cmd).map_err(|e| e.to_string())?;
    
    let reader = pair.master.try_clone_reader().map_err(|e| e.to_string())?;
    let writer = pair.master.take_writer().map_err(|e| e.to_string())?;

    *state.session.lock().await = Some(pair.master);
    *state.writer.lock().await = Some(writer);
    *state.child.lock().await = Some(child);

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
                    let raw_data = String::from_utf8_lossy(&buffer[..n]).into_owned();
                    let _ = app_clone.emit("pty-output", PtyOutputPayload { data: raw_data.clone() });
                    
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

// --- Tauri Command Wrapper ---

#[tauri::command]
pub async fn start_pty(
    command: String,
    args: Vec<String>,
    cwd: Option<String>,
    app: AppHandle,
    state: State<'_, PtyState>,
) -> Result<(), String> {
    start_pty_internal(command, args, cwd, app, &state).await
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
                if let Some(data) = payload.get("data").and_then(|v| v.as_str()) {
                    let _ = tx_clone.try_send(data.to_string());
                }
            }
        });

        let start_res = start_pty_internal(cmd, args, None, handle.clone(), &state).await;
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
}
