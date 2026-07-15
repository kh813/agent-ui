#!/usr/bin/env python3
"""
TeamSpirit attendance script
Usage:
  python3 routine.py clockin           # Clock in
  python3 routine.py clockout          # Clock out
  python3 routine.py clockin --dry-run # Page check only (no punch)
"""

import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
from common import get_chrome_context, save_screenshot, check_element, find_in_frames

_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR.parents[2] / "python"))
from config import SALESFORCE_URL  # noqa: E402

BUTTON = {
    "clockin":  {"id": "#btnStInput", "label": "clock-in"},
    "clockout": {"id": "#btnEtInput", "label": "clock-out"},
}


def print_help():
    print("""
Usage:
  python3 routine.py clockin  [--dry-run]
  python3 routine.py clockout [--dry-run]
""")


def clock_action(page, action: str, dry_run: bool):
    btn = BUTTON[action]
    label = btn["label"]
    selector = btn["id"]

    print(f"{'[DRY-RUN] ' if dry_run else ''}Navigating to TeamSpirit...")
    page.goto(SALESFORCE_URL)

    login_required = False
    try:
        page.wait_for_selector("button:has-text('Google Workspace')", timeout=5000)
        login_required = True
        page.click("button:has-text('Google Workspace')")
    except Exception:
        print("Login screen skipped (already logged in).")

    if login_required:
        print()
        print("━" * 54)
        print("【Manual login required / 手動ログインが必要です】")
        print("  Chrome is open. Please log in to TeamSpirit")
        print("  with your Google account.")
        print("  The script will continue automatically.")
        print()
        print("  Chrome が開いています。TeamSpirit に")
        print("  Google アカウントでログインしてください。")
        print("  ログインが完了すると自動で続行します。")
        print("━" * 54)
        print()

    page.wait_for_url("**/lightning/**", timeout=120000)
    print("Login confirmed.")

    if dry_run:
        found = check_element(page, selector, f"{label} button")
        save_screenshot(page, f"dryrun_{action}")
        print(f"\n[DRY-RUN] Summary")
        print(f"  Page: {page.url}")
        print(f"  {label} button ({selector}): {'found' if found else 'not found'}")
        print(f"  * No punch recorded.")
    else:
        print(f"Looking for '{label}' button...")

        # Search across all frames including iframes, waiting for button to become active.
        # The button starts disabled until the DB responds, so we keep retrying.
        frame, el = None, None
        is_disabled = True
        for _ in range(30):  # wait up to 30 seconds
            frame, el = find_in_frames(page, selector)
            if el:
                is_disabled = frame.evaluate("el => el.disabled", el)
                if not is_disabled:
                    break
            page.wait_for_timeout(1000)

        if el is None:
            print(f"Error: '{label}' button not found. The page structure may have changed.")
            return

        if is_disabled:
            print(f"'{label}' button is grayed out. You may have already punched.")
            return

        frame.click(selector)
        print(f"Clicked '{label}'.")
        try:
            page.wait_for_selector("text=OK", state="visible", timeout=5000)
            page.click("text=OK")
            print("Confirmation dialog dismissed.")
        except Exception:
            pass
        print(f"Done: {label}")


if __name__ == "__main__":
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    positional = [a for a in args if not a.startswith("--")]

    if len(positional) != 1 or positional[0] not in BUTTON:
        print_help()
        sys.exit(1)

    action = positional[0]

    with sync_playwright() as p:
        context, page = get_chrome_context(p, lang='en-US')
        try:
            clock_action(page, action, dry_run)
        finally:
            context.close()
