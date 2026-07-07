use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{PathBuf, Path};

use crate::pty::resolve_project_root;

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct EngineConfig {
    pub id: String,
    pub name: String,
    pub command: String,
    pub args: Vec<String>,
}

#[derive(Serialize, Deserialize, Clone, Debug)]
pub struct AppConfig {
    pub app_name: String,
    pub default_theme: String,
    pub font_family: String,
    pub font_size: u32,
    pub engines: Vec<EngineConfig>,
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            app_name: "agent-ui Chat Console".to_string(),
            default_theme: "light".to_string(),
            font_family: "Menlo, Monaco, 'Courier New', monospace".to_string(),
            font_size: 13,
            engines: vec![EngineConfig {
                id: "agy".to_string(),
                name: "Antigravity".to_string(),
                command: "agy".to_string(),
                args: vec![],
            }],
        }
    }
}

fn get_exe_dir() -> Option<PathBuf> {
    std::env::current_exe().ok().and_then(|p| p.parent().map(|parent| parent.to_path_buf()))
}

#[tauri::command]
pub fn get_app_config(cwd: Option<String>) -> AppConfig {
    let mut search_paths = Vec::new();

    // 1. Search in the CWD (Selected Working Directory)
    if let Some(ref cwd_str) = cwd {
        let cwd_base = Path::new(cwd_str);
        search_paths.push(cwd_base.join("agent_config.json"));
        search_paths.push(cwd_base.join("config").join("agent_config.json"));
    }

    // 2. Search using the same project-root resolution as PTY launch
    // (macOS bundles need to traverse out of Contents/MacOS + the .app + the
    // app/ wrapper folder; get_exe_dir() alone only reaches Contents/MacOS).
    if let Ok(exe_path) = std::env::current_exe() {
        let project_root = resolve_project_root(exe_path);
        search_paths.push(project_root.join("agent_config.json"));
        search_paths.push(project_root.join("config").join("agent_config.json"));
    }

    // 3. Search in the directory containing the executable
    if let Some(exe_dir) = get_exe_dir() {
        search_paths.push(exe_dir.join("agent_config.json"));
        search_paths.push(exe_dir.join("config").join("agent_config.json"));
    }

    // 4. Search in the current runtime working directory
    search_paths.push(PathBuf::from("agent_config.json"));
    search_paths.push(PathBuf::from("config").join("agent_config.json"));

    // Traverse and load the first valid config file found
    for path in search_paths {
        if path.exists() {
            if let Ok(content) = fs::read_to_string(&path) {
                if let Ok(config) = serde_json::from_str::<AppConfig>(&content) {
                    return config;
                }
            }
        }
    }

    // Return default fallback
    AppConfig::default()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    #[test]
    fn test_get_app_config_cwd_resolution() {
        // Create a unique temporary directory
        let temp_base = std::env::temp_dir().join(format!("agent_ui_test_{}", uuid_like_timestamp()));
        let config_dir = temp_base.join("config");
        fs::create_dir_all(&config_dir).unwrap();

        // 1. Test fallback when no file is present
        let config = get_app_config(Some(temp_base.to_string_lossy().to_string()));
        assert_eq!(config.app_name, "agent-ui Chat Console"); // default value

        // 2. Test reading config from CWD root (agent_config.json)
        let config_file_cwd = temp_base.join("agent_config.json");
        let custom_config_cwd = r#"{
            "app_name": "Test Custom CWD",
            "default_theme": "dark",
            "font_family": "Courier",
            "font_size": 16,
            "engines": []
        }"#;
        fs::write(&config_file_cwd, custom_config_cwd).unwrap();

        let config = get_app_config(Some(temp_base.to_string_lossy().to_string()));
        assert_eq!(config.app_name, "Test Custom CWD");
        assert_eq!(config.default_theme, "dark");
        assert_eq!(config.font_size, 16);

        // 3. Test reading config from config/ directory (config/agent_config.json)
        // Delete the root file so it checks the config folder
        let _ = fs::remove_file(&config_file_cwd);

        let config_file_sub = config_dir.join("agent_config.json");
        let custom_config_sub = r#"{
            "app_name": "Test Custom Config Dir",
            "default_theme": "solarizedDark",
            "font_family": "Monospace",
            "font_size": 14,
            "engines": []
        }"#;
        fs::write(&config_file_sub, custom_config_sub).unwrap();

        let config = get_app_config(Some(temp_base.to_string_lossy().to_string()));
        assert_eq!(config.app_name, "Test Custom Config Dir");
        assert_eq!(config.default_theme, "solarizedDark");
        assert_eq!(config.font_size, 14);

        // Cleanup
        let _ = fs::remove_dir_all(&temp_base);
    }

    fn uuid_like_timestamp() -> u128 {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos()
    }
}
