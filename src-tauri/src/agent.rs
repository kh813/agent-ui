use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs;
use std::path::{PathBuf};
use std::process::Command;
use tauri::{AppHandle, Manager};

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

// Load configurations from resource file, resolving via resource_dir in Tauri v2
fn load_config<R: tauri::Runtime>(app: &tauri::AppHandle<R>) -> Result<HashMap<String, AgentConfig>, String> {
    let resource_path = app
        .path()
        .resource_dir()
        .map(|p| p.join("resources/install_commands.json"))
        .map_err(|e| format!("Failed to get resource directory: {}", e))?;

    let path = if resource_path.exists() {
        resource_path
    } else {
        // Fallback during cargo test execution
        let test_path = PathBuf::from("resources/install_commands.json");
        if test_path.exists() {
            test_path
        } else {
            PathBuf::from("src-tauri/resources/install_commands.json")
        }
    };

    let content = fs::read_to_string(&path)
        .map_err(|e| format!("Failed to read config from {:?}: {}", path, e))?;

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

// Best-effort fetch of latest version from web via OS-specific CLI tools
fn fetch_latest_version_from_web() -> Option<String> {
    let is_windows = cfg!(target_os = "windows");
    let output = if is_windows {
        Command::new("powershell")
            .args(&["-Command", "try { (Invoke-WebRequest -UseBasicParsing https://antigravity.google.com/version.txt -TimeoutSec 3).Content.Trim() } catch { exit 1 }"])
            .output()
    } else {
        Command::new("curl")
            .args(&["-fsSL", "--max-time", "3", "https://antigravity.google.com/version.txt"])
            .output()
    };

    if let Ok(out) = output {
        if out.status.success() {
            let ver = String::from_utf8_lossy(&out.stdout).trim().to_string();
            if !ver.is_empty() {
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
    let configs = load_config(&app)?;
    let config = configs.get(&agent_id).ok_or_else(|| format!("Unknown agent: {}", agent_id))?;

    let is_windows = cfg!(target_os = "windows");
    
    // 1. Scan pre-defined directory paths
    let paths_to_check = if is_windows {
        &config.detect_paths.windows
    } else {
        &config.detect_paths.macos
    };

    let mut found_path: Option<String> = None;

    if let Some(ref paths) = paths_to_check {
        for path_str in paths {
            let path = resolve_env_path(path_str);
            if path.exists() {
                found_path = Some(path.to_string_lossy().to_string());
                break;
            }
        }
    }

    // 2. Scan system PATH using which/where
    if found_path.is_none() {
        let check_cmd = if is_windows { "where" } else { "which" };
        let output = Command::new(check_cmd)
            .arg(&config.binary)
            .output();

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
        cmd.args(&config.version_args);
        
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
