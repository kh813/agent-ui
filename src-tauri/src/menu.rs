use std::sync::Mutex;
use tauri::menu::{CheckMenuItem, IsMenuItem, Menu, MenuEvent, MenuItem, Submenu, HELP_SUBMENU_ID};
use tauri::{AppHandle, Emitter, Manager};

use crate::self_update::org_release_configured;

const THEME_MENU_ID_PREFIX: &str = "theme:";
const AUTO_CHECK_UPDATE_MENU_ID: &str = "settings:auto-check-update";
const UPDATE_GITHUB_MENU_ID: &str = "update:github";
const UPDATE_ORG_PROD_MENU_ID: &str = "update:org-prod";
const UPDATE_ORG_TEST_MENU_ID: &str = "update:org-test";

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
    let settings_submenu = Submenu::with_items(handle, "Settings", true, &[&auto_check_update_item])?;

    // Update submenu: an org-managed install (config.toml's [drive]
    // org_release_prod_file_id / org_release_test_file_id set -- see
    // package_release.py) should use its own controlled Drive channel
    // rather than bypass it via raw GitHub, so the plain GitHub item is
    // hidden whenever either org item is available. A plain OSS install
    // with no org config.toml at all gets just the GitHub item, which
    // works even fresh out of a ZIP with no config.toml present yet.
    let (org_prod_configured, org_test_configured) = org_release_configured();
    let update_submenu = if org_prod_configured || org_test_configured {
        let mut items: Vec<MenuItem<tauri::Wry>> = Vec::new();
        if org_prod_configured {
            items.push(MenuItem::with_id(
                handle, UPDATE_ORG_PROD_MENU_ID, "Update to Org Latest...", true, None::<&str>,
            )?);
        }
        if org_test_configured {
            items.push(MenuItem::with_id(
                handle, UPDATE_ORG_TEST_MENU_ID, "Update to Org Test...", true, None::<&str>,
            )?);
        }
        let refs: Vec<&dyn IsMenuItem<tauri::Wry>> =
            items.iter().map(|i| i as &dyn IsMenuItem<tauri::Wry>).collect();
        Submenu::with_items(handle, "Update", true, &refs)?
    } else {
        let github_item = MenuItem::with_id(
            handle, UPDATE_GITHUB_MENU_ID, "Update to GitHub Latest...", true, None::<&str>,
        )?;
        Submenu::with_items(handle, "Update", true, &[&github_item])?
    };

    // Place Theme/Update/Settings just before Help, matching where most apps put extra top-level menus.
    let help_index = menu.items()?.iter().position(|item| item.id() == HELP_SUBMENU_ID);
    match help_index {
        Some(index) => menu.insert(&theme_submenu, index)?,
        None => menu.append(&theme_submenu)?,
    }
    let help_index = menu.items()?.iter().position(|item| item.id() == HELP_SUBMENU_ID);
    match help_index {
        Some(index) => menu.insert(&update_submenu, index)?,
        None => menu.append(&update_submenu)?,
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

    if id == UPDATE_GITHUB_MENU_ID {
        let _ = app.emit("check-self-update-requested", "github");
        return;
    }

    if id == UPDATE_ORG_PROD_MENU_ID {
        let _ = app.emit("check-self-update-requested", "org-prod");
        return;
    }

    if id == UPDATE_ORG_TEST_MENU_ID {
        let _ = app.emit("check-self-update-requested", "org-test");
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
