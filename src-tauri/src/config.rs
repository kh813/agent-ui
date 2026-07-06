use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{PathBuf, Path};

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

    // 2. Search in the directory containing the executable
    if let Some(exe_dir) = get_exe_dir() {
        search_paths.push(exe_dir.join("agent_config.json"));
        search_paths.push(exe_dir.join("config").join("agent_config.json"));
    }

    // 3. Search in the current runtime working directory
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
