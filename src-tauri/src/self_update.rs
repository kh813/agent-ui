// agent-deck's own self-update, distinct from agent.rs's per-engine
// install/update machinery (which drives agy via install_commands.json).
// self_update.py resolves its own project root from `__file__` and needs no
// venv (pure stdlib), so this can just shell out to a plain system
// python3/python with no cwd gymnastics.
use std::process::Command;

use crate::agent::{InstallCommand, UpdateStatus};
use crate::pty::get_default_cwd;

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

fn python_bin() -> &'static str {
    if cfg!(target_os = "windows") {
        "python"
    } else {
        "python3"
    }
}

fn self_update_script_path() -> std::path::PathBuf {
    get_default_cwd()
        .join("python")
        .join("scripts")
        .join("setup")
        .join("self_update.py")
}

pub fn check_self_update_internal() -> Result<UpdateStatus, String> {
    let no_update = UpdateStatus {
        current_version: None,
        latest_version: None,
        update_available: false,
    };

    let mut cmd = Command::new(python_bin());
    cmd.arg(self_update_script_path()).arg("check").arg("--json");
    cmd.current_dir(get_default_cwd());
    #[cfg(target_os = "windows")]
    cmd.creation_flags(CREATE_NO_WINDOW);

    // Best-effort, same philosophy as check_agent_update_internal's own
    // fallback: no python, no network, or a bad GitHub API response should
    // never surface an error to the user -- it just means "no update alert
    // this time", not a broken app.
    let Ok(output) = cmd.output() else {
        return Ok(no_update);
    };
    if !output.status.success() {
        return Ok(no_update);
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let Some(line) = stdout.lines().last() else {
        return Ok(no_update);
    };
    let Ok(parsed) = serde_json::from_str::<serde_json::Value>(line.trim()) else {
        return Ok(no_update);
    };

    let update_available = parsed
        .get("update_available")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let installed_tag = parsed
        .get("installed_tag")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string());
    let latest_tag = parsed
        .get("latest_tag")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());

    Ok(UpdateStatus {
        current_version: installed_tag,
        latest_version: latest_tag,
        update_available,
    })
}

pub fn get_self_update_command_internal() -> InstallCommand {
    InstallCommand {
        command: python_bin().to_string(),
        args: vec![
            self_update_script_path().to_string_lossy().to_string(),
            "apply".to_string(),
        ],
    }
}

// --- Tauri Command Wrappers ---

#[tauri::command]
pub async fn check_self_update() -> Result<UpdateStatus, String> {
    check_self_update_internal()
}

#[tauri::command]
pub async fn get_self_update_command() -> Result<InstallCommand, String> {
    Ok(get_self_update_command_internal())
}
