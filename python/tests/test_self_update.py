"""
Tests for self_update.py — agent-ui's own GitHub-Releases-based updater.

Covers the atomic-swap safety pattern reused from agent-deck's
install_agent_ui.py: download/extract into a staging dir first, and only
remove the existing install once the replacement is verified in place.

Run:
  pytest python/tests/test_self_update.py -v
"""

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python" / "scripts" / "setup"))

import self_update as su  # noqa: E402


def _dest_name() -> str:
    return "agent-ui.exe" if sys.platform == "win32" else "agent-ui.app"


def _asset_name() -> str:
    return "agent-ui-win.zip" if sys.platform == "win32" else "agent-ui-mac.zip"


def _fake_release(tag: str, asset_url: str = "https://example.com/asset.zip") -> dict:
    return {
        "tag_name": tag,
        "assets": [{"name": _asset_name(), "browser_download_url": asset_url}],
    }


def _make_fake_zip(zip_path: Path) -> None:
    name = "agent-ui.exe" if sys.platform == "win32" else "agent-ui.app"
    with zipfile.ZipFile(zip_path, "w") as zf:
        if sys.platform == "win32":
            zf.writestr(name, b"fake exe content")
        else:
            zf.writestr(f"{name}/Contents/MacOS/agent-ui", b"#!/bin/sh\necho hi\n")


@pytest.fixture
def project_root(tmp_path, monkeypatch):
    monkeypatch.setattr(su, "PROJECT_ROOT", tmp_path)
    return tmp_path


class TestCheck:
    def test_reports_update_available_when_no_marker(self, project_root, monkeypatch):
        monkeypatch.setattr(su, "_fetch_latest_release", lambda: _fake_release("v0.1.0"))
        available, installed, latest = su.check()
        assert available is True
        assert installed == ""
        assert latest == "v0.1.0"

    def test_reports_up_to_date_when_marker_matches(self, project_root, monkeypatch):
        (project_root / f"{_dest_name()}.version").write_text("v0.1.0")
        monkeypatch.setattr(su, "_fetch_latest_release", lambda: _fake_release("v0.1.0"))
        available, installed, latest = su.check()
        assert available is False
        assert installed == "v0.1.0"


class TestApply:
    def test_skips_download_when_already_up_to_date(self, project_root, monkeypatch):
        (project_root / f"{_dest_name()}.version").write_text("v0.1.0")
        monkeypatch.setattr(su, "_fetch_latest_release", lambda: _fake_release("v0.1.0"))

        def fail_if_called(cmd, *a, **kw):
            raise AssertionError("curl should not be invoked when already up to date")

        monkeypatch.setattr(su.subprocess, "run", fail_if_called)
        su.apply()  # must return early, not raise

    def test_applies_update_and_writes_marker(self, project_root, monkeypatch):
        monkeypatch.setattr(su, "_fetch_latest_release", lambda: _fake_release("v0.2.0"))

        def fake_run(cmd, *a, **kw):
            if cmd[0] == "curl":
                _make_fake_zip(Path(cmd[-1]))
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(su.subprocess, "run", fake_run)

        su.apply()

        dest = project_root / _dest_name()
        marker = project_root / f"{_dest_name()}.version"
        assert dest.exists()
        assert marker.read_text().strip() == "v0.2.0"

    def test_curl_has_connect_and_max_time_limits(self, project_root, monkeypatch):
        """Regression test: a stalled network connection (no active refusal,
        just silence) must not hang apply() forever — hit for real via a
        confused agy skill invocation (`/update --test`, an argument the
        GitHub-Releases-based self_update.py has no concept of)."""
        monkeypatch.setattr(su, "_fetch_latest_release", lambda: _fake_release("v0.2.0"))

        captured = {}

        def fake_run(cmd, *a, **kw):
            if cmd[0] == "curl":
                captured["cmd"] = cmd
                _make_fake_zip(Path(cmd[-1]))
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(su.subprocess, "run", fake_run)

        su.apply()

        assert "--connect-timeout" in captured["cmd"], "curl call has no connect timeout"
        assert "--max-time" in captured["cmd"], "curl call has no overall time limit"

    def test_failed_download_preserves_existing_install(self, project_root, monkeypatch):
        dest = project_root / _dest_name()
        if sys.platform == "win32":
            dest.write_text("old binary")
        else:
            dest.mkdir()
            (dest / "marker.txt").write_text("old install")
        (project_root / f"{_dest_name()}.version").write_text("v0.1.0")

        monkeypatch.setattr(su, "_fetch_latest_release", lambda: _fake_release("v0.2.0"))

        def fake_run(cmd, *a, **kw):
            raise subprocess.CalledProcessError(1, cmd)

        monkeypatch.setattr(su.subprocess, "run", fake_run)

        with pytest.raises(subprocess.CalledProcessError):
            su.apply()

        assert dest.exists(), (
            "apply() removed the existing install before confirming the "
            "replacement download succeeded."
        )
