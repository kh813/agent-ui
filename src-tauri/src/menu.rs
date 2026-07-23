use std::sync::Mutex;
use tauri::menu::{CheckMenuItem, IsMenuItem, Menu, MenuEvent, MenuItem, Submenu, HELP_SUBMENU_ID};
use tauri::{AppHandle, Emitter, Manager};

const THEME_MENU_ID_PREFIX: &str = "theme:";
const AUTO_CHECK_UPDATE_MENU_ID: &str = "settings:auto-check-update";
const CHECK_SELF_UPDATE_MENU_ID: &str = "settings:check-self-update";
const CHECK_SELF_UPDATE_TEST_MENU_ID: &str = "settings:check-self-update-test";

// Keep in sync with the theme ids/names in src/utils/themes.ts
const THEMES: &[(&str, &str)] = &[
    ("light", "Light (Default)"),
    ("dark", "Dark"),
    ("solarizedLight", "Solarized Light"),
    ("solarizedDark", "Solarized Dark"),
    ("dracula", "Dracula"),
    ("oneDark", "One Dark"),
];

struct ThemeMenuState(Mutex<Vec<(String, CheckMenuItem<tauri::Wry>)>>);
struct AutoCheckUpdateMenuState(CheckMenuItem<tauri::Wry>);

// Tauri only builds its default Edit/Window/Help menu automatically on macOS,
// so build it explicitly (Windows/Linux get a menu bar too) and add a Theme
// submenu that mirrors the in-app theme selector.
pub fn build_menu(
    handle: &AppHandle,
    initial_theme: &str,
    initial_auto_check_update: bool,
) -> tauri::Result<Menu<tauri::Wry>> {
    let menu = Menu::default(handle)?;

    let items: Vec<(String, CheckMenuItem<tauri::Wry>)> = THEMES
        .iter()
        .map(|(id, label)| {
            let item = CheckMenuItem::with_id(
                handle,
                format!("{THEME_MENU_ID_PREFIX}{id}"),
                *label,
                true,
                *id == initial_theme,
                None::<&str>,
            )?;
            Ok((id.to_string(), item))
        })
        .collect::<tauri::Result<_>>()?;

    let theme_submenu_items: Vec<&dyn IsMenuItem<tauri::Wry>> =
        items.iter().map(|(_, item)| item as &dyn IsMenuItem<tauri::Wry>).collect();
    let theme_submenu = Submenu::with_items(handle, "Theme", true, &theme_submenu_items)?;

    let auto_check_update_item = CheckMenuItem::with_id(
        handle,
        AUTO_CHECK_UPDATE_MENU_ID,
        "Check for Updates on Startup",
        true,
        initial_auto_check_update,
        None::<&str>,
    )?;
    // Distinct from the toggle above: that one is about auto-checking agy
    // (the Antigravity CLI engine) on launch. This is an on-demand action
    // for agent-deck's own GitHub-Releases-based self-update (previously
    // only reachable via the now-retired `/update` chat skill).
    let check_self_update_item = MenuItem::with_id(
        handle,
        CHECK_SELF_UPDATE_MENU_ID,
        "Check for agent-deck Updates...",
        true,
        None::<&str>,
    )?;
    // Test channel: latest GitHub pre-release (see release.yml's "determine
    // release channel" step and self_update.py's --test flag) instead of
    // /releases/latest. Lets someone flip back and forth between a
    // pre-release build and production without touching a terminal.
    let check_self_update_test_item = MenuItem::with_id(
        handle,
        CHECK_SELF_UPDATE_TEST_MENU_ID,
        "Check for agent-deck Updates (Test)...",
        true,
        None::<&str>,
    )?;
    let settings_submenu = Submenu::with_items(
        handle,
        "Settings",
        true,
        &[&auto_check_update_item, &check_self_update_item, &check_self_update_test_item],
    )?;

    // Place Theme/Settings just before Help, matching where most apps put extra top-level menus.
    let help_index = menu.items()?.iter().position(|item| item.id() == HELP_SUBMENU_ID);
    match help_index {
        Some(index) => menu.insert(&theme_submenu, index)?,
        None => menu.append(&theme_submenu)?,
    }
    let help_index = menu.items()?.iter().position(|item| item.id() == HELP_SUBMENU_ID);
    match help_index {
        Some(index) => menu.insert(&settings_submenu, index)?,
        None => menu.append(&settings_submenu)?,
    }

    handle.manage(ThemeMenuState(Mutex::new(items)));
    handle.manage(AutoCheckUpdateMenuState(auto_check_update_item));

    Ok(menu)
}

fn set_checked_theme(app: &AppHandle, theme_id: &str) {
    if let Some(state) = app.try_state::<ThemeMenuState>() {
        let items = state.0.lock().unwrap();
        for (id, item) in items.iter() {
            let _ = item.set_checked(id == theme_id);
        }
    }
}

fn set_checked_auto_update(app: &AppHandle, enabled: bool) {
    if let Some(state) = app.try_state::<AutoCheckUpdateMenuState>() {
        let _ = state.0.set_checked(enabled);
    }
}

pub fn handle_menu_event(app: &AppHandle, event: MenuEvent) {
    let id = event.id().as_ref();

    if let Some(theme_id) = id.strip_prefix(THEME_MENU_ID_PREFIX) {
        set_checked_theme(app, theme_id);
        let _ = app.emit("theme-changed", theme_id.to_string());
        return;
    }

    if id == AUTO_CHECK_UPDATE_MENU_ID {
        if let Some(state) = app.try_state::<AutoCheckUpdateMenuState>() {
            // muda already flips the checkmark before dispatching this event
            // (see its Windows/macOS menu_selected handlers), so the current
            // checked state already reflects the click - just read and relay it.
            let enabled = state.0.is_checked().unwrap_or(true);
            let _ = app.emit("auto-check-update-changed", enabled);
        }
        return;
    }

    if id == CHECK_SELF_UPDATE_MENU_ID {
        let _ = app.emit("check-self-update-requested", "prod");
        return;
    }

    if id == CHECK_SELF_UPDATE_TEST_MENU_ID {
        let _ = app.emit("check-self-update-requested", "test");
    }
}

// Invoked by the frontend when the theme changes via the in-app selector,
// so the menu checkmarks stay in sync.
#[tauri::command]
pub fn set_theme(app: AppHandle, theme_id: String) {
    set_checked_theme(&app, &theme_id);
}

// Invoked by the frontend on load (and whenever the setting changes some
// other way) so the menu checkmark stays in sync.
#[tauri::command]
pub fn set_auto_check_update(app: AppHandle, enabled: bool) {
    set_checked_auto_update(&app, enabled);
}
