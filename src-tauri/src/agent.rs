use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::io::Read;
use std::path::{PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use tauri::{AppHandle, Emitter, Manager};

use crate::pty::{get_default_cwd, resolve_app_bundle_dir, resolve_project_root};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;


#[derive(Deserialize, Serialize, Clone, Debug)]
pub struct DetectPaths {
    pub macos: Option<Vec<String>>,
    pub windows: Option<Vec<String>>,
}

#[derive(Deserialize, Serialize, Clone, Debug)]
pub struct InstallCommand {
    pub command: String,
    pub args: Vec<String>,
}

#[derive(Deserialize, Serialize, Clone, Debug)]
pub struct InstallConfig {
    pub macos: Option<InstallCommand>,
    pub windows: Option<InstallCommand>,
}

#[derive(Deserialize, Serialize, Clone, Debug)]
pub struct AgentConfig {
    pub name: String,
    pub binary: String,
    pub detect_paths: DetectPaths,
    pub version_args: Vec<String>,
    pub install: InstallConfig,
    pub update: InstallConfig,
}

#[derive(Serialize, Clone, Debug)]
pub struct AgentStatus {
    pub installed: bool,
    pub path: Option<String>,
    pub version: Option<String>,
}

#[derive(Serialize, Clone, Debug, PartialEq)]
pub struct UpdateStatus {
    pub current_version: Option<String>,
    pub latest_version: Option<String>,
    pub update_available: bool,
}

// Embedded copy of resources/install_commands.json, used whenever the file
// can't be found on disk (e.g. a standalone Windows .exe copied without its
// resources directory). This guarantees the app has sane defaults even when
// not installed via the bundled installer.
const DEFAULT_INSTALL_COMMANDS: &str = include_str!("../resources/install_commands.json");

// Load configurations from resource file, resolving via resource_dir in Tauri v2
fn load_config<R: tauri::Runtime>(app: &tauri::AppHandle<R>) -> Result<HashMap<String, AgentConfig>, String> {
    let resource_path = app
        .path()
        .resource_dir()
        .ok()
        .map(|p| p.join("resources/install_commands.json"));

    let path = resource_path
        .filter(|p| p.exists())
        .or_else(|| {
            // Fallback during cargo test execution
            let test_path = PathBuf::from("resources/install_commands.json");
            if test_path.exists() {
                Some(test_path)
            } else {
                None
            }
        })
        .or_else(|| {
            let dev_path = PathBuf::from("src-tauri/resources/install_commands.json");
            if dev_path.exists() {
                Some(dev_path)
            } else {
                None
            }
        });

    let content = match path {
        Some(path) => fs::read_to_string(&path)
            .map_err(|e| format!("Failed to read config from {:?}: {}", path, e))?,
        None => DEFAULT_INSTALL_COMMANDS.to_string(),
    };

    serde_json::from_str(&content)
        .map_err(|e| format!("Failed to parse JSON: {}", e))
}

// Resolve environment variables like $HOME or $USERPROFILE in paths
fn resolve_env_path(path_str: &str) -> PathBuf {
    let mut resolved = path_str.to_string();
    
    // Replace $HOME
    if let Ok(home) = std::env::var("HOME") {
        resolved = resolved.replace("$HOME", &home);
    }
    
    // Replace $USERPROFILE
    if let Ok(userprofile) = std::env::var("USERPROFILE") {
        resolved = resolved.replace("$USERPROFILE", &userprofile);
    }
    
    PathBuf::from(resolved)
}

// Reject anything that doesn't look like a short version string (e.g. an
// HTML page returned by a misbehaving/redirected endpoint instead of plain text).
fn looks_like_version(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 32
        && s.chars().all(|c| c.is_ascii_alphanumeric() || ".-_+".contains(c))
}

// Best-effort fetch of latest version from web via OS-specific CLI tools
fn fetch_latest_version_from_web() -> Option<String> {
    let is_windows = cfg!(target_os = "windows");
    let output = if is_windows {
        let mut cmd = Command::new("powershell");
        cmd.args(&["-Command", "try { (Invoke-WebRequest -UseBasicParsing https://antigravity.google.com/version.txt -TimeoutSec 3).Content.Trim() } catch { exit 1 }"]);
        #[cfg(target_os = "windows")]
        cmd.creation_flags(CREATE_NO_WINDOW);
        cmd.output()
    } else {
        Command::new("curl")
            .args(&["-fsSL", "--max-time", "3", "https://antigravity.google.com/version.txt"])
            .output()
    };

    if let Ok(out) = output {
        if out.status.success() {
            let ver = String::from_utf8_lossy(&out.stdout).trim().to_string();
            if looks_like_version(&ver) {
                return Some(ver);
            }
        }
    }
    None
}

// --- Internal Logic (Generic Runtime support for testing) ---

pub async fn detect_agent_internal<R: tauri::Runtime>(
    agent_id: String,
    app: tauri::AppHandle<R>,
) -> Result<AgentStatus, String> {
    let configs = load_config(&app).unwrap_or_default();

    let is_windows = cfg!(target_os = "windows");
    let mut found_path: Option<String> = None;
    let mut binary_name = agent_id.clone();
    let mut version_args = vec!["--version".to_string()];

    if let Some(config) = configs.get(&agent_id) {
        binary_name = config.binary.clone();
        version_args = config.version_args.clone();

        // 0. Scan application local subdirectory `./bin/` (highly preferred for portable ZIP config)
        //
        // Bug fixed: this used to take exe_path.parent() directly, which on
        // macOS is just Contents/MacOS/ (one level above the raw Mach-O
        // binary inside the .app bundle) — nowhere near the actual `./bin/`
        // sibling of the bundle itself, so this check silently never matched
        // on macOS and always fell through to steps 1/2 below. Use
        // resolve_app_bundle_dir, which correctly unwraps the .app bundle on
        // macOS (and is a no-op beyond exe_path.parent() on Windows/Linux,
        // where the executable already sits directly in this folder).
        if let Ok(exe_path) = std::env::current_exe() {
            let local_bin_name = if is_windows {
                format!("{}.exe", config.binary)
            } else {
                config.binary.clone()
            };

            // Check in app bundle directory (bin/agy)
            let exe_dir = resolve_app_bundle_dir(exe_path.clone());
            let local_path = exe_dir.join("bin").join(&local_bin_name);
            if local_path.exists() {
                found_path = Some(local_path.to_string_lossy().to_string());
            }

            // Check in app bundle directory's app/bin (app/bin/agy)
            if found_path.is_none() {
                let local_path = exe_dir.join("app").join("bin").join(&local_bin_name);
                if local_path.exists() {
                    found_path = Some(local_path.to_string_lossy().to_string());
                }
            }

            // Check in project root (bin/agy)
            if found_path.is_none() {
                let proj_dir = resolve_project_root(exe_path.clone());
                let local_path = proj_dir.join("bin").join(&local_bin_name);
                if local_path.exists() {
                    found_path = Some(local_path.to_string_lossy().to_string());
                }
            }

            // Check in project root's app/bin (app/bin/agy from project root perspective)
            if found_path.is_none() {
                let proj_dir = resolve_project_root(exe_path.clone());
                let local_path = proj_dir.join("app").join("bin").join(&local_bin_name);
                if local_path.exists() {
                    found_path = Some(local_path.to_string_lossy().to_string());
                }
            }
        }

        // 1. Scan pre-defined directory paths
        let paths_to_check = if is_windows {
            &config.detect_paths.windows
        } else {
            &config.detect_paths.macos
        };

        if found_path.is_none() {
            if let Some(ref paths) = paths_to_check {
                for path_str in paths {
                    let path = resolve_env_path(path_str);
                    if path.exists() {
                        found_path = Some(path.to_string_lossy().to_string());
                        break;
                    }
                }
            }
        }
    }

    // 2. Scan system PATH using which/where
    if found_path.is_none() {
        let check_cmd = if is_windows { "where" } else { "which" };
        let mut cmd = Command::new(check_cmd);
        cmd.arg(&binary_name);
        #[cfg(target_os = "windows")]
        cmd.creation_flags(CREATE_NO_WINDOW);
        let output = cmd.output();

        if let Ok(out) = output {
            if out.status.success() {
                let path_str = String::from_utf8_lossy(&out.stdout).trim().to_string();
                if !path_str.is_empty() {
                    let first_line = path_str.lines().next().unwrap_or("").to_string();
                    if !first_line.is_empty() {
                        found_path = Some(first_line);
                    }
                }
            }
        }
    }

    if let Some(path) = found_path {
        // Run <binary> --version to get version string
        let mut cmd = Command::new(&path);
        cmd.args(&version_args);
        #[cfg(target_os = "windows")]
        cmd.creation_flags(CREATE_NO_WINDOW);

        let version = cmd.output().ok().and_then(|out| {
            if out.status.success() {
                let ver_str = String::from_utf8_lossy(&out.stdout).trim().to_string();
                Some(ver_str.lines().next().unwrap_or("").to_string())
            } else {
                None
            }
        });

        Ok(AgentStatus {
            installed: true,
            path: Some(path),
            version,
        })
    } else {
        Ok(AgentStatus {
            installed: false,
            path: None,
            version: None,
        })
    }
}

pub async fn get_install_command_internal<R: tauri::Runtime>(
    agent_id: String,
    app: tauri::AppHandle<R>,
) -> Result<InstallCommand, String> {
    let configs = load_config(&app)?;
    let config = configs.get(&agent_id).ok_or_else(|| format!("Unknown agent: {}", agent_id))?;

    let is_windows = cfg!(target_os = "windows");
    let cmd = if is_windows {
        config.install.windows.clone()
    } else {
        config.install.macos.clone()
    };

    cmd.ok_or_else(|| "Install command not defined for this OS".to_string())
}

pub async fn check_agent_update_internal<R: tauri::Runtime>(
    agent_id: String,
    app: tauri::AppHandle<R>,
) -> Result<UpdateStatus, String> {
    let status = detect_agent_internal(agent_id, app).await?;
    if !status.installed {
        return Ok(UpdateStatus {
            current_version: None,
            latest_version: None,
            update_available: false,
        });
    }

    let current = status.version;
    let latest = fetch_latest_version_from_web().or_else(|| {
        // Best-effort fallback: if query fails, default to current version (no update alert)
        current.clone()
    });

    let update_available = match (&current, &latest) {
        (Some(cur), Some(lat)) => cur.trim() != lat.trim(),
        _ => false,
    };

    Ok(UpdateStatus {
        current_version: current,
        latest_version: latest,
        update_available,
    })
}

pub async fn get_update_command_internal<R: tauri::Runtime>(
    agent_id: String,
    app: tauri::AppHandle<R>,
) -> Result<InstallCommand, String> {
    let configs = load_config(&app)?;
    let config = configs.get(&agent_id).ok_or_else(|| format!("Unknown agent: {}", agent_id))?;

    let is_windows = cfg!(target_os = "windows");
    let cmd = if is_windows {
        config.update.windows.clone()
    } else {
        config.update.macos.clone()
    };

    cmd.ok_or_else(|| "Update command not defined for this OS".to_string())
}

// --- Tauri Command Wrapper ---

#[tauri::command]
pub async fn detect_agent(agent_id: String, app: AppHandle) -> Result<AgentStatus, String> {
    detect_agent_internal(agent_id, app).await
}

#[tauri::command]
pub async fn get_install_command(agent_id: String, app: AppHandle) -> Result<InstallCommand, String> {
    get_install_command_internal(agent_id, app).await
}

#[tauri::command]
pub async fn check_agent_update(agent_id: String, app: AppHandle) -> Result<UpdateStatus, String> {
    check_agent_update_internal(agent_id, app).await
}

#[tauri::command]
pub async fn get_update_command(agent_id: String, app: AppHandle) -> Result<InstallCommand, String> {
    get_update_command_internal(agent_id, app).await
}

// --- Test Code ---

#[tauri::command]
pub fn check_skill_folder(cwd: String) -> bool {
    if cwd.is_empty() {
        return false;
    }
    let path = std::path::Path::new(&cwd).join("skill");
    path.exists() && path.is_dir()
}

#[tauri::command]
pub async fn build_skill(
    cwd: String,
    agent_id: String,
    app: tauri::AppHandle,
) -> Result<String, String> {
    build_skill_internal(cwd, agent_id, app).await
}

pub async fn build_skill_internal<R: tauri::Runtime>(
    cwd: String,
    agent_id: String,
    app: tauri::AppHandle<R>,
) -> Result<String, String> {
    if cwd.is_empty() {
        return Err("Current working directory is empty".to_string());
    }

    // 1. Detect agent binary path
    let status = detect_agent_internal(agent_id.clone(), app.clone()).await?;
    let binary_path = if status.installed {
        status.path.ok_or_else(|| "Installed agent has no path".to_string())?
    } else {
        return Err(format!("Agent {} is not installed", agent_id));
    };

    // 2. Build skill using "agy build"
    let mut cmd = std::process::Command::new(&binary_path);
    cmd.arg("build");
    cmd.current_dir(&cwd);
    #[cfg(target_os = "windows")]
    cmd.creation_flags(CREATE_NO_WINDOW);

    let output = cmd.output().map_err(|e| format!("Failed to execute build command: {}", e))?;

    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).trim().to_string())
    } else {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
        Err(format!("Build failed.\nStdout: {}\nStderr: {}", stdout, stderr))
    }
}

// --- Generic pre-launch command (config.AppConfig.pre_launch_command) ---
//
// Runs an arbitrary configured command in the selected working directory
// before a PTY session starts, so a parent project (e.g. one bundling this
// app as its GUI shell) can run its own setup/update/auth checks first. This
// generalizes the skill-folder-specific check_skill_folder/build_skill flow
// above for projects that need more than "rebuild a skill folder".
//
// Streams output live via "pre-launch-output" events (same payload shape and
// consumption path as pty.rs's "pty-output" — the frontend feeds both into
// the same xterm.js instance via onRawOutput) rather than blocking silently:
// a project's pre-launch check can take minutes on a first run (e.g.
// downloading a portable Python runtime, creating a venv, installing
// dependencies), during which a static "running checks..." message with no
// visible progress reads as a hang.
//
// Unlike pty.rs's PTY session, this does NOT use a real PTY (portable_pty) —
// just plain piped stdio read on background threads — because we need the
// real process exit code for pre_launch_required's block-on-failure
// semantics, and Child::wait() gives us that directly. The PTY read loop in
// pty.rs only ever emits "terminated"/"error" with no exit code (that's fine
// for the install/update flows, which use it via an indirect
// check-installed-status-afterward signal instead), which isn't enough here.

#[derive(Serialize, Clone, Debug)]
pub struct PreLaunchOutputPayload {
    pub data: Vec<u8>,
}

// Since start_pre_launch_command_internal reads plain piped stdio (not a
// real PTY — see the comment above on why), the child's bare "\n" line
// endings reach us as-is: no kernel tty line discipline (ONLCR) is there to
// translate them to "\r\n" the way it transparently does for pty.rs's real
// PTY session. The frontend feeds both output streams into the same
// xterm.js instance, which — like any real terminal — only resets the
// cursor column on "\r"; a bare "\n" just moves down a row, producing a
// diagonal/staircase misalignment across multi-line output (observed with
// preflight.sh's Japanese-language setup prompts). Insert the missing "\r"
// ourselves. `last_was_cr` carries state across chunk boundaries so a "\r"
// that ends one 1024-byte read and the "\n" that begins the next aren't
// double-translated into "\r\r\n".
fn normalize_lf_to_crlf(buf: &[u8], last_was_cr: &mut bool) -> Vec<u8> {
    let mut out = Vec::with_capacity(buf.len());
    for (i, &b) in buf.iter().enumerate() {
        if b == b'\n' {
            let prev_was_cr = if i == 0 { *last_was_cr } else { buf[i - 1] == b'\r' };
            if !prev_was_cr {
                out.push(b'\r');
            }
        }
        out.push(b);
    }
    if let Some(&last) = buf.last() {
        *last_was_cr = last == b'\r';
    }
    out
}

#[derive(Serialize, Clone, Debug)]
pub struct PreLaunchStatusPayload {
    pub success: bool,
}

#[tauri::command]
pub async fn start_pre_launch_command<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    cwd: String,
    command: String,
    args: Vec<String>,
) -> Result<(), String> {
    start_pre_launch_command_internal(app, cwd, command, args)
}

fn start_pre_launch_command_internal<R: tauri::Runtime>(
    app: tauri::AppHandle<R>,
    cwd: String,
    command: String,
    args: Vec<String>,
) -> Result<(), String> {
    if command.is_empty() {
        return Err("pre_launch_command is empty".to_string());
    }

    let mut cmd = Command::new(&command);
    cmd.args(&args);
    // Match start_pty's cwd resolution (pty.rs): fall back to the resolved
    // project root rather than leaving the child's cwd unset, which would
    // default to wherever the OS happened to launch this app from (e.g. "/"
    // on macOS for a double-clicked .app) — not the project root where a
    // relative pre_launch_args script (like "preflight.sh") actually lives.
    // Without this, a project bundling this app whose user never explicitly
    // picked a working directory would see "No such file or directory".
    if cwd.is_empty() {
        cmd.current_dir(get_default_cwd());
    } else {
        cmd.current_dir(&cwd);
    }
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::piped());
    #[cfg(target_os = "windows")]
    cmd.creation_flags(CREATE_NO_WINDOW);

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("Failed to execute pre-launch command '{}': {}", command, e))?;

    // Order between the stdout and stderr streams isn't preserved relative
    // to each other (two independent reader threads), only within each
    // stream — acceptable for progress display, where exact interleaving
    // rarely matters.
    for pipe in [
        child.stdout.take().map(|s| Box::new(s) as Box<dyn Read + Send>),
        child.stderr.take().map(|s| Box::new(s) as Box<dyn Read + Send>),
    ]
    .into_iter()
    .flatten()
    {
        let app_clone = app.clone();
        thread::spawn(move || {
            let mut reader = pipe;
            let mut buf = [0u8; 1024];
            let mut last_was_cr = false;
            loop {
                match reader.read(&mut buf) {
                    Ok(0) | Err(_) => break,
                    Ok(n) => {
                        let data = normalize_lf_to_crlf(&buf[..n], &mut last_was_cr);
                        let _ = app_clone.emit(
                            "pre-launch-output",
                            PreLaunchOutputPayload { data },
                        );
                    }
                }
            }
        });
    }

    thread::spawn(move || {
        let success = child.wait().map(|s| s.success()).unwrap_or(false);
        let _ = app.emit("pre-launch-status", PreLaunchStatusPayload { success });
    });

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_resolve_env_path() {
        let home = std::env::var("HOME").unwrap_or_default();
        if !home.is_empty() {
            let path = resolve_env_path("$HOME/test/path");
            assert_eq!(path.to_string_lossy(), format!("{}/test/path", home));
        }

        let userprofile = std::env::var("USERPROFILE").unwrap_or_default();
        if !userprofile.is_empty() {
            let path = resolve_env_path("$USERPROFILE\\test\\path");
            assert_eq!(path.to_string_lossy(), format!("{}\\test\\path", userprofile));
        }
    }

    #[tokio::test]
    async fn test_detect_agent_mock() {
        use tauri::test::mock_app;
        let app = mock_app();
        
        let status = detect_agent_internal("agy".to_string(), app.handle().clone()).await;
        assert!(status.is_ok());
        
        let s = status.unwrap();
        println!("Mock detect result for agy: installed = {}, path = {:?}", s.installed, s.path);
    }

    #[test]
    fn test_skill_detection_mock() {
        let temp_dir = std::env::temp_dir();
        let skill_dir = temp_dir.join("skill");
        
        if skill_dir.exists() {
            let _ = std::fs::remove_dir_all(&skill_dir);
        }
        
        let path_str = temp_dir.to_string_lossy().to_string();
        
        assert_eq!(check_skill_folder(path_str.clone()), false);
        
        std::fs::create_dir(&skill_dir).unwrap();
        assert_eq!(check_skill_folder(path_str.clone()), true);
        
        let _ = std::fs::remove_dir_all(&skill_dir);
    }

    #[tokio::test]
    async fn test_check_agent_update_mock() {
        use tauri::test::mock_app;
        let app = mock_app();

        let status = check_agent_update_internal("agy".to_string(), app.handle().clone()).await;
        assert!(status.is_ok());

        let s = status.unwrap();
        println!("Mock update result for agy: {:?}", s);
    }

    // Drains a "pre-launch-status" success flag and the concatenated text of
    // all "pre-launch-output" events received within a short timeout, using
    // the same mock_app + Listener pattern as pty.rs's test_start_pty_and_emission.
    async fn run_and_collect<R: tauri::Runtime>(
        app: &tauri::AppHandle<R>,
        cwd: String,
        command: String,
        args: Vec<String>,
    ) -> (Option<bool>, String) {
        use tauri::Listener;

        let (status_tx, mut status_rx) = tokio::sync::mpsc::channel(1);
        app.listen("pre-launch-status", move |event| {
            if let Ok(payload) = serde_json::from_str::<serde_json::Value>(event.payload()) {
                if let Some(success) = payload.get("success").and_then(|v| v.as_bool()) {
                    let _ = status_tx.try_send(success);
                }
            }
        });

        let (out_tx, mut out_rx) = tokio::sync::mpsc::channel(64);
        app.listen("pre-launch-output", move |event| {
            if let Ok(payload) = serde_json::from_str::<serde_json::Value>(event.payload()) {
                if let Some(bytes) = payload.get("data").and_then(|v| v.as_array()) {
                    let data: Vec<u8> = bytes.iter().filter_map(|b| b.as_u64()).map(|b| b as u8).collect();
                    let _ = out_tx.try_send(String::from_utf8_lossy(&data).into_owned());
                }
            }
        });

        start_pre_launch_command_internal(app.clone(), cwd, command, args).unwrap();

        let mut success = None;
        let mut output = String::new();
        let deadline = tokio::time::sleep(tokio::time::Duration::from_secs(3));
        tokio::pin!(deadline);
        loop {
            tokio::select! {
                Some(s) = status_rx.recv() => { success = Some(s); if out_rx.is_empty() { break; } }
                Some(chunk) = out_rx.recv() => { output.push_str(&chunk); }
                _ = &mut deadline => break,
            }
        }
        (success, output)
    }

    #[tokio::test]
    async fn test_start_pre_launch_command_success() {
        use tauri::test::mock_app;
        let app = mock_app();
        let handle = app.handle().clone();

        let (cmd, args): (&str, Vec<&str>) = if cfg!(target_os = "windows") {
            ("cmd", vec!["/c", "exit 0"])
        } else {
            ("sh", vec!["-c", "exit 0"])
        };
        let (success, _) = run_and_collect(
            &handle,
            String::new(),
            cmd.to_string(),
            args.into_iter().map(String::from).collect(),
        )
        .await;
        assert_eq!(success, Some(true));
    }

    #[tokio::test]
    async fn test_start_pre_launch_command_failure_surfaces_nonzero_exit() {
        use tauri::test::mock_app;
        let app = mock_app();
        let handle = app.handle().clone();

        let (cmd, args): (&str, Vec<&str>) = if cfg!(target_os = "windows") {
            ("cmd", vec!["/c", "exit 1"])
        } else {
            ("sh", vec!["-c", "exit 1"])
        };
        let (success, _) = run_and_collect(
            &handle,
            String::new(),
            cmd.to_string(),
            args.into_iter().map(String::from).collect(),
        )
        .await;
        assert_eq!(success, Some(false));
    }

    #[test]
    fn test_start_pre_launch_command_empty_command_is_error() {
        use tauri::test::mock_app;
        let app = mock_app();
        let result = start_pre_launch_command_internal(app.handle().clone(), String::new(), String::new(), vec![]);
        assert!(result.is_err());
    }

    // Regression test for the "column staircase" bug (2026-07-15): piped
    // child stdout carries bare "\n" with no kernel tty layer to add the "\r"
    // xterm.js needs to reset the cursor column, so multi-line output (e.g.
    // preflight.sh's setup prompts) rendered progressively further right on
    // each line instead of starting at column 0.
    #[test]
    fn test_normalize_lf_to_crlf_inserts_missing_cr() {
        let mut last_was_cr = false;
        let out = normalize_lf_to_crlf(b"line one\nline two\n", &mut last_was_cr);
        assert_eq!(out, b"line one\r\nline two\r\n");
    }

    #[test]
    fn test_normalize_lf_to_crlf_leaves_existing_crlf_untouched() {
        let mut last_was_cr = false;
        let out = normalize_lf_to_crlf(b"already\r\ncrlf\r\n", &mut last_was_cr);
        assert_eq!(out, b"already\r\ncrlf\r\n");
    }

    #[test]
    fn test_normalize_lf_to_crlf_handles_cr_split_across_chunks() {
        // A "\r" landing on the last byte of one 1024-byte read and the "\n"
        // that completes it arriving at the start of the next read must not
        // be double-translated into "\r\r\n".
        let mut last_was_cr = false;
        let first = normalize_lf_to_crlf(b"partial\r", &mut last_was_cr);
        assert_eq!(first, b"partial\r");
        assert!(last_was_cr);

        let second = normalize_lf_to_crlf(b"\nrest", &mut last_was_cr);
        assert_eq!(second, b"\nrest");
    }

    #[tokio::test]
    async fn test_start_pre_launch_command_multiline_output_uses_crlf() {
        use tauri::test::mock_app;
        let app = mock_app();
        let handle = app.handle().clone();

        let (cmd, args): (&str, Vec<&str>) = if cfg!(target_os = "windows") {
            ("cmd", vec!["/c", "echo line-one&echo line-two"])
        } else {
            ("printf", vec!["line-one\\nline-two\\n"])
        };
        let (_success, output) = run_and_collect(
            &handle,
            String::new(),
            cmd.to_string(),
            args.into_iter().map(String::from).collect(),
        )
        .await;
        assert!(
            output.contains("line-one\r\nline-two"),
            "expected CRLF-separated lines, got: {:?}",
            output
        );
    }

    #[tokio::test]
    async fn test_start_pre_launch_command_streams_output() {
        use tauri::test::mock_app;
        let app = mock_app();
        let handle = app.handle().clone();

        let (cmd, args): (&str, Vec<&str>) = if cfg!(target_os = "windows") {
            ("cmd", vec!["/c", "echo streaming-test"])
        } else {
            ("echo", vec!["streaming-test"])
        };
        let (success, output) = run_and_collect(
            &handle,
            String::new(),
            cmd.to_string(),
            args.into_iter().map(String::from).collect(),
        )
        .await;
        assert_eq!(success, Some(true));
        assert!(output.contains("streaming-test"), "expected streamed output to contain the echoed text, got: {:?}", output);
    }

    #[tokio::test]
    async fn test_start_pre_launch_command_uses_cwd() {
        use tauri::test::mock_app;
        let app = mock_app();
        let handle = app.handle().clone();

        let temp_dir = std::env::temp_dir().join(format!(
            "agent_ui_prelaunch_test_{}",
            std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_nanos()
        ));
        std::fs::create_dir_all(&temp_dir).unwrap();
        std::fs::write(temp_dir.join("marker.txt"), "hi").unwrap();

        let (cmd, args): (&str, Vec<String>) = if cfg!(target_os = "windows") {
            ("cmd", vec!["/c".to_string(), "if exist marker.txt (exit 0) else (exit 1)".to_string()])
        } else {
            ("sh", vec!["-c".to_string(), "test -f marker.txt".to_string()])
        };
        let (success, _) = run_and_collect(&handle, temp_dir.to_string_lossy().to_string(), cmd.to_string(), args).await;
        assert_eq!(success, Some(true), "command should find marker.txt in the given cwd");

        let _ = std::fs::remove_dir_all(&temp_dir);
    }

    #[tokio::test]
    async fn test_start_pre_launch_command_empty_cwd_falls_back_to_default_cwd() {
        // Regression guard: an empty cwd must resolve to get_default_cwd()
        // (matching start_pty's own fallback), not leave the child process's
        // cwd unset — which previously broke a relative pre_launch_args
        // script the moment the user hadn't explicitly picked a working
        // directory yet.
        use tauri::test::mock_app;
        let app = mock_app();
        let handle = app.handle().clone();

        let default_dir = get_default_cwd();
        let marker_name = format!(
            "agent_ui_prelaunch_default_cwd_marker_{}",
            std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_nanos()
        );
        std::fs::write(default_dir.join(&marker_name), "hi").unwrap();

        let (cmd, args): (&str, Vec<String>) = if cfg!(target_os = "windows") {
            ("cmd", vec!["/c".to_string(), format!("if exist {} (exit 0) else (exit 1)", marker_name)])
        } else {
            ("sh", vec!["-c".to_string(), format!("test -f {}", marker_name)])
        };
        let (success, _) = run_and_collect(&handle, String::new(), cmd.to_string(), args).await;
        assert_eq!(success, Some(true), "empty cwd should resolve to get_default_cwd(), not the OS's arbitrary default");

        let _ = std::fs::remove_file(default_dir.join(&marker_name));
    }
}
