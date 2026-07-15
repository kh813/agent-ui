#!/usr/bin/env python3
"""
Google Drive アップロードスクリプト

Usage:
  python3 python/scripts/tools/drive_upload.py PATH [PATH ...] --folder FOLDER_ID
                                             [--overwrite] [--skip] [--dry-run]

  PATH         アップロードするファイルまたはフォルダのパス（複数指定可）
  --folder     アップロード先 Google Drive フォルダ ID
  --overwrite  既存ファイルを上書き
  --skip       既存ファイルをスキップして新規のみアップロード
  --dry-run    実際にはアップロードせず結果を表示
"""

import sys
import os
import mimetypes
from pathlib import Path

SCRIPT_DIR   = Path(__file__).resolve().parent   # python/scripts/tools
PROJECT_ROOT = SCRIPT_DIR.parents[2]             # project root

SCOPES     = ["https://www.googleapis.com/auth/drive"]
TOKEN_PATH = Path.home() / ".gemini" / "agent_ui_library_token.json"


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

_log = get_logger("drive_upload")
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


# ── Auth ───────────────────────────────────────────────────────────

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
            try:
                creds.refresh(Request())
            except Exception as e:
                _log.warning("token refresh failed, re-authenticating: %s", e)
                creds = None
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
            creds = run_auth_flow(flow, login_hint=USER_EMAIL or None)
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds, cache_discovery=False)


# ── Drive helpers ──────────────────────────────────────────────────

def _get_folder_name(service, folder_id: str) -> str:
    if folder_id == "root":
        return "My Drive（ルート）"
    try:
        return service.files().get(
            fileId=folder_id, fields="name", supportsAllDrives=True
        ).execute()["name"]
    except Exception:
        return folder_id


def _list_children(service, folder_id: str) -> tuple:
    """→ (files: {name: {id, modified}}, folders: {name: folder_id})"""
    files, folders, page_token = {}, {}, None
    while True:
        res = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="nextPageToken, files(id, name, mimeType, modifiedTime)",
            supportsAllDrives=True, includeItemsFromAllDrives=True,
            pageSize=200, pageToken=page_token,
        ).execute()
        for f in res.get("files", []):
            if f["mimeType"] == "application/vnd.google-apps.folder":
                folders[f["name"]] = f["id"]
            else:
                files[f["name"]] = {"id": f["id"], "modified": f["modifiedTime"][:10]}
        page_token = res.get("nextPageToken")
        if not page_token:
            break
    return files, folders


def _get_or_create_folder(service, name: str, parent_id: str) -> str:
    """Drive 上のフォルダを返す。なければ作成する。"""
    res = service.files().list(
        q=(f"'{parent_id}' in parents and name='{name}'"
           " and mimeType='application/vnd.google-apps.folder' and trashed=false"),
        fields="files(id)", supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    files = res.get("files", [])
    if files:
        return files[0]["id"]
    res = service.files().create(
        body={"name": name,
              "mimeType": "application/vnd.google-apps.folder",
              "parents": [parent_id]},
        fields="id", supportsAllDrives=True,
    ).execute()
    return res["id"]


def _upload_file(service, local_path: Path, parent_id: str, existing_id: str = None):
    from googleapiclient.http import MediaFileUpload
    mime = mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"
    media = MediaFileUpload(str(local_path), mimetype=mime, resumable=True)
    if existing_id:
        service.files().update(
            fileId=existing_id, media_body=media, supportsAllDrives=True,
        ).execute()
    else:
        service.files().create(
            body={"name": local_path.name, "parents": [parent_id]},
            media_body=media, fields="id", supportsAllDrives=True,
        ).execute()


# ── Conflict scan ──────────────────────────────────────────────────

def _scan_conflicts(service, local_items: list, drive_folder_id: str,
                    prefix: str = "") -> list:
    """
    Drive と競合するファイルを再帰的に検出する。
    drive_folder_id が None（新規フォルダ）の場合は競合なし。
    Returns: [(display_path, drive_modified_date), ...]
    """
    if drive_folder_id is None:
        return []
    existing_files, existing_folders = _list_children(service, drive_folder_id)
    conflicts = []
    for item in local_items:
        if item.name.startswith("."):
            continue
        if item.is_file():
            if item.name in existing_files:
                conflicts.append(
                    (prefix + item.name, existing_files[item.name]["modified"])
                )
        elif item.is_dir():
            sub_id = existing_folders.get(item.name)
            conflicts.extend(
                _scan_conflicts(service, list(item.iterdir()),
                                sub_id, prefix + item.name + "/")
            )
    return conflicts


# ── Upload / dry-run ───────────────────────────────────────────────

def _process(service, local_items: list, drive_folder_id: str,
             overwrite: bool, skip: bool, dry_run: bool,
             indent: str = "") -> tuple:
    """
    ファイル・フォルダを再帰的に処理する（dry_run または実アップロード）。
    drive_folder_id が None の場合は新規フォルダ内（全アイテムが新規扱い）。
    Returns: (uploaded, skipped, failed)
    """
    if drive_folder_id is not None:
        existing_files, existing_folders = _list_children(service, drive_folder_id)
    else:
        existing_files, existing_folders = {}, {}

    uploaded = skipped = failed = 0

    for item in sorted(local_items, key=lambda x: (x.is_dir(), x.name)):
        if item.name.startswith("."):
            continue

        if item.is_file():
            is_conflict = item.name in existing_files
            existing_id = existing_files[item.name]["id"] if is_conflict else None
            size_kb     = item.stat().st_size // 1024
            verb        = "上書き / Overwrite" if is_conflict else "新規 / New"
            disp        = indent + item.name

            if is_conflict and skip:
                print(f"  - {disp}  ({size_kb} KB)  → スキップ / Skipped")
                skipped += 1
                continue

            if dry_run:
                marker = "⚠" if is_conflict else "✓"
                print(f"  {marker} {disp}  ({size_kb} KB)  → {verb}")
                uploaded += 1
            else:
                try:
                    _upload_file(service, item, drive_folder_id, existing_id)
                    print(f"  ✓ {disp}  ({size_kb} KB)  → {verb}")
                    uploaded += 1
                except Exception as e:
                    print(f"  ✗ {disp}  [FAILED] {e}")
                    failed += 1

        elif item.is_dir():
            sub_existing_id = existing_folders.get(item.name)
            is_new          = sub_existing_id is None
            marker          = "📁" if is_new else "📂"
            label           = "新規フォルダ / New folder" if is_new else "既存フォルダ / Existing folder"
            print(f"  {marker} {indent}{item.name}/  → {label}")

            if dry_run:
                sub_id = sub_existing_id  # None for new folders → all items treated as new
            else:
                sub_id = sub_existing_id or _get_or_create_folder(
                    service, item.name, drive_folder_id
                )

            u, s, f = _process(
                service, list(item.iterdir()),
                sub_id, overwrite, skip, dry_run, indent + "  "
            )
            uploaded += u; skipped += s; failed += f

    return uploaded, skipped, failed


# ── Entry point ────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="指定ファイル・フォルダを Google Drive にアップロードします"
    )
    parser.add_argument("paths", nargs="+", metavar="PATH",
                        help="アップロードするファイルまたはフォルダのパス（複数指定可）")
    parser.add_argument("--folder", required=True, metavar="FOLDER_ID",
                        help="アップロード先 Google Drive フォルダ ID")
    parser.add_argument("--overwrite", action="store_true",
                        help="既存ファイルを上書き")
    parser.add_argument("--skip", action="store_true",
                        help="既存ファイルをスキップ、新規のみアップロード")
    parser.add_argument("--dry-run", action="store_true",
                        help="実際にはアップロードせず結果を表示")
    args = parser.parse_args()

    if args.overwrite and args.skip:
        print("[ERROR] --overwrite と --skip は同時に指定できません。")
        sys.exit(1)

    targets = []
    for p in args.paths:
        path = Path(p)
        if not path.exists():
            print(f"[ERROR] パスが見つかりません / Path not found: {p}")
            sys.exit(1)
        targets.append(path)

    service     = _get_service()
    folder_name = _get_folder_name(service, args.folder)
    prefix      = "[DRY-RUN] " if args.dry_run else ""

    print(f"{prefix}アップロード先 / Destination: {folder_name}")
    print(f"  (folder ID: {args.folder})")
    print()

    # 競合チェック（--overwrite / --skip 未指定 かつ dry-run でない場合）
    if not args.overwrite and not args.skip and not args.dry_run:
        conflicts = _scan_conflicts(service, targets, args.folder)
        if conflicts:
            print("⚠ 以下のファイルはすでに Drive に存在します / Already exist on Drive:")
            for path, modified in conflicts:
                print(f"  ・{path}  (Drive 上の更新日 / Modified: {modified})")
            print()
            print("  --overwrite : 上書きしてアップロード / Overwrite existing files")
            print("  --skip      : 既存ファイルをスキップ、新規のみアップロード")
            print("               Skip existing, upload new files only")
            sys.exit(2)

    uploaded, skipped, failed = _process(
        service, targets, args.folder,
        args.overwrite, args.skip, args.dry_run,
    )

    print()
    if args.dry_run:
        print(f"[DRY-RUN] {uploaded} 件が対象（実際のアップロードは行っていません）")
        print(f"[DRY-RUN] {uploaded} item(s) would be processed — no upload performed")
    else:
        parts = []
        if uploaded: parts.append(f"{uploaded} 件アップロード完了")
        if skipped:  parts.append(f"{skipped} 件スキップ")
        if failed:   parts.append(f"{failed} 件エラー")
        print("完了 / Done: " + "、".join(parts))
        if failed:
            sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _log.error("unhandled exception", exc_info=True)
        raise
