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
