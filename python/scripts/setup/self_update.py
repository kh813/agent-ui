"""Self-update checker for agent-ui itself.

Unlike agent-deck's install_agent_ui.py (which pins to a specific known-good
upstream release and re-brands the binary under a different name), this
script updates agent-ui in place: it asks GitHub for whatever the *latest*
published release actually is, and swaps the currently-installed
agent-ui.app / agent-ui.exe (a sibling of python/ and config/ at the project
root — see the release workflow's zip-staging step) for the new one.

Reuses the atomic-swap safety pattern from install_agent_ui.py: download and
extract into a staging directory first, and only remove the existing install
once the replacement is verified in place, so a failed/interrupted download
never leaves the user with no agent-ui at all.

Since agent-ui may be the very process invoking this (e.g. via a skill run
from inside a live session), this script never touches the running binary's
open file — it replaces it on disk and asks the user to relaunch. It does
not attempt a hot in-place self-replace.

Usage:
  python3 self_update.py check    # print whether an update is available
  python3 self_update.py apply    # download and install the latest release
"""
import json
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REPO = "kh813/agent-ui"
_API_LATEST = f"https://api.github.com/repos/{_REPO}/releases/latest"

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _dest_name() -> str:
    return "agent-ui.exe" if sys.platform == "win32" else "agent-ui.app"


def _asset_name() -> str:
    return "agent-ui-win.zip" if sys.platform == "win32" else "agent-ui-mac.zip"


def _marker_path() -> Path:
    return PROJECT_ROOT / f"{_dest_name()}.version"


def _installed_tag() -> str:
    marker = _marker_path()
    return marker.read_text().strip() if marker.exists() else ""


def _fetch_latest_release() -> dict:
    req = urllib.request.Request(
        _API_LATEST, headers={"Accept": "application/vnd.github+json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check() -> tuple[bool, str, str]:
    """Return (update_available, installed_tag, latest_tag)."""
    release = _fetch_latest_release()
    latest_tag = release["tag_name"]
    installed_tag = _installed_tag()
    return (installed_tag != latest_tag, installed_tag, latest_tag)


def apply() -> None:
    release = _fetch_latest_release()
    latest_tag = release["tag_name"]
    installed_tag = _installed_tag()

    if installed_tag == latest_tag:
        print(f"  Already up to date: {_dest_name()} ({latest_tag})")
        return

    asset_name = _asset_name()
    asset = next(
        (a for a in release.get("assets", []) if a["name"] == asset_name), None
    )
    if asset is None:
        raise RuntimeError(
            f"Release {latest_tag} does not contain an asset named {asset_name}"
        )
    url = asset["browser_download_url"]

    print(f"  Updating agent-ui: {installed_tag or 'unknown'} -> {latest_tag}")
    print(f"  Downloading {url}...")

    dest = PROJECT_ROOT / _dest_name()
    upstream_name = "agent-ui.exe" if sys.platform == "win32" else "agent-ui.app"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        zip_path = tmp_path / asset_name
        subprocess.run(
            ["curl", "-fsSL", "--connect-timeout", "10", "--max-time", "120",
             url, "-o", str(zip_path)],
            check=True, stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW,
        )
        staging = tmp_path / "extracted"
        staging.mkdir()
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(staging)

        new_dest = staging / upstream_name
        if not new_dest.exists():
            raise RuntimeError(
                f"Downloaded archive from {url} did not contain {upstream_name}"
            )

        if sys.platform != "win32":
            subprocess.run(["xattr", "-cr", str(new_dest)], check=False, stdin=subprocess.DEVNULL)
            (new_dest / "Contents" / "MacOS" / "agent-ui").chmod(0o755)

        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        shutil.move(str(new_dest), str(dest))

    _marker_path().write_text(latest_tag)
    print(f"  agent-ui {latest_tag} installed to {dest}.")
    print("  Restart agent-ui to use the new version.")


def _usage():
    print("Usage: self_update.py [check|apply]")
    sys.exit(1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        available, installed, latest = check()
        if available:
            print(f"Update available: {installed or 'unknown'} -> {latest}")
        else:
            print(f"Already up to date: {latest}")
    elif cmd == "apply":
        apply()
    else:
        _usage()
