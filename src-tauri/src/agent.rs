use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::{PathBuf};
use std::process::Command;
use tauri::{AppHandle, Manager};

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
        if let Ok(exe_path) = std::env::current_exe() {
            if let Some(exe_dir) = exe_path.parent() {
                let local_bin_name = if is_windows {
                    format!("{}.exe", config.binary)
                } else {
                    config.binary.clone()
                };
                let local_path = exe_dir.join("bin").join(local_bin_name);
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
}
