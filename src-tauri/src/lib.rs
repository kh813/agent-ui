mod pty;
mod agent;
mod config;
mod menu;

use pty::PtyState;

// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(PtyState::default())
        // Tauri only builds this default Edit/Window/Help menu automatically on macOS;
        // set it explicitly so Windows and Linux also get a menu bar with Copy/Paste/etc.,
        // plus Theme and Settings submenus mirroring in-app preferences.
        .menu(|handle| menu::build_menu(handle, &config::get_app_config(None).default_theme, true))
        .on_menu_event(menu::handle_menu_event)
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_store::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            greet,
            pty::start_pty,
            pty::write_to_pty,
            pty::stop_pty,
            pty::resize_pty,
            agent::detect_agent,
            agent::get_install_command,
            agent::check_agent_update,
            agent::get_update_command,
            agent::check_skill_folder,
            agent::build_skill,
            config::get_app_config,
            menu::set_theme,
            menu::set_auto_check_update
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_greet() {
        let result = greet("World");
        assert_eq!(result, "Hello, World! You've been greeted from Rust!");
    }
}
