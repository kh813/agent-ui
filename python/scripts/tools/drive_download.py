#!/usr/bin/env python3
"""
Google Drive ダウンロードスクリプト

Usage:
  python3 python/scripts/tools/drive_download.py URL [--overwrite] [--skip] [--dry-run]

  URL        Google Drive ファイルまたはフォルダの URL
  --overwrite  既存ファイルを上書き
  --skip       既存ファイルをスキップして新規のみダウンロード
  --dry-run    実際にはダウンロードせず結果を表示

Exit codes:
  0  正常終了
  1  エラーあり
  2  競合ファイルあり（--overwrite / --skip 未指定時）
"""

import sys
import os
import re
import io
import argparse
from pathlib import Path

SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]

DEST_ROOT = PROJECT_ROOT / "files"

SCOPES     = ["https://www.googleapis.com/auth/drive.readonly"]
TOKEN_PATH = Path.home() / ".gemini" / "agent_ui_library_token.json"

GOOGLE_NATIVE_MIMETYPES = {
    "application/vnd.google-apps.document",
    "application/vnd.google-apps.spreadsheet",
    "application/vnd.google-apps.presentation",
    "application/vnd.google-apps.form",
    "application/vnd.google-apps.drawing",
    "application/vnd.google-apps.script",
    "application/vnd.google-apps.site",
}
FOLDER_MIMETYPE = "application/vnd.google-apps.folder"


# ── venv / auth ────────────────────────────────────────────────

def _reexec_with_venv():
    try:
        import googleapiclient  # noqa: F401
    except ImportError:
        import subprocess as _sp
        if sys.platform == "win32":
            venv_python = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
        else:
            venv_python = PROJECT_ROOT / "venv" / "bin" / "python3"
        if not venv_python.exists():
            print("[ERROR] venv が見つかりません。先に setup を実行してください。")
            sys.exit(1)
        if Path(sys.prefix).resolve() == (PROJECT_ROOT / "venv").resolve():
            if os.environ.get("_VENV_PKGS_INSTALLED"):
                print("[ERROR] Required packages could not be loaded after installation.")
                sys.exit(1)
            _sp.run([str(venv_python), "-m", "pip", "install", "-q", "--no-cache-dir",
                     "google-auth", "google-auth-oauthlib",
                     "google-api-python-client"], check=True)
            os.environ["_VENV_PKGS_INSTALLED"] = "1"
        os.environ["PYTHONWARNINGS"] = "ignore"
        if sys.platform == "win32":
            sys.exit(_sp.run([str(venv_python)] + sys.argv).returncode)
        else:
            os.execv(str(venv_python), [str(venv_python)] + sys.argv)


_reexec_with_venv()

sys.path.insert(0, str(PROJECT_ROOT / "python"))
from config import OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET, USER_EMAIL  # noqa: E402
from scripts.auth import run_auth_flow  # noqa: E402
from scripts.logger import get_logger, log_startup  # noqa: E402

_log = get_logger("drive_download")
log_startup(_log)

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

    # Reuse existing token (shared with drive_upload.py)
    all_scopes = SCOPES + ["https://www.googleapis.com/auth/drive"]
    creds = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), all_scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                _log.warning("token refresh failed, re-authenticating: %s", e)
                creds = None
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, all_scopes)
            creds = run_auth_flow(flow, login_hint=USER_EMAIL or None)
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds, cache_discovery=False)


# ── URL parsing ────────────────────────────────────────────────

def _parse_url(url: str) -> tuple:
    """Returns (resource_id, resource_type).
    resource_type: 'file' | 'folder' | 'google_native' | None
    """
    # Google Workspace native editors
    for pattern in [
        r"docs\.google\.com/document/d/([^/?#]+)",
        r"docs\.google\.com/spreadsheets/d/([^/?#]+)",
        r"docs\.google\.com/presentation/d/([^/?#]+)",
        r"docs\.google\.com/forms/d/([^/?#]+)",
        r"docs\.google\.com/drawings/d/([^/?#]+)",
    ]:
        m = re.search(pattern, url)
        if m:
            return m.group(1), "google_native"

    # Folder
    m = re.search(r"/folders/([^/?#\s]+)", url)
    if m:
        return m.group(1), "folder"

    # File  /file/d/ID
    m = re.search(r"/file/d/([^/?#\s]+)", url)
    if m:
        return m.group(1), "file"

    # Fallback: ?id=ID or &id=ID
    m = re.search(r"[?&]id=([^&\s]+)", url)
    if m:
        return m.group(1), "file"

    return None, None


# ── Drive helpers ──────────────────────────────────────────────

def _get_file_metadata(service, file_id: str) -> dict:
    return service.files().get(
        fileId=file_id,
        fields="id, name, mimeType, size",
        supportsAllDrives=True,
    ).execute()


def _scan_folder(service, folder_id: str, rel_prefix: str = "") -> list:
    """Recursively collect all items in a Drive folder.
    Returns list of dicts: {rel_path, file_id, size_kb, mime_type, is_native}
    """
    items = []
    page_token = None
    while True:
        res = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id, name, mimeType, size)",
            supportsAllDrives=True, includeItemsFromAllDrives=True,
            pageSize=200, pageToken=page_token,
        ).execute()
        for f in res.get("files", []):
            rel = rel_prefix + f["name"]
            if f["mimeType"] == FOLDER_MIMETYPE:
                items.extend(_scan_folder(service, f["id"], rel + "/"))
            elif f["mimeType"] in GOOGLE_NATIVE_MIMETYPES:
                items.append({
                    "rel_path": rel,
                    "file_id": f["id"],
                    "size_kb": 0,
                    "mime_type": f["mimeType"],
                    "is_native": True,
                })
            else:
                items.append({
                    "rel_path": rel,
                    "file_id": f["id"],
                    "size_kb": int(f.get("size", 0)) // 1024,
                    "mime_type": f["mimeType"],
                    "is_native": False,
                })
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return items


def _scan_conflicts(items: list, dest_dir: Path) -> list:
    """Returns list of (rel_path,) that already exist locally."""
    return [it["rel_path"] for it in items
            if not it["is_native"] and (dest_dir / it["rel_path"]).exists()]


def _download_file(service, file_id: str, dest_path: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    with open(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


# ── Process ────────────────────────────────────────────────────

def _process(service, items: list, dest_dir: Path,
             overwrite: bool, skip: bool, dry_run: bool) -> tuple:
    """Download items to dest_dir. Returns (downloaded, skipped, failed)."""
    downloaded = skipped = failed = 0

    for it in items:
        dest_path = dest_dir / it["rel_path"]
        size_label = f" ({it['size_kb']} KB)" if it["size_kb"] else ""

        if it["is_native"]:
            kind = it["mime_type"].split(".")[-1].replace("google-apps-", "")
            print(f"  ⊘ {it['rel_path']}  → Google {kind}（スキップ / skipped）")
            skipped += 1
            continue

        is_conflict = dest_path.exists()
        if is_conflict and skip:
            print(f"  - {it['rel_path']}{size_label}  → スキップ / Skipped")
            skipped += 1
            continue

        verb = "上書き / Overwrite" if is_conflict else "新規 / New"

        if dry_run:
            marker = "⚠" if is_conflict else "✓"
            print(f"  {marker} {it['rel_path']}{size_label}  → {verb}")
            downloaded += 1
        else:
            try:
                _download_file(service, it["file_id"], dest_path)
                print(f"  ✓ {it['rel_path']}{size_label}  → {verb}")
                downloaded += 1
            except Exception as e:
                print(f"  ✗ {it['rel_path']}  [FAILED] {e}")
                failed += 1

    return downloaded, skipped, failed


# ── Entry point ────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Google Drive からファイル・フォルダをダウンロードします"
    )
    parser.add_argument("url", metavar="URL",
                        help="Google Drive ファイルまたはフォルダの URL")
    parser.add_argument("--overwrite", action="store_true",
                        help="既存ファイルを上書き")
    parser.add_argument("--skip", action="store_true",
                        help="既存ファイルをスキップ、新規のみダウンロード")
    parser.add_argument("--dry-run", action="store_true",
                        help="実際にはダウンロードせず結果を表示")
    args = parser.parse_args()

    if args.overwrite and args.skip:
        print("[ERROR] --overwrite と --skip は同時に指定できません。")
        sys.exit(1)

    resource_id, resource_type = _parse_url(args.url)

    if resource_type is None:
        print("[ERROR] URL から Drive ID を抽出できませんでした。")
        print("  URL 例: https://drive.google.com/drive/folders/FOLDER_ID")
        print("       or https://drive.google.com/file/d/FILE_ID/view")
        sys.exit(1)

    if resource_type == "google_native":
        print("[ERROR] このURLは Google ドキュメント / スプレッドシート / スライドです。")
        print("  Google ネイティブ形式はダウンロードに対応していません。")
        print("  Google Docs/Sheets/Slides cannot be downloaded directly.")
        sys.exit(1)

    service = _get_service()
    prefix  = "[DRY-RUN] " if args.dry_run else ""

    DEST_ROOT.mkdir(exist_ok=True)

    if resource_type == "file":
        meta = _get_file_metadata(service, resource_id)
        if meta["mimeType"] in GOOGLE_NATIVE_MIMETYPES:
            print("[ERROR] このファイルは Google ネイティブ形式のため対応していません。")
            sys.exit(1)

        dest_path = DEST_ROOT / meta["name"]
        size_kb   = int(meta.get("size", 0)) // 1024
        is_conflict = dest_path.exists()

        print(f"{prefix}ダウンロード先 / Destination: files/")
        print()

        if not args.overwrite and not args.skip and not args.dry_run and is_conflict:
            print("⚠ 以下のファイルはすでに存在します / Already exists locally:")
            print(f"  ・{meta['name']}  ({size_kb} KB)")
            print()
            print("  --overwrite : 上書きしてダウンロード / Overwrite existing file")
            print("  --skip      : スキップ（既存ファイルを保持）/ Skip (keep existing)")
            sys.exit(2)

        items = [{
            "rel_path": meta["name"],
            "file_id": resource_id,
            "size_kb": size_kb,
            "mime_type": meta["mimeType"],
            "is_native": False,
        }]
        dest_dir = DEST_ROOT

    else:  # folder
        meta = _get_file_metadata(service, resource_id)
        folder_name = meta["name"]
        dest_dir    = DEST_ROOT / folder_name

        print(f"{prefix}フォルダ / Folder: {folder_name}")
        print(f"{prefix}ダウンロード先 / Destination: files/{folder_name}/")
        print(f"  (folder ID: {resource_id})")
        print()
        print("ファイル一覧を取得中 / Scanning folder contents...")

        items = _scan_folder(service, resource_id)
        if not items:
            print("[INFO] フォルダが空です。/ Folder is empty.")
            sys.exit(0)

        # 競合チェック
        if not args.overwrite and not args.skip and not args.dry_run:
            conflicts = _scan_conflicts(items, dest_dir)
            if conflicts:
                print()
                print("⚠ 以下のファイルはすでに存在します / Already exist locally:")
                for path in conflicts:
                    print(f"  ・{path}")
                print()
                print("  --overwrite : 上書きしてダウンロード / Overwrite existing files")
                print("  --skip      : 既存ファイルをスキップ、新規のみダウンロード")
                print("               Skip existing, download new files only")
                sys.exit(2)

        print()

    downloaded, skipped, failed = _process(
        service, items, dest_dir,
        args.overwrite, args.skip, args.dry_run,
    )

    print()
    if args.dry_run:
        downloadable = sum(1 for it in items if not it["is_native"])
        print(f"[DRY-RUN] {downloadable} 件が対象（実際のダウンロードは行っていません）")
        print(f"[DRY-RUN] {downloadable} item(s) would be downloaded — no changes made")
    else:
        parts = []
        if downloaded: parts.append(f"{downloaded} 件ダウンロード完了")
        if skipped:    parts.append(f"{skipped} 件スキップ")
        if failed:     parts.append(f"{failed} 件エラー")
        print("完了 / Done: " + "、".join(parts))
        if failed:
            sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _log.error("unhandled exception", exc_info=True)
        raise
