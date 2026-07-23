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
  python3 self_update.py check              # print whether an update is available (prod channel)
  python3 self_update.py check --json       # same, as a single JSON line (for callers like the Tauri menu)
  python3 self_update.py apply              # download and install the latest release (prod channel)
  python3 self_update.py check --test       # same, but against the latest pre-release
  python3 self_update.py apply --test       # download and install the latest pre-release

Channels: "prod" (default) is GitHub's /releases/latest, which by GitHub's
own definition excludes pre-releases. "--test" walks the plain /releases
list for the newest release tagged as a pre-release (see release.yml's
"determine release channel" step for how a tag becomes one). apply()'s own
tag-equality check means switching channels back and forth just works,
including "downgrading" from a test build's tag back to the current prod
tag.
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
            subprocess.run(["xattr", "-cr", str(new_dest)], check=False, stdin=subprocess.DEVNULL)
            (new_dest / "Contents" / "MacOS" / "agent-deck").chmod(0o755)
            # Defensive ad-hoc re-sign over the final bundle (an upstream CI
            # signing bug once shipped a bundle whose resource seal predated
            # Contents/Resources — harmless no-op on correctly-signed builds).
            subprocess.run(
                ["codesign", "--force", "--deep", "--sign", "-", str(new_dest)],
                check=False, stdin=subprocess.DEVNULL,
            )
            # Gate: confirmed for real (2026-07-23) that an invalid signature
            # here means macOS refuses to even launch the app ("is damaged
            # and can't be opened", error -47, with NO user override
            # available) -- a materially worse failure than the normal
            # "unidentified developer" Gatekeeper prompt, which DOES offer an
            # Open Anyway override once the signature itself verifies. Better
            # to keep the current, working install than swap in a bundle
            # that can never launch at all.
            verify = subprocess.run(
                ["codesign", "--verify", "--deep", "--strict", str(new_dest)],
                capture_output=True, stdin=subprocess.DEVNULL,
            )
            if verify.returncode != 0:
                raise RuntimeError(
                    f"Code signature verification failed for the downloaded "
                    f"{latest_tag} build -- aborting before replacing the "
                    f"current install. Details: "
                    f"{verify.stderr.decode(errors='replace').strip()}"
                )

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

        _install_python_payload(staging)

    _marker_path(dest_name).write_text(latest_tag)
    print(f"  {latest_tag} installed to {dest}.")
    print("  Restart the app to use the new version.")


def _usage():
    print("Usage: self_update.py [check|apply] [--test] [--json]")
    sys.exit(1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    rest = sys.argv[2:]
    channel = "test" if "--test" in rest else "prod"
    if cmd == "check":
        available, installed, latest = check(channel)
        if "--json" in rest:
            print(json.dumps({
                "update_available": available,
                "installed_tag": installed,
                "latest_tag": latest,
                "channel": channel,
            }))
        elif available:
            print(f"Update available ({channel}): {installed or 'unknown'} -> {latest}")
        else:
            print(f"Already up to date ({channel}): {latest}")
    elif cmd == "apply":
        apply(channel)
    else:
        _usage()
