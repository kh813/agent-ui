"""Self-update checker for agent-deck (formerly agent-ui) itself.

Updates the app in place: asks GitHub for whatever the *latest* published
release actually is, and swaps the currently-installed app bundle/exe (a
sibling of python/ and config/ at the project root — see the release
workflow's zip-staging step) for the new one, along with the bundled
python/ tree (skills, setup scripts) from the same zip.

Product rename (2026-07-16): this project (and its GitHub repo) renamed
agent-ui -> agent-deck. The canonical bundle/exe name, asset names, and the
binary embedded inside a Mac bundle (Contents/MacOS/agent-deck) all changed
accordingly starting with v0.0.15. Backward compat for anyone still on a
pre-v0.0.15 self_update.py (baked in, unpatchable) is handled entirely on
the release-CI side: v0.0.15+ releases ALSO publish legacy-named assets
(agent-ui-mac.zip/agent-ui-win.zip, with the old agent-ui.app/agent-ui.exe
internal structure) for one/two releases' grace period — see release.yml's
"package legacy-named ... compatibility zip" steps. This script itself only
ever deals in the current (agent-deck) naming.

Rebranded installs: an ORGANIZATION may separately ship this whole layout
under its own product name — the bundle then sits at the project root as
e.g. acme-console.app / acme-console.exe instead of agent-deck.* (only the
OUTER name differs; the binary inside a Mac bundle is still
Contents/MacOS/agent-deck, baked in at build time). This script therefore:
  - detects the installed bundle's actual name and KEEPS it when swapping
    in the update, rather than assuming agent-deck.*;
  - reads the installed version from the rebrander's marker
    (app/<name>.version, written as "<tag>+<build>" by its own pinned
    installer) as a fallback, comparing tags with any "+build" suffix
    stripped;
  - always WRITES its own marker to <root>/<name>.version and never touches
    the rebrander's app/<name>.version — the rebrander's pinned installer
    checks its own marker against its own pin, and overwriting it with a
    newer tag would make that installer "helpfully" reinstall (downgrade
    to) its pin on the next launch.

python/ payload (2026-07-16): also extracted from the same zip on every
update — previously only the binary was swapped, silently leaving skills
and setup scripts at the old version forever. python/skills-personal/ (user
-created and catalog-synced skills) is preserved across the refresh. Every
*.sh in the new payload is normalized to LF: the Windows zip's python/ tree
has shipped CRLF before (Windows CI runners), which breaks bash on Mac
("$'\\r': command not found").

Reuses the atomic-swap safety pattern: download and extract into a staging
directory first, and only remove the existing install once the replacement
is verified in place, so a failed/interrupted download never leaves the
user with no install at all.

Since this app may be the very process invoking this script (e.g. via a
skill run from inside a live session), this script never touches the
running binary's open file — it replaces it on disk and asks the user to
relaunch. It does not attempt a hot in-place self-replace.

Usage:
  python3 self_update.py check                          # GitHub prod channel (/releases/latest)
  python3 self_update.py check --json                   # same, as a single JSON line (for the Tauri menu)
  python3 self_update.py apply                          # download and install the latest release
  python3 self_update.py check --test                   # GitHub's newest pre-release instead
  python3 self_update.py apply --test
  python3 self_update.py check --drive-file-id ID        # org's config-bundled Drive build instead
  python3 self_update.py apply --drive-file-id ID        # (see package_release.py for what builds this)

Channels: "prod" (default) is GitHub's /releases/latest, which by GitHub's
own definition excludes pre-releases. "--test" walks the plain /releases
list for the newest release tagged as a pre-release (see release.yml's
"determine release channel" step for how a tag becomes one). apply()'s own
tag-equality check means switching channels back and forth just works,
including "downgrading" from a test build's tag back to the current prod
tag.

--drive-file-id is a separate, third source entirely: a specific Google
Drive file (this org's config-bundled internal distribution ZIP, built
and kept up to date by package_release.py) rather than anything on
GitHub. This is the only path in this file that needs Google's OAuth
libraries (see _reexec_with_venv_for_drive_mode) -- the GitHub paths
above stay pure-stdlib on purpose, so this script works even before a
venv exists.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
_REPO = "kh813/agent-deck"  # renamed from kh813/agent-ui 2026-07-16 (old URL 301-redirects)
_API_LATEST = f"https://api.github.com/repos/{_REPO}/releases/latest"
_API_RELEASES = f"https://api.github.com/repos/{_REPO}/releases"

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _dest_name() -> str:
    """Name of the installed bundle/exe at the project root — kept as-is
    across updates so a rebranded install stays under its own name."""
    if sys.platform == "win32":
        default = "agent-deck.exe"
        if (PROJECT_ROOT / default).exists():
            return default
        # A rebranded install has exactly one launcher exe at the root.
        exes = sorted(p.name for p in PROJECT_ROOT.glob("*.exe"))
        return exes[0] if len(exes) == 1 else default
    default = "agent-deck.app"
    if (PROJECT_ROOT / default).is_dir():
        return default
    for p in sorted(PROJECT_ROOT.glob("*.app")):
        # The rebranded bundle is still agent-deck inside (see module docstring).
        if (p / "Contents" / "MacOS" / "agent-deck").exists():
            return p.name
    return default


def _asset_name() -> str:
    return "agent-deck-win.zip" if sys.platform == "win32" else "agent-deck-mac.zip"


def _marker_path(dest_name: str) -> Path:
    return PROJECT_ROOT / f"{dest_name}.version"


def _installed_tag(dest_name: str) -> str:
    """Installed version tag, with any rebrander "+build" suffix stripped.

    Reads this script's own root-level marker first; falls back to a
    rebrander's app/<name>.version (see module docstring)."""
    for marker in (_marker_path(dest_name),
                   PROJECT_ROOT / "app" / f"{dest_name}.version"):
        if marker.exists():
            return marker.read_text().strip().split("+")[0]
    return ""


def _fetch_latest_release() -> dict:
    req = urllib.request.Request(
        _API_LATEST, headers={"Accept": "application/vnd.github+json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_latest_prerelease() -> dict:
    """Return the newest pre-release (a tag with a semver prerelease suffix,
    e.g. v0.0.22-rc1 -- see release.yml). GitHub's /releases/latest endpoint
    excludes pre-releases by definition, so this walks the plain releases
    list instead, which the API already returns newest-first."""
    req = urllib.request.Request(
        _API_RELEASES, headers={"Accept": "application/vnd.github+json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        releases = json.loads(resp.read().decode("utf-8"))
    for release in releases:
        if release.get("prerelease"):
            return release
    raise RuntimeError(f"No pre-release found among {_REPO}'s releases")


def _fetch_release(channel: str) -> dict:
    return _fetch_latest_prerelease() if channel == "test" else _fetch_latest_release()


def check(channel: str = "prod") -> tuple[bool, str, str]:
    """Return (update_available, installed_tag, latest_tag) for the given
    channel ("prod" = latest stable release, "test" = latest pre-release)."""
    release = _fetch_release(channel)
    latest_tag = release["tag_name"]
    installed_tag = _installed_tag(_dest_name())
    return (installed_tag != latest_tag, installed_tag, latest_tag)


def _normalize_sh_to_lf(target: Path) -> None:
    for sh in target.rglob("*.sh"):
        data = sh.read_bytes()
        if b"\r\n" in data:
            sh.write_bytes(data.replace(b"\r\n", b"\n"))


def _install_python_payload(staging: Path) -> None:
    """Refresh <root>/python/ from the zip, preserving skills-personal/."""
    new_python = staging / "python"
    if not new_python.exists():
        return

    dest_python = PROJECT_ROOT / "python"
    existing_personal = dest_python / "skills-personal"
    personal_backup = staging / "_skills_personal_backup"
    if existing_personal.exists():
        shutil.move(str(existing_personal), str(personal_backup))

    if dest_python.is_symlink():
        dest_python.unlink()
    elif dest_python.exists():
        shutil.rmtree(dest_python)
    shutil.copytree(new_python, dest_python)
    _normalize_sh_to_lf(dest_python)

    if personal_backup.exists():
        shutil.rmtree(dest_python / "skills-personal", ignore_errors=True)
        shutil.move(str(personal_backup), str(dest_python / "skills-personal"))


def _verify_mac_signature(new_dest: Path, label: str) -> None:
    """Defensive re-sign + verify over a freshly extracted mac bundle (an
    upstream CI signing bug once shipped one whose resource seal predated
    Contents/Resources -- harmless no-op on correctly-signed builds).

    Gate: confirmed for real (2026-07-23) that an invalid signature here
    means macOS refuses to even launch the app ("is damaged and can't be
    opened", error -47, with NO user override available) -- materially
    worse than the normal "unidentified developer" Gatekeeper prompt, which
    DOES offer an Open Anyway override once the signature itself verifies.
    Better to keep the current, working install than swap in a bundle that
    can never launch at all."""
    subprocess.run(["xattr", "-cr", str(new_dest)], check=False, stdin=subprocess.DEVNULL)
    (new_dest / "Contents" / "MacOS" / "agent-deck").chmod(0o755)
    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", str(new_dest)],
        check=False, stdin=subprocess.DEVNULL,
    )
    verify = subprocess.run(
        ["codesign", "--verify", "--deep", "--strict", str(new_dest)],
        capture_output=True, stdin=subprocess.DEVNULL,
    )
    if verify.returncode != 0:
        raise RuntimeError(
            f"Code signature verification failed for {label} -- aborting "
            f"before replacing the current install. Details: "
            f"{verify.stderr.decode(errors='replace').strip()}"
        )


def _atomic_swap(new_dest: Path, dest: Path) -> None:
    """Swap new_dest into dest's path, handling the same edge cases on
    every caller: a stale symlink from an old layout, an existing
    directory, and Windows' refusal to recreate a file at a path whose
    last handle (the running process itself) hasn't closed yet."""
    if dest.is_symlink():
        dest.unlink()
    elif dest.is_dir():
        shutil.rmtree(dest)
    elif dest.exists():
        if sys.platform == "win32":
            # This process's own exe is `dest` (or its parent, if this
            # script is running inside an agy session spawned by it) —
            # Windows lets you DELETE or RENAME a running exe (the OS
            # loader opens it with FILE_SHARE_DELETE), but it won't let
            # you create a new file at that same path until the last
            # handle closes (i.e. until the user restarts): a plain
            # dest.unlink() here "succeeds" but the shutil.move() right
            # after it then fails with "Access is denied". Renaming the
            # old exe out of the way first frees the original path
            # immediately, since we're no longer touching the
            # pending-delete file at all.
            old_dest = dest.with_name(dest.name + ".old")
            if old_dest.exists():
                try:
                    old_dest.unlink()
                except OSError:
                    pass  # leftover from a prior update; harmless, ignore
            dest.rename(old_dest)
        else:
            dest.unlink()
    shutil.move(str(new_dest), str(dest))


def apply(channel: str = "prod") -> None:
    release = _fetch_release(channel)
    latest_tag = release["tag_name"]
    dest_name = _dest_name()
    installed_tag = _installed_tag(dest_name)

    if installed_tag == latest_tag:
        print(f"  Already up to date: {dest_name} ({latest_tag})")
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

    print(f"  Updating: {installed_tag or 'unknown'} -> {latest_tag}")
    print(f"  Downloading {url}...")

    dest = PROJECT_ROOT / dest_name
    upstream_name = "agent-deck.exe" if sys.platform == "win32" else "agent-deck.app"

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
            _verify_mac_signature(new_dest, f"the downloaded {latest_tag} build")

        _atomic_swap(new_dest, dest)
        _install_python_payload(staging)

    _marker_path(dest_name).write_text(latest_tag)
    print(f"  {latest_tag} installed to {dest}.")
    print("  Restart the app to use the new version.")


# ── Org (Google Drive) channel ───────────────────────────────────────────
#
# Distinct from the GitHub channels above: this fetches the config-bundled
# internal distribution ZIP that package_release.py builds and uploads to a
# fixed Drive file (config.toml's [drive] org_release_prod_file_id /
# org_release_test_file_id -- see the Tauri menu's "Update to Org
# Latest/Test" items, which pass the resolved file ID in via
# --drive-file-id). Unlike the GitHub path, this needs Google's OAuth
# libraries, so it's the one thing in this file that isn't pure-stdlib --
# see _reexec_with_venv_for_drive_mode below, invoked only when actually
# needed.

def _drive_marker_path(dest_name: str) -> Path:
    return PROJECT_ROOT / f"{dest_name}.drive-source.json"


def _reexec_with_venv_for_drive_mode():
    """The plain GitHub check/apply path stays pure-stdlib on purpose (see
    module docstring: this script must work even before/without a venv).
    Only re-exec under the venv's python when --drive-file-id is actually
    present on the command line."""
    if "--drive-file-id" not in sys.argv:
        return
    try:
        import googleapiclient  # noqa: F401
        return  # already importable (already in venv, or installed globally)
    except ImportError:
        pass
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


def _get_drive_service():
    sys.path.insert(0, str(PROJECT_ROOT / "python"))
    from config import OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET, USER_EMAIL  # noqa: E402
    from scripts.auth import run_auth_flow  # noqa: E402
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    client_config = {
        "installed": {
            "client_id": OAUTH_CLIENT_ID,
            "client_secret": OAUTH_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    # Shared with skills_catalog.py/drive_upload.py/backup_config.py -- same
    # scope, same token cache, so authorizing once via any of them covers all.
    token_path = Path.home() / ".gemini" / "agent_ui_library_token.json"
    scopes = ["https://www.googleapis.com/auth/drive"]

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_config(client_config, scopes)
            creds = run_auth_flow(flow, login_hint=USER_EMAIL or None,
                                   purpose="agent-deck 組織内アップデート / Org update")
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def check_drive(file_id: str) -> tuple[bool, str, str]:
    """Return (update_available, installed_marker, latest_marker) for the
    org's Drive-hosted, config-bundled distribution ZIP. Uses the Drive
    file's modifiedTime as the "version" -- there's no release tag for a
    single mutable file that package_release.py overwrites in place on
    every --test/--prod run."""
    service = _get_drive_service()
    meta = service.files().get(
        fileId=file_id, fields="modifiedTime", supportsAllDrives=True
    ).execute()
    latest_modified = meta["modifiedTime"]

    marker = _drive_marker_path(_dest_name())
    installed_modified = ""
    if marker.exists():
        try:
            stored = json.loads(marker.read_text())
        except (json.JSONDecodeError, OSError):
            stored = {}
        if stored.get("file_id") == file_id:
            installed_modified = stored.get("modifiedTime", "")

    return (installed_modified != latest_modified, installed_modified, latest_modified)


def _download_drive_media(service, file_id: str, dest_path: Path) -> None:
    from googleapiclient.http import MediaIoBaseDownload
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    with open(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def apply_drive(file_id: str) -> None:
    service = _get_drive_service()
    meta = service.files().get(
        fileId=file_id, fields="modifiedTime", supportsAllDrives=True
    ).execute()
    latest_modified = meta["modifiedTime"]

    dest_name = _dest_name()
    dest = PROJECT_ROOT / dest_name
    upstream_name = "agent-deck.exe" if sys.platform == "win32" else "agent-deck.app"

    print("  Downloading org build from Google Drive...")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        zip_path = tmp_path / "agent-deck-org.zip"
        _download_drive_media(service, file_id, zip_path)

        staging = tmp_path / "extracted"
        staging.mkdir()
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(staging)

        new_dest = staging / upstream_name
        if not new_dest.exists():
            raise RuntimeError(
                f"Drive ZIP did not contain {upstream_name} -- "
                f"was it built by package_release.py?"
            )

        if sys.platform != "win32":
            _verify_mac_signature(new_dest, "the org build downloaded from Drive")

        _atomic_swap(new_dest, dest)
        _install_python_payload(staging)

        # The org's config-bundled ZIP is the one place config.toml itself
        # ships -- refresh the local copy so org-wide config changes (Drive
        # file IDs, OAuth creds, company settings) propagate the same way
        # the app/skills do, not just on a fresh install.
        bundled_config = staging / "config.toml"
        if bundled_config.exists():
            shutil.copy(bundled_config, PROJECT_ROOT / "config.toml")

    _drive_marker_path(dest_name).write_text(json.dumps({
        "file_id": file_id,
        "modifiedTime": latest_modified,
    }))
    print(f"  Org build installed to {dest}.")
    print("  Restart the app to use the new version.")


def _usage():
    print("Usage: self_update.py [check|apply] [--test] [--json] [--drive-file-id ID]")
    sys.exit(1)


if __name__ == "__main__":
    _reexec_with_venv_for_drive_mode()

    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    rest = sys.argv[2:]

    drive_file_id = None
    if "--drive-file-id" in rest:
        idx = rest.index("--drive-file-id")
        if idx + 1 >= len(rest):
            print("[ERROR] --drive-file-id requires a value")
            sys.exit(1)
        drive_file_id = rest[idx + 1]

    channel = "test" if "--test" in rest else "prod"

    if cmd == "check":
        if drive_file_id:
            available, installed, latest = check_drive(drive_file_id)
            label = "org"
        else:
            available, installed, latest = check(channel)
            label = channel
        if "--json" in rest:
            print(json.dumps({
                "update_available": available,
                "installed_tag": installed,
                "latest_tag": latest,
                "channel": label,
            }))
        elif available:
            print(f"Update available ({label}): {installed or 'unknown'} -> {latest}")
        else:
            print(f"Already up to date ({label}): {latest}")
    elif cmd == "apply":
        if drive_file_id:
            apply_drive(drive_file_id)
        else:
            apply(channel)
    else:
        _usage()
