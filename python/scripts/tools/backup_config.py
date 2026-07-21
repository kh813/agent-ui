#!/usr/bin/env python3
"""Back up this directory's org-private, gitignored files to Google Drive.

This project's own working directory doubles as both the public agent-deck
development environment (git-tracked) and an organization's private config
store (config.toml, client_secret_*.json, docs/ — all gitignored, since
they never belong on the public GitHub repo). None of that is recoverable
from git if this directory is ever lost, so this script zips it up and
uploads it to a Drive file the organization controls, overwriting the
previous backup in place (same pattern as the skill-catalog's own upload
flow — see skills_catalog.py).

Re-run this whenever config.toml, client_secret_*.json, or docs/ change, to
keep the backup current. A cron job or a manual habit both work; there's no
launch-time or scheduled hook for this by design, since these files change
rarely and a stale-by-a-few-days backup is not an emergency.

Usage:
  python3 python/scripts/tools/backup_config.py [<file_id>]

  <file_id>  Optional Drive file ID to upload to. Defaults to config.toml's
             [drive].config_backup_file_id.
"""
import sys
import os
import zipfile
import tempfile
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

# Paths (relative to PROJECT_ROOT) to include in the backup zip -- exactly
# the gitignored, org-private files a fresh clone of this repo won't have,
# but that are needed to keep doing admin/release work.
#
# python/skills-personal/ is included because it's the sole home for
# org-specific skill SOURCE (SKILL.md + bundled scripts) once authoring
# moves out of a git-tracked directory -- the Drive skill-catalog only
# preserves the last-*published* version of each skill, so unpublished
# local edits have no other backup at all.
_BACKUP_GLOBS = [
    "config.toml",
    "client_secret_*.json",
    "docs/**/*",
    "python/skills-personal/**/*",
]


def _reexec_with_venv():
    try:
        import googleapiclient  # noqa: F401
    except ImportError:
        if sys.platform == "win32":
            venv_python = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
        else:
            venv_python = PROJECT_ROOT / "venv" / "bin" / "python3"
        if not venv_python.exists():
            print("[ERROR] venv not found. Run setup first.")
            sys.exit(1)
        os.environ["PYTHONWARNINGS"] = "ignore"
        if sys.platform == "win32":
            import subprocess as _sp
            sys.exit(_sp.run([str(venv_python)] + sys.argv).returncode)
        else:
            os.execv(str(venv_python), [str(venv_python)] + sys.argv)


_reexec_with_venv()

sys.path.insert(0, str(PROJECT_ROOT / "python"))
from config import OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET, CONFIG_BACKUP_FILE_ID  # noqa: E402
from scripts.auth import run_auth_flow  # noqa: E402

CLIENT_CONFIG = {
    "installed": {
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}


def _get_service():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
            creds = run_auth_flow(flow)
        TOKEN_PATH.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _collect_files() -> list[Path]:
    seen = []
    for pattern in _BACKUP_GLOBS:
        for p in sorted(PROJECT_ROOT.glob(pattern)):
            if p.is_file() and p not in seen:
                seen.append(p)
    return seen


def main():
    file_id = sys.argv[1] if len(sys.argv) > 1 else CONFIG_BACKUP_FILE_ID
    if not file_id:
        print("[ERROR] config.toml に drive.config_backup_file_id が設定されていません。")
        print("[ERROR] Set drive.config_backup_file_id in config.toml, or pass a file ID as an argument.")
        sys.exit(1)

    files = _collect_files()
    if not files:
        print("[ERROR] バックアップ対象のファイルが見つかりませんでした。")
        print("[ERROR] No backup target files were found.")
        sys.exit(1)

    print("バックアップ対象 / Backing up:")
    for f in files:
        print(f"  + {f.relative_to(PROJECT_ROOT)}")

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "agent-deck-config.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                zf.write(f, f.relative_to(PROJECT_ROOT))

        size_kb = zip_path.stat().st_size / 1024
        print(f"アップロード中 / Uploading: agent-deck-config.zip ({size_kb:.1f} KB) ...")

        from googleapiclient.http import MediaFileUpload
        service = _get_service()
        media = MediaFileUpload(str(zip_path), mimetype="application/zip", resumable=True)
        service.files().update(
            fileId=file_id,
            media_body=media,
            supportsAllDrives=True,
        ).execute()

    print("✓ アップロード完了 / Upload complete")
    print(f"  https://drive.google.com/file/d/{file_id}/view")


if __name__ == "__main__":
    main()
