use portable_pty::{native_pty_system, CommandBuilder, PtySize};
use serde::Serialize;
use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::Arc;
use std::thread;
use tauri::{AppHandle, Emitter, State};
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

// --- 内部ロジック（テスト可能、ジェネリックなRuntimeに対応） ---

pub async fn start_pty_internal<R: tauri::Runtime>(
    command: String,
    args: Vec<String>,
    cwd: Option<String>,
    app: tauri::AppHandle<R>,
    state: &PtyState,
) -> Result<(), String> {
    // 既存のセッションがあれば停止する
    let _ = stop_pty_internal(state).await;

    let pty_system = native_pty_system();
    
    // 標準的なターミナルサイズを設定
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
        }
    }

    let child = pair.slave.spawn_command(cmd).map_err(|e| e.to_string())?;
    
    let reader = pair.master.try_clone_reader().map_err(|e| e.to_string())?;
    let writer = pair.master.take_writer().map_err(|e| e.to_string())?;

    // Stateに保持
    *state.session.lock().await = Some(pair.master);
    *state.writer.lock().await = Some(writer);
    *state.child.lock().await = Some(child);

    // 非同期で出力を読み取り、Tauri Eventでフロントへストリーミング
    let app_clone = app.clone();
    thread::spawn(move || {
        let mut reader = reader;
        let mut buffer = [0u8; 1024];
        loop {
            match reader.read(&mut buffer) {
                Ok(0) => {
                    // EOF: プロセス終了
                    let _ = app_clone.emit("pty-status", "terminated");
                    break;
                }
                Ok(n) => {
                    let data = String::from_utf8_lossy(&buffer[..n]).into_owned();
                    let _ = app_clone.emit("pty-output", PtyOutputPayload { data });
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
    // childをkill
    let mut child_guard = state.child.lock().await;
    if let Some(mut child) = child_guard.take() {
        let _ = child.kill();
    }
    
    // writerをクリア
    let mut writer_guard = state.writer.lock().await;
    *writer_guard = None;

    // sessionをクリア
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

// --- Tauriコマンド（薄いラッパー） ---

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

// --- テストコード ---

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

        // 内部関数をモックのhandleで直接呼び出す
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
