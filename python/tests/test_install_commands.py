"""
Regression test for src-tauri/resources/install_commands.json's agy
install commands.

The bug: the Windows install command used `iex (iwr -useb <url>)` -- a
"fileless" download-and-execute-in-memory pattern. This is the signature
shape of a huge number of malware droppers, so security products
(confirmed for real: ESET on a real company machine) commonly flag and
block it outright, breaking agy's onboarding install for legitimate users
too.

Fix: download the installer script to a temp file first, then execute
that file directly (`& $tmp`), which is a far less commonly-flagged
pattern. Since `& $tmp` (running a script FILE) is subject to
ExecutionPolicy in a way a `-Command`-evaluated string is not, the
command also sets `Set-ExecutionPolicy -Scope Process -Bypass` first --
scoped to only the current process, no elevation needed, reverted
automatically when the process exits.

This file is embedded into the compiled Tauri binary at build time via
`include_str!` (see src-tauri/src/agent.rs) -- editing the source JSON
requires a rebuild for the change to reach a real install.

Run:
  pytest python/tests/test_install_commands.py -v
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALL_COMMANDS_PATH = ROOT / "src-tauri" / "resources" / "install_commands.json"


def _windows_install_args() -> str:
    data = json.loads(INSTALL_COMMANDS_PATH.read_text())
    return " ".join(data["agy"]["install"]["windows"]["args"])


def _macos_install_args() -> str:
    data = json.loads(INSTALL_COMMANDS_PATH.read_text())
    return " ".join(data["agy"]["install"]["macos"]["args"])


def _detect_paths() -> dict:
    data = json.loads(INSTALL_COMMANDS_PATH.read_text())
    return data["agy"]["detect_paths"]


class TestWindowsInstallCommandAvoidsFilelessExecution:
    def test_is_valid_json(self):
        json.loads(INSTALL_COMMANDS_PATH.read_text())

    def test_does_not_pipe_remote_script_into_iex(self):
        args = _windows_install_args()
        assert "iex (iwr" not in args and "| iex" not in args, (
            "install_commands.json's Windows agy install command pipes a "
            "remote script directly into iex (fileless execution) -- this "
            "exact pattern gets blocked by security products like ESET, "
            "breaking legitimate installs. Download to a temp file and "
            "execute that instead."
        )

    def test_downloads_to_a_file_before_executing(self):
        args = _windows_install_args()
        assert "Invoke-WebRequest" in args and "-OutFile" in args, (
            "install_commands.json's Windows agy install command no longer "
            "downloads the installer script to a file before running it."
        )
        assert "& $tmp" in args, (
            "install_commands.json's Windows agy install command no longer "
            "executes the downloaded temp file directly."
        )

    def test_sets_process_scoped_execution_policy(self):
        """Running a downloaded .ps1 FILE (unlike a -Command string) is
        subject to ExecutionPolicy -- without this, the file-based
        approach could newly fail on a machine with a Restricted policy
        that the old iex-based approach happened to bypass."""
        args = _windows_install_args()
        assert "Set-ExecutionPolicy" in args and "-Scope Process" in args, (
            "install_commands.json's Windows agy install command no longer "
            "sets a process-scoped execution policy bypass -- running the "
            "downloaded script file could fail under a Restricted policy."
        )

    def test_cleans_up_the_temp_file(self):
        args = _windows_install_args()
        assert "Remove-Item $tmp" in args, (
            "install_commands.json's Windows agy install command no longer "
            "cleans up the downloaded temp script file."
        )


class TestInstallUrlsPointAtTheRealInstallerHost:
    """Regression guard for a second, independent bug found 2026-07-21:
    the URLs baked into install_commands.json (antigravity.google.com/
    install.sh and .../install.ps1) returned the antigravity.google.com
    website's own HTML/JS SPA shell instead of a real installer script --
    confirmed via direct curl from a clean environment, so this was not
    an AV/EDR block. The official download page documents a different
    domain (antigravity.google, no ".com") and path (/cli/install.sh,
    /cli/install.ps1), confirmed by curl to serve real scripts
    (content-type application/x-sh and application/octet-stream
    respectively). Do not revert to the antigravity.google.com host
    without re-verifying it serves real script content, not the site
    shell."""

    def test_macos_uses_the_real_installer_host(self):
        args = _macos_install_args()
        assert "https://antigravity.google/cli/install.sh" in args, (
            "install_commands.json's macOS agy install command should "
            "fetch from antigravity.google/cli/install.sh (confirmed to "
            "serve a real script) -- not antigravity.google.com/install.sh "
            "(confirmed to serve the website's HTML shell instead)."
        )

    def test_windows_uses_the_real_installer_host(self):
        args = _windows_install_args()
        assert "https://antigravity.google/cli/install.ps1" in args, (
            "install_commands.json's Windows agy install command should "
            "fetch from antigravity.google/cli/install.ps1 (confirmed to "
            "serve a real script) -- not antigravity.google.com/install.ps1 "
            "(confirmed to serve the website's HTML shell instead)."
        )


class TestDetectPathsMatchWhereTheInstallerActuallyPutsIt:
    """Regression guard for a third bug found 2026-07-21: our install
    commands set a $BINDIR / -Command "app/bin" override that both
    install.sh and install.ps1 silently ignore (confirmed by running the
    real installer end to end) -- they only honor a --dir/-d flag, and
    default to $HOME/.local/bin (macOS) / $env:LOCALAPPDATA\\agy\\bin
    (Windows) otherwise. Since neither script was actually being told
    -dir, every real install landed at that per-user default -- which
    was NOT in this file's own detect_paths list, and (confirmed via
    /etc/paths + /etc/paths.d on a real Mac) is also not on the minimal
    PATH a GUI-launched app inherits, so detect_agent_internal's `which`
    fallback can't find it either. Net effect: install could succeed at
    the OS level while agent-deck kept reporting it as not installed.
    Both installers' default locations require no admin/elevation, so
    the fix is to just point detect_paths at reality rather than fight
    the installers' own default (a custom --dir would need to keep being
    re-verified against upstream's own defaults every time they change,
    exactly as happened to the dead $BINDIR override this replaces)."""

    def test_macos_detects_the_installers_real_default_location(self):
        paths = _detect_paths()["macos"]
        assert "$HOME/.local/bin/agy" in paths, (
            "install_commands.json's macOS detect_paths is missing "
            "$HOME/.local/bin/agy -- install.sh's actual default install "
            "location (confirmed by running it for real)."
        )

    def test_windows_detects_the_installers_real_default_location(self):
        paths = _detect_paths()["windows"]
        assert "$USERPROFILE\\AppData\\Local\\agy\\bin\\agy.exe" in paths, (
            "install_commands.json's Windows detect_paths is missing "
            "$USERPROFILE\\AppData\\Local\\agy\\bin\\agy.exe -- install.ps1's "
            "actual default install location ($env:LOCALAPPDATA\\agy\\bin)."
        )

    def test_macos_install_command_no_longer_sets_the_ignored_bindir_override(self):
        args = _macos_install_args()
        assert "BINDIR" not in args and "app/bin" not in args, (
            "install_commands.json's macOS install command still sets a "
            "$BINDIR override or creates app/bin -- confirmed for real that "
            "install.sh ignores $BINDIR entirely (it only reads a --dir/-d "
            "flag), so this is dead, misleading configuration."
        )

    def test_windows_install_command_no_longer_sets_the_ignored_bindir_override(self):
        args = _windows_install_args()
        assert "BINDIR" not in args and "app\\bin" not in args, (
            "install_commands.json's Windows install command still sets a "
            "$env:BINDIR override or creates app\\bin -- confirmed for real "
            "that install.ps1 ignores $env:BINDIR entirely (it only reads a "
            "-d/--dir flag), so this is dead, misleading configuration."
        )
