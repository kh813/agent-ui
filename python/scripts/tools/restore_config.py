#!/usr/bin/env python3
"""Restore this directory's org-private, gitignored files from a backup ZIP
(the counterpart to backup_config.py — see that script's docstring for what
gets backed up and why).

Two ways to run this:

1. On a machine that ALREADY has a working config.toml (e.g. re-syncing
   docs/ after a local edit was lost, or refreshing from the latest
   backup): just run with no arguments. This downloads the current backup
   ZIP via the Drive API, using the file ID in config.toml's own
   [drive].config_backup_file_id.

     python3 python/scripts/tools/restore_config.py

2. On a genuinely fresh machine with NO config.toml yet: the Drive-API
   mode above can't work (config.toml holds the very OAuth client_id/
   secret this script would need to call the Drive API — a chicken-and-
   egg problem). Instead, download agent-deck-config.zip manually via a
   browser (using the org's existing Drive access — no OAuth setup
   needed for a plain browser download), then point this script at the
   downloaded file:

     python3 python/scripts/tools/restore_config.py --zip ~/Downloads/agent-deck-config.zip

Either way, any local file this would overwrite is renamed aside first
(<name>.bak-<timestamp>) rather than silently clobbered, in case there are
uncommitted local edits newer than the backup.

Usage:
  python3 python/scripts/tools/restore_config.py [--zip <path>] [<file_id>]
"""
import sys
import os
import time
import zipfile
import tempfile
import argparse
from pathlib import Path

# Windows pipe (agy.exe's pty etc.) makes stdout fall back to CP932/CP1252,
# corrupting or crashing outright (UnicodeEncodeError) on this file's
# non-ASCII output. See python/tests/test_windows_utf8.py for the incident
# history.
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass

SCRIPT_DIR   = Path(__file__).resolve().parent   # python/scripts/tools
PROJECT_ROOT = SCRIPT_DIR.parents[2]              # project root

SCOPES     = ["https://www.googleapis.com/auth/drive"]
TOKEN_PATH = Path.home() / ".gemini" / "agent_deck_library_token.json"


def _extract_with_backup(zip_path: Path) -> None:
    """Extract zip_path into PROJECT_ROOT, renaming any existing file this
    would overwrite aside first (never silently clobbers)."""
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if not n.endswith("/")]
        for name in names:
            dest = PROJECT_ROOT / name
            if dest.exists():
                stamp = time.strftime("%Y%m%d%H%M%S")
                backup = dest.with_name(f"{dest.name}.bak-{stamp}")
                dest.rename(backup)
                print(f"  existing {name} -> {backup.name}")
        zf.extractall(PROJECT_ROOT)
        for name in names:
            print(f"  restored: {name}")


def _restore_from_local_zip(zip_path: Path) -> None:
    if not zip_path.is_file():
        print(f"[ERROR] ファイルが見つかりません / File not found: {zip_path}")
        sys.exit(1)
    print(f"復元中 / Restoring from: {zip_path}")
    _extract_with_backup(zip_path)
    print("✓ 復元完了 / Restore complete")


def _reexec_with_venv():
    try:
        import googleapiclient  # noqa: F401
    except ImportError:
        if sys.platform == "win32":
            venv_python = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
        else:
            venv_python = PROJECT_ROOT / "venv" / "bin" / "python3"
        if not venv_python.exists():
            print("[ERROR] venv not found. Run setup first, or use --zip with a manually downloaded backup.")
            sys.exit(1)
        os.environ["PYTHONWARNINGS"] = "ignore"
        if sys.platform == "win32":
            import subprocess as _sp
            sys.exit(_sp.run([str(venv_python)] + sys.argv).returncode)
        else:
            os.execv(str(venv_python), [str(venv_python)] + sys.argv)


def _restore_via_drive_api(file_id: str) -> None:
    _reexec_with_venv()

    sys.path.insert(0, str(PROJECT_ROOT / "python"))
    from config import OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET, CONFIG_BACKUP_FILE_ID  # noqa: E402
    from scripts.auth import run_auth_flow  # noqa: E402

    file_id = file_id or CONFIG_BACKUP_FILE_ID
    if not file_id:
        print("[ERROR] config.toml に drive.config_backup_file_id が設定されていません。")
        print("[ERROR] Set drive.config_backup_file_id in config.toml, or pass a file ID as an argument.")
        sys.exit(1)

    client_config = {
        "installed": {
            "client_id": OAUTH_CLIENT_ID,
            "client_secret": OAUTH_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    import io

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
            creds = run_auth_flow(flow)
        TOKEN_PATH.write_text(creds.to_json())
    service = build("drive", "v3", credentials=creds, cache_discovery=False)

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "agent-deck-config.zip"
        print(f"ダウンロード中 / Downloading from https://drive.google.com/file/d/{file_id}/view ...")
        request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
        fh = io.FileIO(zip_path, "wb")
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        fh.close()

        _extract_with_backup(zip_path)

    print("✓ 復元完了 / Restore complete")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--zip", type=Path, default=None,
                        help="Restore from an already-downloaded local ZIP instead of fetching via the Drive API.")
    parser.add_argument("file_id", nargs="?", default=None,
                        help="Drive file ID (Drive-API mode only). Defaults to config.toml's [drive].config_backup_file_id.")
    args = parser.parse_args()

    if args.zip:
        _restore_from_local_zip(args.zip)
    else:
        _restore_via_drive_api(args.file_id)


if __name__ == "__main__":
    main()
