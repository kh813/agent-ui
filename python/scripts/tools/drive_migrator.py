#!/usr/bin/env python3
"""
Google Drive フォルダ移行ツール

Usage:
  python3 python/scripts/tools/drive_migrator.py scan <source_url> <dest_url> [--batch-size N]
  python3 python/scripts/tools/drive_migrator.py execute
  python3 python/scripts/tools/drive_migrator.py status
"""

import sys
import os
import re
import json
import time
from pathlib import Path
from datetime import datetime

SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]

SCOPES     = ["https://www.googleapis.com/auth/drive"]
TOKEN_PATH = Path.home() / ".gemini" / "agent_ui_library_token.json"
TASK_FILE  = PROJECT_ROOT / "tmp" / "migration_tasks.json"

FOLDER_MIME   = "application/vnd.google-apps.folder"
SHORTCUT_MIME = "application/vnd.google-apps.shortcut"

SLEEP_SEC         = 0.3   # seconds between API calls
CHECKPOINT_EVERY  = 50    # save progress every N files
DEFAULT_BATCH_SIZE = 1000  # files per execute session


# ── venv bootstrap ──────────────────────────────────────────────────────────

def _reexec_with_venv():
    try:
        import googleapiclient  # noqa: F401
    except ImportError:
        import subprocess as _sp
        venv_python = (
            PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
            if sys.platform == "win32"
            else PROJECT_ROOT / "venv" / "bin" / "python3"
        )
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
from scripts.auth import run_auth_flow                                 # noqa: E402
from scripts.logger import get_logger, log_startup                     # noqa: E402

_log = get_logger("drive_migrator")
log_startup(_log)

_USER_DOMAIN = USER_EMAIL.split("@")[-1] if USER_EMAIL and "@" in USER_EMAIL else ""

CLIENT_CONFIG = {
    "installed": {
        "client_id":     OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
        "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
        "token_uri":     "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}


# ── Auth ────────────────────────────────────────────────────────────────────

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
                _log.warning("token refresh failed: %s", e)
                creds = None
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
            creds = run_auth_flow(flow, login_hint=USER_EMAIL or None)
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds, cache_discovery=False)


# ── URL / ID parsing ─────────────────────────────────────────────────────────

def _parse_folder_id(url: str) -> str | None:
    url = url.strip()
    patterns = [
        r"drive\.google\.com/drive/(?:u/\d+/)?folders/([^/?#\s]+)",
        r"drive\.google\.com/drive/(?:u/\d+/)?shared-drives/([^/?#\s]+)",
        r"[?&]id=([^&\s]+)",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    # Plain ID
    if re.match(r"^[A-Za-z0-9_-]{25,}$", url):
        return url
    return None


# ── Rate-limited API wrapper ─────────────────────────────────────────────────

def _api(request, max_retries: int = 6):
    from googleapiclient.errors import HttpError
    wait = 1.0
    for attempt in range(max_retries):
        try:
            result = request.execute()
            time.sleep(SLEEP_SEC)
            return result
        except HttpError as e:
            if e.resp.status in (429, 500, 503):
                print(f"  [WAIT] {e.resp.status} — {wait:.0f}s 待機中 / waiting...")
                time.sleep(wait)
                wait = min(wait * 2, 64)
            else:
                raise
    raise RuntimeError(f"API call failed after {max_retries} retries")


# ── Task file ────────────────────────────────────────────────────────────────

def _load() -> dict:
    if not TASK_FILE.exists():
        print(f"[ERROR] タスクファイルが見つかりません: {TASK_FILE.relative_to(PROJECT_ROOT)}")
        print("        先に 'scan' を実行してください。")
        sys.exit(1)
    return json.loads(TASK_FILE.read_text(encoding="utf-8"))


def _save(data: dict):
    TASK_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASK_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Pre-flight permission check ──────────────────────────────────────────────

def _check_permissions(service, source_id: str, dest_id: str) -> list[str]:
    """Check access rights on source and destination folders.

    Returns a list of warning strings (empty = no issues found).
    Prints results to stdout.
    """
    from googleapiclient.errors import HttpError

    warnings: list[str] = []

    def _get_folder(fid: str, label: str) -> dict | None:
        try:
            return _api(service.files().get(
                fileId=fid,
                fields="id,name,driveId,capabilities(canAddChildren,canListChildren,"
                       "canMoveChildrenOutOfDrive,canMoveItemOutOfDrive)",
                supportsAllDrives=True,
            ))
        except HttpError as e:
            warnings.append(f"{label}: アクセスできません ({e.resp.status}) — {e}")
            return None

    print("アクセス権を確認中... / Checking permissions...")

    src = _get_folder(source_id, "移動元")
    dst = _get_folder(dest_id,   "移動先")

    if src:
        caps = src.get("capabilities", {})
        if caps.get("canListChildren") is False:
            warnings.append("移動元フォルダを一覧できません (canListChildren=false)。"
                            "閲覧権限がない可能性があります。")
        if caps.get("canMoveChildrenOutOfDrive") is False:
            warnings.append("移動元フォルダから他のドライブへのファイル移動が制限されています "
                            "(canMoveChildrenOutOfDrive=false)。"
                            "多くのファイルでコピー+削除が必要になります。")
        if src.get("driveId"):
            print(f"  移動元は共有ドライブ内のフォルダです (driveId: {src['driveId']})")

    if dst:
        caps = dst.get("capabilities", {})
        if caps.get("canAddChildren") is False:
            warnings.append("移動先フォルダへのファイル追加権限がありません (canAddChildren=false)。"
                            "移行を実行できません。")
        if dst.get("driveId"):
            print(f"  移動先は共有ドライブ内のフォルダです (driveId: {dst['driveId']})")

    if warnings:
        print()
        for w in warnings:
            print(f"  ⚠ {w}")
    else:
        print("  OK")
    print()

    return warnings


# ── Per-file migration prediction ────────────────────────────────────────────

_PREDICT_FIELDS = (
    "nextPageToken,"
    "files(id,name,mimeType,"
    "owners(emailAddress),"
    "capabilities(canMoveItemOutOfDrive,canCopy,canDelete,canTrash))"
)


def _predict_method(caps: dict, owners: list) -> str:
    """Predict how a file will be migrated based on its capabilities and ownership.

    Returns one of: "move" | "copy+delete" | "copy-only" | "will_fail"
    """
    can_move   = caps.get("canMoveItemOutOfDrive")   # None = unknown
    can_copy   = caps.get("canCopy",  True)
    can_delete = caps.get("canDelete", False) or caps.get("canTrash", False)

    external = _USER_DOMAIN and any(
        o.get("emailAddress", "").split("@")[-1] != _USER_DOMAIN
        for o in owners
        if o.get("emailAddress")
    )

    if not can_copy and can_move is False:
        return "will_fail"
    if not can_copy:
        return "will_fail"
    if can_move is True and not external:
        return "move"
    if can_delete:
        return "copy+delete"
    return "copy-only"


# ── Batch assignment ─────────────────────────────────────────────────────────

def _assign_batches(tasks: list[dict], batch_size: int) -> int:
    """Assign batch numbers to tasks in-place. Returns total number of file batches.

    Folders → batch 0  (created once, before any file batch)
    Files + shortcuts → batch 1, 2, 3... (batch_size items each)
    """
    file_idx = 0
    for task in tasks:
        if task["type"] == "folder":
            task["batch"] = 0
        else:
            task["batch"] = (file_idx // batch_size) + 1
            file_idx += 1
    return (file_idx + batch_size - 1) // batch_size if file_idx > 0 else 0


# ── Phase 1: scan ────────────────────────────────────────────────────────────

def cmd_scan(source_url: str, dest_url: str, batch_size: int = DEFAULT_BATCH_SIZE):
    source_id = _parse_folder_id(source_url)
    dest_id   = _parse_folder_id(dest_url)

    if not source_id:
        print(f"[ERROR] 移動元フォルダIDを取得できません: {source_url}")
        sys.exit(1)
    if not dest_id:
        print(f"[ERROR] 移動先フォルダIDを取得できません: {dest_url}")
        sys.exit(1)

    service = _get_service()

    def _name(fid):
        try:
            return _api(service.files().get(fileId=fid, fields="name", supportsAllDrives=True))["name"]
        except Exception:
            return fid

    source_name = _name(source_id)
    dest_name   = _name(dest_id)
    print(f"移動元 / Source : {source_name}  ({source_id})")
    print(f"移動先 / Dest   : {dest_name}  ({dest_id})")
    print()

    perm_warnings = _check_permissions(service, source_id, dest_id)

    print("スキャン中... / Scanning...")

    tasks: list[dict] = []
    folder_map = {source_id: dest_id}   # source_folder_id → dest_folder_id

    # BFS: (source_folder_id, relative_path)
    queue = [(source_id, "")]
    scanned = 0

    while queue:
        cur_id, cur_path = queue.pop(0)
        scanned += 1
        if scanned > 1:
            print(f"  フォルダ #{scanned}: {cur_path}")

        page_token = None
        while True:
            res = _api(service.files().list(
                q=f"'{cur_id}' in parents and trashed=false",
                fields=_PREDICT_FIELDS,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                pageSize=200,
                pageToken=page_token,
                orderBy="name",
            ))
            for f in res.get("files", []):
                rel  = f"{cur_path}/{f['name']}" if cur_path else f["name"]
                mime = f["mimeType"]
                caps = f.get("capabilities", {})
                owners = f.get("owners", [])

                if mime == SHORTCUT_MIME:
                    tasks.append({
                        "id": f["id"], "name": f["name"], "mime_type": mime,
                        "type": "shortcut", "path": rel,
                        "source_parent_id": cur_id,
                        "status": "pending_trash", "method": "trash",
                        "prediction": "trash",
                        "dest_id": None, "error": None,
                    })
                elif mime == FOLDER_MIME:
                    folder_caps = f.get("capabilities", {})
                    if folder_caps.get("canMoveItemOutOfDrive") is True:
                        # Folder can be moved as a unit — skip recursion into contents
                        tasks.append({
                            "id": f["id"], "name": f["name"], "mime_type": mime,
                            "type": "folder", "path": rel,
                            "source_parent_id": cur_id,
                            "status": "pending", "method": "move_folder",
                            "prediction": "move_folder",
                            "dest_id": None, "error": None,
                        })
                    else:
                        tasks.append({
                            "id": f["id"], "name": f["name"], "mime_type": mime,
                            "type": "folder", "path": rel,
                            "source_parent_id": cur_id,
                            "status": "pending", "method": "create_folder",
                            "prediction": "create_folder",
                            "dest_id": None, "error": None,
                        })
                        queue.append((f["id"], rel))
                else:
                    prediction = _predict_method(caps, owners)
                    tasks.append({
                        "id": f["id"], "name": f["name"], "mime_type": mime,
                        "type": "file", "path": rel,
                        "source_parent_id": cur_id,
                        "status": "pending", "method": None,
                        "prediction": prediction,
                        "dest_id": None, "error": None,
                    })

            page_token = res.get("nextPageToken")
            if not page_token:
                break

    n_folders_move   = sum(1 for t in tasks if t["type"] == "folder" and t.get("method") == "move_folder")
    n_folders_create = sum(1 for t in tasks if t["type"] == "folder" and t.get("method") == "create_folder")
    n_folders   = n_folders_move + n_folders_create
    n_files     = sum(1 for t in tasks if t["type"] == "file")
    n_shortcuts = sum(1 for t in tasks if t["type"] == "shortcut")

    file_tasks = [t for t in tasks if t["type"] == "file"]
    pred_count = {
        "move":        sum(1 for t in file_tasks if t["prediction"] == "move"),
        "copy+delete": sum(1 for t in file_tasks if t["prediction"] == "copy+delete"),
        "copy-only":   sum(1 for t in file_tasks if t["prediction"] == "copy-only"),
        "will_fail":   sum(1 for t in file_tasks if t["prediction"] == "will_fail"),
    }

    total_batches = _assign_batches(tasks, batch_size)

    data = {
        "source_root_id":   source_id,
        "source_root_name": source_name,
        "dest_root_id":     dest_id,
        "dest_root_name":   dest_name,
        "scanned_at":       datetime.now().isoformat(timespec="seconds"),
        "perm_warnings":    perm_warnings,
        "batch_size":       batch_size,
        "total_batches":    total_batches,
        "folder_map":       folder_map,
        "tasks":            tasks,
    }
    _save(data)

    print()
    print("── スキャン完了 / Scan complete ──────────────────────────────────")
    if n_folders_move:
        print(f"  フォルダ（一括移動）  : {n_folders_move}  ← 配下ファイルを含む一括移動")
    if n_folders_create:
        print(f"  フォルダ（個別作成）  : {n_folders_create}")
    print(f"  ファイル      / Files     : {n_files}")
    print(f"  ショートカット / Shortcuts : {n_shortcuts}  ← ゴミ箱へ移動")
    print(f"  合計          / Total     : {len(tasks)}")
    if n_folders_move:
        print(f"  ※ 一括移動フォルダの配下ファイルは上記カウントに含まれません")
    print()
    print("移行方法の予測 / Predicted migration method:")
    print(f"  移動         (move)        : {pred_count['move']} 件")
    print(f"  コピー+削除  (copy+delete) : {pred_count['copy+delete']} 件"
          + ("  ← 組織外オーナー等" if pred_count["copy+delete"] else ""))
    if pred_count["copy-only"]:
        print(f"  コピーのみ   (copy-only)   : {pred_count['copy-only']} 件"
              "  ⚠ 元ファイルを削除できない可能性")
    if pred_count["will_fail"]:
        print(f"  失敗見込み   (will fail)   : {pred_count['will_fail']} 件"
              "  ✗ 閲覧のみ権限 — コピー不可")

    print()
    if total_batches <= 1:
        print("バッチ計画 / Batch plan: 1回の実行で完了できます")
    else:
        est_min = int(batch_size * SLEEP_SEC / 60) + 1
        print(f"バッチ計画 / Batch plan  ({batch_size:,} ファイル/バッチ, 約{est_min}分/回):")
        for b in range(1, total_batches + 1):
            b_files = sum(1 for t in tasks if t.get("batch") == b and t["type"] == "file")
            b_sc    = sum(1 for t in tasks if t.get("batch") == b and t["type"] == "shortcut")
            extras  = []
            if b == 1 and n_folders_create:
                extras.append(f"フォルダ作成 {n_folders_create} 件（初回のみ）")
            if b == 1 and n_folders_move:
                extras.append(f"フォルダ一括移動 {n_folders_move} 件（初回のみ）")
            if b_sc:
                extras.append(f"ショートカット {b_sc} 件")
            note = f"  + {', '.join(extras)}" if extras else ""
            print(f"  バッチ {b:2d}/{total_batches}: {b_files:5,} ファイル{note}")
        print(f"  → execute を {total_batches} 回実行すれば完了")

    if perm_warnings:
        print()
        print("⚠ フォルダ権限の警告 / Folder permission warnings:")
        for w in perm_warnings:
            print(f"  - {w}")

    blockers = [w for w in perm_warnings if "canAddChildren=false" in w]
    if blockers or pred_count["will_fail"] == n_files:
        print()
        print("✗ 移行を実行できない可能性があります。上記の警告を確認してください。")
    elif pred_count["will_fail"] > 0 or pred_count["copy-only"] > 0 or perm_warnings:
        print()
        print("⚠ 一部のファイルで問題が発生する可能性があります。execute 後に結果を確認してください。")

    print()
    print(f"タスクファイル: {TASK_FILE.relative_to(PROJECT_ROOT)}")


# ── Phase 2: execute ─────────────────────────────────────────────────────────

def cmd_execute():
    from googleapiclient.errors import HttpError

    data          = _load()
    tasks         = data["tasks"]
    folder_map    = data["folder_map"]
    total_batches = data.get("total_batches", 0)
    batch_size    = data.get("batch_size", DEFAULT_BATCH_SIZE)

    # Determine which batch to run next
    batched = total_batches > 1
    if batched:
        open_batches = sorted({
            t["batch"] for t in tasks
            if t.get("batch", 0) > 0
            and t["status"] in ("pending", "pending_trash")
        })
        current_batch = open_batches[0] if open_batches else None
    else:
        current_batch = None

    pending_folders = [t for t in tasks if t["type"] == "folder" and t["status"] == "pending"]

    if batched and current_batch is not None:
        pending_files = [t for t in tasks
                         if t["type"] == "file"
                         and t["status"] == "pending"
                         and t.get("batch") == current_batch]
        pending_trash = [t for t in tasks
                         if t["type"] == "shortcut"
                         and t["status"] == "pending_trash"
                         and t.get("batch") == current_batch]
    else:
        pending_files = [t for t in tasks if t["type"] == "file"     and t["status"] == "pending"]
        pending_trash = [t for t in tasks if t["type"] == "shortcut" and t["status"] == "pending_trash"]

    already_done = sum(1 for t in tasks if t["status"] in ("done", "trashed"))
    grand_total  = len(tasks)

    if not any([pending_folders, pending_files, pending_trash]):
        if batched and current_batch is None:
            print(f"全 {total_batches} バッチ完了！移行がすべて終わりました。")
        else:
            print("すべてのタスクが完了しています。/ All tasks are already complete.")
        cmd_status()
        return

    if batched and current_batch is not None:
        print(f"バッチ {current_batch}/{total_batches} を実行します "
              f"({len(pending_files):,} ファイル"
              + (f" + {len(pending_trash)} ショートカット" if pending_trash else "")
              + (f" + フォルダ作成 {len(pending_folders)} 件" if pending_folders else "")
              + ")")

    service = _get_service()
    counts  = {"done": 0, "move_folder": 0, "copy+delete": 0, "copy-only": 0, "failed": 0}

    def _prog():
        done = already_done + counts["done"] + counts["failed"]
        return f"[{done}/{grand_total}]"

    # ── Step 1: process destination folders (top-down) ──────────────────────
    if pending_folders:
        n_pf_move   = sum(1 for t in pending_folders if t.get("method") == "move_folder")
        n_pf_create = sum(1 for t in pending_folders if t.get("method") == "create_folder")
        parts = []
        if n_pf_create: parts.append(f"作成 {n_pf_create}")
        if n_pf_move:   parts.append(f"一括移動 {n_pf_move}")
        print(f"── フォルダ / Folders ({', '.join(parts)}) ──")
        pending_folders.sort(key=lambda t: t["path"].count("/"))

        for task in pending_folders:
            dest_parent = folder_map.get(task["source_parent_id"])
            if not dest_parent:
                task["status"] = "failed"
                task["error"]  = f"parent not resolved: {task['source_parent_id']}"
                counts["failed"] += 1
                print(f"  {_prog()} [FAIL] {task['path']}")
                _save(data)
                continue

            if task.get("method") == "move_folder":
                try:
                    _api(service.files().update(
                        fileId=task["id"],
                        addParents=dest_parent,
                        removeParents=task["source_parent_id"],
                        fields="id",
                        supportsAllDrives=True,
                    ))
                    task["dest_id"] = task["id"]
                    task["status"]  = "done"
                    counts["done"]        += 1
                    counts["move_folder"] += 1
                    print(f"  {_prog()} [フォルダ一括移動] {task['path']}（配下一式）")
                except Exception as e:
                    task["status"] = "failed"
                    task["error"]  = str(e)
                    counts["failed"] += 1
                    print(f"  {_prog()} [FAIL] {task['path']} — {e}")
                    print(f"         ※ scan を再実行するとフォルダ内ファイルを個別処理できます")
            else:
                try:
                    res = _api(service.files().create(
                        body={"name": task["name"], "mimeType": FOLDER_MIME, "parents": [dest_parent]},
                        fields="id",
                        supportsAllDrives=True,
                    ))
                    task["dest_id"] = res["id"]
                    task["status"]  = "done"
                    folder_map[task["id"]] = res["id"]
                    data["folder_map"] = folder_map
                    counts["done"] += 1
                    print(f"  {_prog()} [フォルダ作成] {task['path']}")
                except Exception as e:
                    task["status"] = "failed"
                    task["error"]  = str(e)
                    counts["failed"] += 1
                    print(f"  {_prog()} [FAIL] {task['path']} — {e}")

            _save(data)

    # ── Step 2: move / copy+delete files ────────────────────────────────────
    if pending_files:
        print()
        print(f"── ファイル移動 / Moving {len(pending_files)} files ──")

        for i, task in enumerate(pending_files, 1):
            dest_parent = folder_map.get(task["source_parent_id"])
            if not dest_parent:
                task["status"] = "failed"
                task["error"]  = f"parent not resolved: {task['source_parent_id']}"
                counts["failed"] += 1
                print(f"  {_prog()} [FAIL] {task['path']}")
                _save(data)
                continue

            # Try move
            moved = False
            try:
                _api(service.files().update(
                    fileId=task["id"],
                    addParents=dest_parent,
                    removeParents=task["source_parent_id"],
                    fields="id",
                    supportsAllDrives=True,
                ))
                task["status"]  = "done"
                task["method"]  = "move"
                task["dest_id"] = task["id"]
                moved = True
                counts["done"] += 1
                print(f"  {_prog()} [移動] {task['path']}")
            except HttpError as e:
                if e.resp.status not in (403, 500):
                    task["status"] = "failed"
                    task["error"]  = f"move: {e}"
                    counts["failed"] += 1
                    print(f"  {_prog()} [FAIL] {task['path']} — {e}")
                    _save(data)
                    continue
                # Fall through to copy+delete

            if not moved:
                # Copy
                try:
                    copy_res = _api(service.files().copy(
                        fileId=task["id"],
                        body={"name": task["name"], "parents": [dest_parent]},
                        fields="id",
                        supportsAllDrives=True,
                    ))
                    task["dest_id"] = copy_res["id"]
                except Exception as e2:
                    task["status"] = "failed"
                    task["error"]  = f"copy: {e2}"
                    counts["failed"] += 1
                    print(f"  {_prog()} [FAIL] {task['path']} — {e2}")
                    _save(data)
                    continue

                # Delete original (try permanent delete, fall back to trash)
                deleted = False
                for del_fn in [
                    lambda: _api(service.files().delete(fileId=task["id"], supportsAllDrives=True)),
                    lambda: _api(service.files().update(fileId=task["id"], body={"trashed": True},
                                                        fields="id", supportsAllDrives=True)),
                ]:
                    try:
                        del_fn()
                        deleted = True
                        break
                    except Exception:
                        pass

                task["status"] = "done"
                if deleted:
                    task["method"] = "copy+delete"
                    counts["copy+delete"] += 1
                    print(f"  {_prog()} [コピー+削除] {task['path']}")
                else:
                    task["method"] = "copy-only"
                    task["error"]  = "original could not be deleted"
                    counts["copy-only"] += 1
                    print(f"  {_prog()} [コピーのみ ⚠] {task['path']}  ← 元ファイル削除不可")
                counts["done"] += 1

            _save(data)

            if i % CHECKPOINT_EVERY == 0:
                print(f"  ... {i}/{len(pending_files)} 件処理済み。2秒待機中...")
                time.sleep(2)

    # ── Step 3: trash shortcuts ──────────────────────────────────────────────
    if pending_trash:
        print()
        print(f"── ショートカットをゴミ箱へ / Trashing {len(pending_trash)} shortcuts ──")

        for task in pending_trash:
            try:
                _api(service.files().update(
                    fileId=task["id"],
                    body={"trashed": True},
                    fields="id",
                    supportsAllDrives=True,
                ))
                task["status"] = "trashed"
                counts["done"] += 1
                print(f"  {_prog()} [ゴミ箱] {task['path']}")
            except Exception as e:
                task["error"]  = str(e)
                counts["failed"] += 1
                print(f"  {_prog()} [FAIL] {task['path']} — {e}")
            _save(data)

    # ── Summary ──────────────────────────────────────────────────────────────
    print()
    print("═" * 60)
    print("完了 / Migration complete")
    print("═" * 60)
    total_done   = counts["done"]
    n_trashed    = sum(1 for t in tasks if t["status"] == "trashed")
    n_file_moved = total_done - counts["move_folder"] - counts["copy+delete"] - counts["copy-only"] - n_trashed
    print(f"  完了       : {total_done}")
    if counts["move_folder"]:
        print(f"    フォルダ一括移動: {counts['move_folder']}（配下ファイル含む）")
    print(f"    移動      : {n_file_moved}")
    print(f"    コピー+削除: {counts['copy+delete']}")
    if counts["copy-only"]:
        print(f"    コピーのみ : {counts['copy-only']}  ← 元ファイルが残っています")
    print(f"    ゴミ箱    : {n_trashed}")
    print(f"  失敗       : {counts['failed']}")

    copy_only = [t for t in tasks if t.get("method") == "copy-only"]
    if copy_only:
        print()
        print("⚠ 元ファイルを削除できなかったファイル（手動で確認してください）:")
        for t in copy_only:
            print(f"  - {t['path']}")

    failed = [t for t in tasks if t["status"] == "failed"]
    if failed:
        print()
        print("✗ 失敗したファイル:")
        for t in failed:
            print(f"  - {t['path']}: {t.get('error', '')}")

    trashed = [t for t in tasks if t["status"] == "trashed"]
    if trashed:
        print()
        print(f"🗑 ゴミ箱に移動したショートカット ({len(trashed)} 件):")
        for t in trashed:
            print(f"  - {t['path']}")

    # Batch progress report
    if batched and current_batch is not None:
        remaining_batches = sorted({
            t["batch"] for t in tasks
            if t.get("batch", 0) > 0
            and t["status"] in ("pending", "pending_trash")
        })
        print()
        print("─" * 60)
        if remaining_batches:
            next_b  = remaining_batches[0]
            n_left  = sum(1 for t in tasks
                          if t.get("batch", 0) > 0
                          and t["status"] in ("pending", "pending_trash"))
            est_min = int(batch_size * SLEEP_SEC / 60) + 1
            print(f"✓ バッチ {current_batch}/{total_batches} 完了")
            print(f"  残り {len(remaining_batches)} バッチ / {n_left:,} ファイル")
            print(f"  次回 (バッチ {next_b}) の実行コマンド（目安 約{est_min}分）:")
            print(f"  venv/bin/python3 python/scripts/tools/drive_migrator.py execute"
                  " >> tmp/migration_log.txt 2>&1")
        else:
            print(f"🎉 全 {total_batches} バッチ完了！移行がすべて終わりました。")


# ── Status ───────────────────────────────────────────────────────────────────

def cmd_status():
    data  = _load()
    tasks = data["tasks"]

    by_status: dict[str, list] = {}
    for t in tasks:
        by_status.setdefault(t["status"], []).append(t)

    print(f"移動元 / Source : {data.get('source_root_name', data['source_root_id'])}")
    print(f"移動先 / Dest   : {data.get('dest_root_name', data['dest_root_id'])}")
    print(f"スキャン日時    : {data.get('scanned_at', '?')}")
    print()

    for status, label in [
        ("done",          "done (移動済み)"),
        ("trashed",       "trashed (ゴミ箱)"),
        ("pending",       "pending (未処理)"),
        ("pending_trash", "pending_trash (ショートカット待ち)"),
        ("failed",        "failed (失敗)"),
    ]:
        n = len(by_status.get(status, []))
        if n:
            print(f"  {label:30s}: {n}")
    print(f"  {'合計 / Total':30s}: {len(tasks)}")

    failed = by_status.get("failed", [])
    if failed:
        print()
        print("失敗したファイル:")
        for t in failed:
            print(f"  - {t['path']}: {t.get('error', '')}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0]
    if cmd == "scan":
        if len(args) < 3:
            print("Usage: drive_migrator.py scan <source_url> <dest_url> [--batch-size N]")
            sys.exit(1)
        batch_size = DEFAULT_BATCH_SIZE
        if "--batch-size" in args:
            idx = args.index("--batch-size")
            try:
                batch_size = int(args[idx + 1])
            except (IndexError, ValueError):
                print("[ERROR] --batch-size には整数を指定してください")
                sys.exit(1)
        cmd_scan(args[1], args[2], batch_size=batch_size)
    elif cmd == "execute":
        cmd_execute()
    elif cmd == "status":
        cmd_status()
    else:
        print(f"不明なコマンド: {cmd}")
        print("コマンド: scan | execute | status")
        sys.exit(1)


if __name__ == "__main__":
    main()
