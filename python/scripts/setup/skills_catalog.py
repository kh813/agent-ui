"""Skill Catalog — Google Drive の共有スキルカタログ操作ツール。

Usage:
  python3 skills_catalog.py list
  python3 skills_catalog.py update-index
  python3 skills_catalog.py list-local
  python3 skills_catalog.py info <name|owner/name>
  python3 skills_catalog.py download <name|owner/name>
  python3 skills_catalog.py upload <skill_name>
  python3 skills_catalog.py delete <name|owner/name>
  python3 skills_catalog.py change-owner <name|owner/name> <new_email>
  python3 skills_catalog.py whoami
"""
import sys
import io
import os
import subprocess
from pathlib import Path

# Re-exec with venv Python if google packages are not available.
def _reexec_with_venv():
    try:
        import googleapiclient  # noqa: F401
    except ImportError:
        import subprocess as _sp
        script_dir = Path(__file__).resolve().parent
        project_root = script_dir.parents[2]
        if sys.platform == "win32":
            venv_python = project_root / "venv" / "Scripts" / "python.exe"
            pip_exe     = project_root / "venv" / "Scripts" / "pip.exe"
        else:
            venv_python = project_root / "venv" / "bin" / "python3"
            pip_exe     = project_root / "venv" / "bin" / "pip"
        if not venv_python.exists():
            print("[ERROR] venv not found. Please run setup first.")
            sys.exit(1)
        # Install missing packages if already on venv Python, then always re-exec
        # (sys.prefix check is reliable; sys.executable.resolve() is not — on Mac both
        #  system and venv Python may resolve to the same Homebrew binary via symlinks)
        if Path(sys.prefix).resolve() == (project_root / "venv").resolve():
            if os.environ.get("_VENV_PKGS_INSTALLED"):
                print("[ERROR] Required packages could not be loaded after installation.")
                sys.exit(1)
            print("  依存パッケージをインストール中 / Installing required packages...")
            _sp.run([str(pip_exe), "install", "-q", "--no-cache-dir",
                     "google-auth", "google-auth-oauthlib", "google-api-python-client"],
                    check=True)
            os.environ["_VENV_PKGS_INSTALLED"] = "1"
        # Re-exec with venv Python (first invocation, or after in-place install)
        os.environ["PYTHONWARNINGS"] = "ignore"
        if sys.platform == "win32":
            result = _sp.run([str(venv_python)] + sys.argv)
            sys.exit(result.returncode)
        else:
            os.execv(str(venv_python), [str(venv_python)] + sys.argv)

_reexec_with_venv()

# ============================================================
# Configuration
# ============================================================
SCRIPT_DIR   = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "python"))
from config import (  # noqa: E402
    OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET,
    CATALOG_FOLDER_ID, CATALOG_URL, CATALOG_FILE_ID, CONFIG_PATH,
    USER_EMAIL,
)
from scripts.auth import run_auth_flow  # noqa: E402
SCOPES    = ["https://www.googleapis.com/auth/drive"]
TOKEN_PATH = Path.home() / ".gemini" / "agent_ui_library_token.json"
# ============================================================

CLIENT_CONFIG = {
    "installed": {
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}

# Personal skill layer: catalog import/share reads and writes here, since
# imported/shared skills are per-installation, not the bundled skill set.
SKILLS_SRC        = PROJECT_ROOT / "python" / "skills-personal"
# `list-local` additionally shows the bundled layer.
COMMON_SKILL_ROOTS = [PROJECT_ROOT / "python" / "skills"]
INDEX_PATH        = PROJECT_ROOT / "python" / "skills" / "skill-catalog" / "catalog-index.md"
CATALOG_FILE_NAME = "skill-catalog.md"  # Drive ライブラリフォルダ直下の共有カタログ


# ── Auth & service ────────────────────────────────────────────

def _get_credentials():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

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

    return creds


def _get_service():
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=_get_credentials(), cache_discovery=False)


def _current_email(service) -> str:
    return service.about().get(fields="user").execute()["user"]["emailAddress"]


def _owner_prefix(email: str) -> str:
    return email.split("@")[0]


# ── Drive helpers ─────────────────────────────────────────────

def _list_owner_folders(service) -> dict:
    """Return {owner_name: folder_id} for all owner subfolders."""
    res = service.files().list(
        q=(f"'{CATALOG_FOLDER_ID}' in parents"
           " and mimeType='application/vnd.google-apps.folder'"
           " and trashed=false"),
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        pageSize=200,
    ).execute()
    return {f["name"]: f["id"] for f in res.get("files", [])}


def _list_md_in_folder(service, folder_id: str) -> list:
    """Return [{id, name, modifiedTime}] for .md files in a folder."""
    res = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id, name, modifiedTime)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        pageSize=200,
    ).execute()
    return [f for f in res.get("files", []) if f["name"].endswith(".md")]


def _get_file_content(service, file_id: str) -> str:
    from googleapiclient.http import MediaIoBaseDownload
    req = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue().decode("utf-8")


def _get_or_create_owner_folder(service, owner_name: str) -> str:
    folders = _list_owner_folders(service)
    if owner_name in folders:
        return folders[owner_name]
    res = service.files().create(
        body={
            "name": owner_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [CATALOG_FOLDER_ID],
        },
        fields="id",
        supportsAllDrives=True,
    ).execute()
    return res["id"]


def _find_skill(service, name_or_path: str) -> list:
    """
    Find skills matching name_or_path ('skill-name' or 'owner/skill-name').
    Returns list of {owner, name, file_id, modified}.
    """
    if "/" in name_or_path:
        owner, skill_name = name_or_path.split("/", 1)
        folders = _list_owner_folders(service)
        if owner not in folders:
            return []
        filename = skill_name + ".md"
        return [
            {"owner": owner, "name": skill_name,
             "file_id": f["id"], "modified": f["modifiedTime"][:10]}
            for f in _list_md_in_folder(service, folders[owner])
            if f["name"] == filename
        ]
    else:
        skill_name = name_or_path
        filename = skill_name + ".md"
        folders = _list_owner_folders(service)
        matches = []
        for owner, folder_id in folders.items():
            for f in _list_md_in_folder(service, folder_id):
                if f["name"] == filename:
                    matches.append({
                        "owner": owner, "name": skill_name,
                        "file_id": f["id"], "modified": f["modifiedTime"][:10],
                    })
        return matches


def _require_single_match(matches: list, query: str) -> dict:
    if not matches:
        print(f"[ERROR] スキルが見つかりません / Skill not found: {query}")
        sys.exit(1)
    if len(matches) > 1:
        print(f"複数のスキルが見つかりました / Multiple skills found for '{query}':")
        for m in matches:
            print(f"  {m['owner']}/{m['name']}  ({m['modified']})")
        print("\nオーナー付きで指定してください / Specify with owner, e.g.:")
        print(f"  ... {matches[0]['owner']}/{matches[0]['name']}")
        sys.exit(2)
    return matches[0]


# ── Frontmatter helpers ───────────────────────────────────────

def _parse_frontmatter(content: str) -> dict:
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}
    meta = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()
    return meta


def _update_frontmatter(content: str, updates: dict) -> str:
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        fm = ["---"] + [f"{k}: {v}" for k, v in updates.items()] + ["---", ""]
        return "\n".join(fm) + content

    end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), -1)
    if end == -1:
        return content

    existing_keys, new_lines = set(), [lines[0]]
    for line in lines[1:end]:
        if ":" in line:
            key = line.partition(":")[0].strip()
            existing_keys.add(key)
            if key in updates:
                new_lines.append(f"{key}: {updates[key]}")
                continue
        new_lines.append(line)
    for key, val in updates.items():
        if key not in existing_keys:
            new_lines.append(f"{key}: {val}")
    new_lines.append(lines[end])
    new_lines.extend(lines[end + 1:])
    return "\n".join(new_lines)


def _upload_content(service, folder_id: str, filename: str,
                    content: str, existing_file_id: str = None) -> str:
    from googleapiclient.http import MediaIoBaseUpload
    media = MediaIoBaseUpload(
        io.BytesIO(content.encode("utf-8")),
        mimetype="text/plain",
        resumable=False,
    )
    if existing_file_id:
        service.files().update(
            fileId=existing_file_id,
            media_body=media,
            supportsAllDrives=True,
        ).execute()
        return existing_file_id
    else:
        res = service.files().create(
            body={"name": filename, "parents": [folder_id]},
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        ).execute()
        return res["id"]


# ── Shared Drive catalog (skill-catalog.md in library root) ──

def _find_catalog_file_id(service) -> str:
    """Drive ライブラリフォルダ直下の skill-catalog.md の file_id を返す。なければ None。
    config.toml に catalog_file_id が設定されている場合はそれを優先使用する。"""
    if CATALOG_FILE_ID:
        return CATALOG_FILE_ID
    res = service.files().list(
        q=(f"'{CATALOG_FOLDER_ID}' in parents"
           f" and name='{CATALOG_FILE_NAME}'"
           " and trashed=false"),
        fields="files(id)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
        pageSize=5,
    ).execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None


def _update_config_catalog_file_id(new_id: str) -> None:
    """config.toml の catalog_file_id を新しい値で更新する。"""
    import re
    text = CONFIG_PATH.read_text(encoding="utf-8")
    new_text, n = re.subn(
        r'^(catalog_file_id\s*=\s*)"[^"]*"',
        rf'\1"{new_id}"',
        text,
        flags=re.MULTILINE,
    )
    if n == 0:
        # キーがまだなければ catalog_url 行の直後に追加
        new_text = re.sub(
            r'(catalog_url\s*=\s*"[^"]*"\n)',
            rf'\1catalog_file_id   = "{new_id}"\n',
            text,
        )
    if new_text != text:
        CONFIG_PATH.write_text(new_text, encoding="utf-8")


def _push_catalog_to_drive(service) -> None:
    """ローカルの catalog-index.md を Drive の skill-catalog.md に同期する。
    catalog_file_id が指すファイルが削除されていた場合は自動的に再作成し、
    config.toml の catalog_file_id を更新する。"""
    from googleapiclient.errors import HttpError
    if not INDEX_PATH.exists():
        return
    content = INDEX_PATH.read_text(encoding="utf-8")
    existing_id = _find_catalog_file_id(service)
    try:
        _upload_content(service, CATALOG_FOLDER_ID, CATALOG_FILE_NAME, content, existing_id)
    except HttpError as e:
        if e.resp.status != 404 or not existing_id:
            raise
        # 設定済み ID が無効（ファイルが削除されていた） → 新規作成して config.toml を更新
        print("  [WARN] カタログファイルが見つかりません。新規作成します。")
        print("  [WARN] Catalog file not found. Recreating...")
        new_id = _upload_content(service, CATALOG_FOLDER_ID, CATALOG_FILE_NAME, content, None)
        _update_config_catalog_file_id(new_id)
        print(f"  [OK] 新しいカタログを作成しました (ID: {new_id})")
        print(f"  [OK] Catalog recreated (ID: {new_id})")
        print(f"  [INFO] config.toml の catalog_file_id を更新しました。")
        print(f"  [INFO] 次回 ZIP 配布前に config/config.toml.template も同じ ID に更新してください。")
        print(f"  [INFO] config.toml updated. Remember to update config/config.toml.template before the next ZIP distribution.")
        return
    print(f"  [OK] カタログを Drive に同期しました / Catalog synced to Drive")


def _pull_catalog_from_drive(service) -> list:
    """Drive の skill-catalog.md を取得してローカルキャッシュに書き込む。
    catalog_file_id が指すファイルが削除されていた場合はフォルダ内を名前で再検索する。
    ファイルが存在しない場合は None を返す。"""
    from googleapiclient.errors import HttpError
    catalog_id = _find_catalog_file_id(service)
    if not catalog_id:
        return None
    try:
        content = _get_file_content(service, catalog_id)
    except HttpError as e:
        if e.resp.status != 404:
            raise
        # 設定済み ID が無効 → フォルダ内をフォールバック検索
        if not CATALOG_FILE_ID:
            return None
        res = service.files().list(
            q=(f"'{CATALOG_FOLDER_ID}' in parents"
               f" and name='{CATALOG_FILE_NAME}'"
               " and trashed=false"),
            fields="files(id)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=5,
        ).execute()
        files = res.get("files", [])
        if not files:
            return None
        content = _get_file_content(service, files[0]["id"])
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(content, encoding="utf-8")
    return _read_index()


# ── Library index (local cache) ──────────────────────────────

def _write_index(skills: list):
    """スキル一覧を catalog-index.md に書き込む。"""
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "<!-- このファイルは自動生成されます / Auto-generated — do not edit manually -->",
        f"<!-- Updated: {ts} -->",
        "",
        "| スキル名 / Name | オーナー / Owner | 更新日 / Updated | 説明 / Description |",
        "|---|---|---|---|",
    ]
    for s in sorted(skills, key=lambda x: (x["name"], x["owner"])):
        # | はテーブル構文を壊すため全角に置換
        desc = s.get("description", "").replace("|", "｜")
        lines.append(f"| {s['name']} | {s['owner']} | {s['modified']} | {desc} |")
    lines.append("")
    INDEX_PATH.write_text("\n".join(lines), encoding="utf-8")


def _read_index():
    """catalog-index.md からスキル一覧を読み込む。存在しない場合は None を返す。"""
    if not INDEX_PATH.exists():
        return None
    skills = []
    for line in INDEX_PATH.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| "):
            continue
        # 先頭と末尾の | を除いてから分割（description に | が含まれないことを前提）
        parts = [p.strip() for p in line[1:-1].split("|")]
        if len(parts) < 3:
            continue
        name = parts[0]
        # skip header and separator rows
        if name.startswith("スキル名") or set(name) <= set("-"):
            continue
        owner    = parts[1] if len(parts) > 1 else ""
        modified = parts[2] if len(parts) > 2 else ""
        desc     = parts[3] if len(parts) > 3 else ""
        skills.append({"name": name, "owner": owner,
                       "modified": modified, "description": desc})
    return skills


def _index_add(skill_name: str, owner: str):
    """インデックスにエントリを追加または更新する。説明はローカル SKILL.md から取得。"""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    skill_md = SKILLS_SRC / skill_name / "SKILL.md"
    desc = ""
    if skill_md.exists():
        desc = _parse_frontmatter(skill_md.read_text(encoding="utf-8")).get("description", "")
    skills = _read_index() or []
    skills = [s for s in skills
              if not (s["name"] == skill_name and s["owner"] == owner)]
    skills.append({"name": skill_name, "owner": owner,
                   "modified": today, "description": desc})
    _write_index(skills)


def _index_remove(skill_name: str, owner: str):
    """インデックスからエントリを削除する。"""
    skills = _read_index() or []
    skills = [s for s in skills
              if not (s["name"] == skill_name and s["owner"] == owner)]
    _write_index(skills)


def _index_change_owner(skill_name: str, old_owner: str, new_owner: str):
    """インデックスのオーナーを変更する。説明は既存エントリから引き継ぐ。"""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    skills = _read_index() or []
    existing = next((s for s in skills
                     if s["name"] == skill_name and s["owner"] == old_owner), {})
    desc = existing.get("description", "")
    skills = [s for s in skills
              if not (s["name"] == skill_name and s["owner"] == old_owner)]
    skills.append({"name": skill_name, "owner": new_owner,
                   "modified": today, "description": desc})
    _write_index(skills)


# ── Commands ──────────────────────────────────────────────────

def cmd_list_local():
    """List locally installed skills grouped into Default / My skill / Catalog sections."""
    # Determine current user's owner prefix without a Drive API call.
    if USER_EMAIL:
        me = _owner_prefix(USER_EMAIL)
    else:
        try:
            me = os.getlogin()
        except Exception:
            me = ""

    commons, mine, catalog = [], [], []

    all_roots = COMMON_SKILL_ROOTS + [SKILLS_SRC]
    skill_mds = [
        md for root in all_roots if root.exists()
        for md in sorted(root.rglob("SKILL.md"))
        if "disabled" not in md.parts
    ]

    for skill_md in skill_mds:
        skill_dir = skill_md.parent
        content = skill_md.read_text(encoding="utf-8")
        meta = _parse_frontmatter(content)
        email = meta.get("email", "")
        entry = {"name": skill_dir.name, "description": meta.get("description", "")}

        if not email:
            commons.append(entry)
        elif me and _owner_prefix(email) == me:
            mine.append(entry)
        else:
            catalog.append({**entry, "owner": _owner_prefix(email)})

    if not commons and not mine and not catalog:
        print("ローカルにスキルはありません。/ No local skills found.")
        return

    C1, C2 = 20, 28

    def _row(cat, name, desc):
        d = desc[:55] + "..." if len(desc) > 55 else desc
        print(f"{cat:<{C1}}  {name:<{C2}}  {d}")

    print(f"{'カテゴリ / Category':<{C1}}  {'スキル名 / Skill':<{C2}}  説明 / Description")
    print("─" * (C1 + C2 + 62))
    for s in commons:
        _row("Common", s["name"], s["description"])
    for s in mine:
        _row("My skill", s["name"], s["description"])
    for s in catalog:
        _row(s["owner"], s["name"], s["description"])

    total = len(commons) + len(mine) + len(catalog)
    print()
    print(f"計 {total} スキル / Total {total} skills")
    if mine or catalog:
        print("My skill = 自分が作成・オーナーのスキル / Skills you own (can be shared to catalog)")
        print("<owner>  = カタログからインポートしたスキル / Skills imported from catalog")
    if not me:
        print()
        print("※ config.toml の [user] email を設定すると My skill を自動識別できます。")
        print("  Set [user] email in config.toml to auto-detect your own skills.")



def cmd_whoami():
    service = _get_service()
    email = _current_email(service)
    print(f"  ログイン中 / Logged in as : {email}")
    print(f"  オーナーフォルダ / Owner folder: {_owner_prefix(email)}/")


def cmd_update_index():
    """Drive をフルスキャンしてインデックスを更新する。"""
    service = _get_service()
    folders = _list_owner_folders(service)
    all_skills = []
    for owner, folder_id in sorted(folders.items()):
        for f in _list_md_in_folder(service, folder_id):
            content = _get_file_content(service, f["id"])
            desc = _parse_frontmatter(content).get("description", "")
            all_skills.append({
                "owner": owner,
                "name": f["name"][:-3],
                "modified": f["modifiedTime"][:10],
                "description": desc,
            })
    _write_index(all_skills)
    _push_catalog_to_drive(service)
    print(f"  [OK] インデックスを更新しました ({len(all_skills)} スキル)")
    print(f"       / Index updated ({len(all_skills)} skill(s))")


_DESC_MAX = 40  # 説明の表示最大文字数

def _print_skills_table(skills: list):
    if not skills:
        print("ライブラリにスキルはありません。/ No skills in the catalog.")
        return
    skills = sorted(skills, key=lambda x: x["name"])
    w_name  = max(len(s["name"])  for s in skills)
    w_owner = max(len(s["owner"]) for s in skills)
    w_name  = max(w_name,  len("スキル名 / Name"))
    w_owner = max(w_owner, len("オーナー / Owner"))
    header = (f"{'スキル名 / Name':<{w_name}}  "
              f"{'オーナー / Owner':<{w_owner}}  {'更新日 / Updated':<10}  説明 / Description")
    print(header)
    print("─" * len(header))
    for s in skills:
        desc = s.get("description", "")
        if len(desc) > _DESC_MAX:
            desc = desc[:_DESC_MAX - 1] + "…"
        print(f"{s['name']:<{w_name}}  {s['owner']:<{w_owner}}  {s['modified']:<10}  {desc}")


def cmd_list():
    try:
        service = _get_service()
        skills = _pull_catalog_from_drive(service)
        if skills is None:
            print("  カタログを初期化中... / Building catalog (first run)...")
            cmd_update_index()
            skills = _read_index() or []
    except Exception:
        # Drive 接続失敗時はローカルキャッシュにフォールバック
        skills = _read_index()
        if skills is None:
            print("[ERROR] Drive に接続できず、ローカルキャッシュもありません。")
            print("        ネットワーク接続を確認して再実行してください。")
            sys.exit(1)
        print("[INFO] Drive に接続できません。ローカルキャッシュを使用します。")
    _print_skills_table(skills)


def cmd_info(name_or_path: str):
    service = _get_service()
    m = _require_single_match(_find_skill(service, name_or_path), name_or_path)
    content = _get_file_content(service, m["file_id"])
    meta = _parse_frontmatter(content)

    print("─" * 56)
    print(f"  スキル / Skill  : {m['name']}")
    print(f"  オーナー / Owner: {m['owner']}")
    print(f"  更新日 / Updated: {m['modified']}")
    if meta.get("author"):
        print(f"  作成者 / Author : {meta['author']}")
    if meta.get("description"):
        print(f"  説明 / Desc     : {meta['description']}")
    print("─" * 56)
    print(content)


def cmd_download(name_or_path: str):
    service = _get_service()
    m = _require_single_match(_find_skill(service, name_or_path), name_or_path)

    skill_dir = SKILLS_SRC / m["name"]
    skill_md  = skill_dir / "SKILL.md"

    if skill_dir.exists():
        print(f"[INFO] 既存のスキルを上書きします / Overwriting existing skill: {m['name']}")

    skill_dir.mkdir(exist_ok=True)
    content = _get_file_content(service, m["file_id"])
    skill_md.write_text(content, encoding="utf-8")

    print(f"[OK] ダウンロード完了 / Downloaded: {m['owner']}/{m['name']}")
    print(f"     保存先 / Saved to: python/skills-personal/{m['name']}/SKILL.md")
    print()
    print("スキルを有効化するには / To activate the skill:")
    print("  python3 python/scripts/setup/setup.py skills rebuild")


def cmd_upload(skill_name: str):
    skill_md = SKILLS_SRC / skill_name / "SKILL.md"
    if not skill_md.exists():
        print(f"[ERROR] SKILL.md が見つかりません / Not found: {skill_md}")
        sys.exit(1)

    service = _get_service()
    email   = _current_email(service)
    owner   = _owner_prefix(email)

    content = skill_md.read_text(encoding="utf-8")
    meta    = _parse_frontmatter(content)

    # Inject author/email into frontmatter if missing or stale
    updates = {}
    if not meta.get("author"):
        about = service.about().get(fields="user").execute()
        updates["author"] = about["user"].get("displayName", owner)
    if meta.get("email") != email:
        updates["email"] = email
    if updates:
        content = _update_frontmatter(content, updates)
        skill_md.write_text(content, encoding="utf-8")
        print(f"[INFO] frontmatter を更新しました (author/email)")

    # Collision check: same skill name under a different owner?
    existing = _find_skill(service, skill_name)
    for e in existing:
        if e["owner"] != owner:
            print(f"[ERROR] 同名のスキルが別のオーナーのもとに存在します:")
            print(f"        {e['owner']}/{skill_name}")
            print(f"        スキル名を変更するか、オーナーに連絡してください。")
            sys.exit(1)

    folder_id  = _get_or_create_owner_folder(service, owner)
    own_match  = next((e for e in existing if e["owner"] == owner), None)
    file_id    = _upload_content(service, folder_id, skill_name + ".md",
                                 content, own_match["file_id"] if own_match else None)
    verb = "更新しました / Updated" if own_match else "アップロードしました / Uploaded"
    print(f"[OK] {verb}: {owner}/{skill_name}")
    _index_add(skill_name, owner)
    _push_catalog_to_drive(service)


def cmd_delete(name_or_path: str):
    service = _get_service()
    email   = _current_email(service)
    owner   = _owner_prefix(email)

    m = _require_single_match(_find_skill(service, name_or_path), name_or_path)

    if m["owner"] != owner:
        print(f"[ERROR] 削除できません。このスキルのオーナーは {m['owner']} です。")
        print(f"        自分がオーナーのスキルのみ削除できます。")
        sys.exit(1)

    service.files().delete(fileId=m["file_id"], supportsAllDrives=True).execute()
    print(f"[OK] 削除しました / Deleted: {m['owner']}/{m['name']}")
    _index_remove(m["name"], m["owner"])
    _push_catalog_to_drive(service)


def cmd_change_owner(name_or_path: str, new_email: str):
    service = _get_service()
    email   = _current_email(service)
    owner   = _owner_prefix(email)

    m = _require_single_match(_find_skill(service, name_or_path), name_or_path)

    if m["owner"] != owner:
        print(f"[ERROR] オーナーを変更できません。このスキルのオーナーは {m['owner']} です。")
        sys.exit(1)

    new_owner     = _owner_prefix(new_email)
    old_folder_id = _list_owner_folders(service)[m["owner"]]
    new_folder_id = _get_or_create_owner_folder(service, new_owner)

    # Update email in frontmatter and move file
    content = _update_frontmatter(_get_file_content(service, m["file_id"]),
                                  {"email": new_email})
    from googleapiclient.http import MediaIoBaseUpload
    service.files().update(
        fileId=m["file_id"],
        media_body=MediaIoBaseUpload(
            io.BytesIO(content.encode("utf-8")), mimetype="text/plain", resumable=False),
        supportsAllDrives=True,
    ).execute()
    service.files().update(
        fileId=m["file_id"],
        addParents=new_folder_id,
        removeParents=old_folder_id,
        supportsAllDrives=True,
        fields="id, parents",
    ).execute()

    print(f"[OK] オーナーを変更しました / Owner changed:")
    print(f"     {m['owner']}/{m['name']}  →  {new_owner}/{m['name']}")
    _index_change_owner(m["name"], m["owner"], new_owner)
    _push_catalog_to_drive(service)


# ── Entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    cmd = args[0]
    if cmd == "list":
        cmd_list()
    elif cmd == "update-index":
        cmd_update_index()
    elif cmd == "list-local":
        cmd_list_local()
    elif cmd == "whoami":
        cmd_whoami()
    elif cmd == "info":
        if len(args) < 2:
            print("[ERROR] Usage: skills_catalog.py info <name|owner/name>"); sys.exit(1)
        cmd_info(args[1])
    elif cmd == "download":
        if len(args) < 2:
            print("[ERROR] Usage: skills_catalog.py download <name|owner/name>"); sys.exit(1)
        cmd_download(args[1])
    elif cmd == "upload":
        if len(args) < 2:
            print("[ERROR] Usage: skills_catalog.py upload <skill_name>"); sys.exit(1)
        cmd_upload(args[1])
    elif cmd == "delete":
        if len(args) < 2:
            print("[ERROR] Usage: skills_catalog.py delete <name|owner/name>"); sys.exit(1)
        cmd_delete(args[1])
    elif cmd == "change-owner":
        if len(args) < 3:
            print("[ERROR] Usage: skills_catalog.py change-owner <name|owner/name> <new_email>"); sys.exit(1)
        cmd_change_owner(args[1], args[2])
    else:
        print(f"[ERROR] Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)
