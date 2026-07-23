#!/usr/bin/env python3
"""Rebuild kh813/agent-deck's public GitHub release with this org's own
config.toml merged in, and upload the result to a Drive file used for
internal (config-bundled) distribution.

Supersedes the old agent-deck-old/src/scripts/release.sh flow for this
org: rather than building the app locally and bundling a hand-installed
agy, this downloads the SAME public release ZIPs any external adopter
would get (agent-deck-mac.zip / agent-deck-win.zip), merges both
platforms into one flat tree (no wrapper folder -- identical layout to
the public ZIP itself, so README/docs/user_guide.md's extraction
instructions apply unchanged), drops in this project's own config.toml
(the one thing the public ZIP can never include), and re-zips.

Channel resolution is shared with self_update.py: --test bundles
kh813/agent-deck's newest GitHub pre-release (a tag with a semver
prerelease suffix -- see release.yml); --prod bundles its
/releases/latest. Uploads to the Drive file ID configured in this org's
own config.toml ([drive].org_release_test_file_id / _prod_file_id),
overwriting the previous upload in place (same update-existing-file
pattern as backup_config.py).

Usage:
  python3 python/scripts/tools/package_release.py --test
  python3 python/scripts/tools/package_release.py --prod
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
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

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

sys.path.insert(0, str(PROJECT_ROOT / "python" / "scripts" / "setup"))
import self_update as su  # noqa: E402 -- reuses channel/tag resolution


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
            sys.exit(subprocess.run([str(venv_python)] + sys.argv).returncode)
        else:
            os.execv(str(venv_python), [str(venv_python)] + sys.argv)


_reexec_with_venv()

sys.path.insert(0, str(PROJECT_ROOT / "python"))
from config import (  # noqa: E402
    OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET,
    ORG_RELEASE_TEST_FILE_ID, ORG_RELEASE_PROD_FILE_ID,
    USER_EMAIL,
)
from scripts.auth import run_auth_flow  # noqa: E402

SCOPES     = ["https://www.googleapis.com/auth/drive"]
# Shared with skills_catalog.py/drive_upload.py/backup_config.py -- same
# scope, same token cache, so authorizing once via any of them covers all.
TOKEN_PATH = Path.home() / ".gemini" / "agent_ui_library_token.json"

CLIENT_CONFIG = {
    "installed": {
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}

_ASSET_NAMES = ("agent-deck-mac.zip", "agent-deck-win.zip")


def _download(url: str, dest: Path) -> None:
    subprocess.run(
        ["curl", "-fsSL", "--connect-timeout", "10", "--max-time", "120",
         url, "-o", str(dest)],
        check=True, stdin=subprocess.DEVNULL, creationflags=_NO_WINDOW,
    )


def build_package(channel: str, staging: Path, config_toml: Path = None) -> Path:
    """Download both platform release ZIPs for `channel`, merge them into a
    single flat tree, drop in `config_toml` (defaults to this project's own
    config.toml), and zip it up. Returns the path to the built ZIP.

    No re-download needed per platform beyond the two assets: both zips
    ship identical python/config/agent_config.json/messages content, so
    extracting the second directly over the first is a same-content
    overwrite, not a real merge conflict -- only the platform-specific
    bundle/exe and preflight.sh/.bat actually differ between them.
    """
    release = su._fetch_release(channel)
    tag = release["tag_name"]
    print(f"  Resolved {channel} tag: {tag}")

    assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}
    missing = [n for n in _ASSET_NAMES if n not in assets]
    if missing:
        raise RuntimeError(f"Release {tag} is missing asset(s): {', '.join(missing)}")

    merged = staging / "merged"
    merged.mkdir()
    for name in _ASSET_NAMES:
        zip_path = staging / name
        print(f"  Downloading {name} ({tag})...")
        _download(assets[name], zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(merged)

    mac_binary = merged / "agent-deck.app" / "Contents" / "MacOS" / "agent-deck"
    if mac_binary.exists():
        mac_binary.chmod(0o755)
        # Defensive re-sign after the extract/merge round-trip -- the same
        # upstream CI signing quirk documented in release.yml (resource seal
        # sealed before Contents/Resources was finalized) can resurface
        # after ANY copy/repack of the bundle, not just the original build.
        # Harmless no-op if the signature was already fine.
        subprocess.run(["xattr", "-cr", str(merged / "agent-deck.app")],
                        check=False, stdin=subprocess.DEVNULL)
        subprocess.run(
            ["codesign", "--force", "--deep", "--sign", "-", str(merged / "agent-deck.app")],
            check=False, stdin=subprocess.DEVNULL,
        )
        # Gate: confirmed for real (2026-07-23) that an invalid signature
        # here means macOS refuses to even launch the app ("is damaged and
        # can't be opened", error -47, with NO user override available) --
        # worse than the normal "unidentified developer" Gatekeeper prompt,
        # which DOES offer an Open Anyway override once the signature itself
        # verifies. Abort before zipping/uploading a build that can never
        # launch, rather than shipping it and finding out from a user report.
        verify = subprocess.run(
            ["codesign", "--verify", "--deep", "--strict", str(merged / "agent-deck.app")],
            capture_output=True, stdin=subprocess.DEVNULL,
        )
        if verify.returncode != 0:
            raise RuntimeError(
                f"Code signature verification failed for the merged "
                f"agent-deck.app ({tag}) -- aborting before packaging/upload. "
                f"Details: {verify.stderr.decode(errors='replace').strip()}"
            )

    config_toml = config_toml or (PROJECT_ROOT / "config.toml")
    if not config_toml.exists():
        raise RuntimeError(f"config.toml not found at {config_toml} -- nothing to merge in")
    shutil.copy(config_toml, merged / "config.toml")

    zip_name = "agent-deck-test.zip" if channel == "test" else "agent-deck.zip"
    out_zip = staging / zip_name
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(merged.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(merged))

    return out_zip


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
            creds = run_auth_flow(flow, login_hint=USER_EMAIL or None,
                                   purpose="社内向け配布ZIP / Internal distribution ZIP")
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def upload(zip_path: Path, file_id: str) -> None:
    from googleapiclient.http import MediaFileUpload
    size_kb = zip_path.stat().st_size / 1024
    print(f"  Uploading {zip_path.name} ({size_kb:.1f} KB) ...")
    service = _get_service()
    media = MediaFileUpload(str(zip_path), mimetype="application/zip", resumable=True)
    service.files().update(fileId=file_id, media_body=media, supportsAllDrives=True).execute()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--test", action="store_true",
                        help="Bundle the newest GitHub pre-release; upload to org_release_test_file_id")
    group.add_argument("--prod", action="store_true",
                        help="Bundle the latest stable release; upload to org_release_prod_file_id")
    args = parser.parse_args()

    channel = "test" if args.test else "prod"
    file_id = ORG_RELEASE_TEST_FILE_ID if channel == "test" else ORG_RELEASE_PROD_FILE_ID
    if not file_id:
        print(f"[ERROR] config.toml に [drive] org_release_{channel}_file_id が設定されていません。")
        print(f"[ERROR] Set [drive] org_release_{channel}_file_id in config.toml.")
        sys.exit(1)

    with tempfile.TemporaryDirectory() as tmp:
        out_zip = build_package(channel, Path(tmp))
        upload(out_zip, file_id)

    print("✓ アップロード完了 / Upload complete")
    print(f"  https://drive.google.com/file/d/{file_id}/view")


if __name__ == "__main__":
    main()
