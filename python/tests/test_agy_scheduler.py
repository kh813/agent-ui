"""
Tests for agy_scheduler.py — cross-platform scheduling for headless agy prompts.

All filesystem roots (sidecar dir, LaunchAgents dir) and subprocess.run are
mocked/redirected to tmp_path so tests never touch the real machine's
LaunchAgents, Task Scheduler, or this repo's own scheduled/ directory.

Run:
  venv/bin/pytest python/tests/test_agy_scheduler.py -v
"""

import sys
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

_SRC_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SRC_DIR / "scripts" / "automation"))

import agy_scheduler as sch  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_roots(tmp_path, monkeypatch):
    """Redirect all persistent state under tmp_path and stub out subprocess."""
    monkeypatch.setattr(sch, "_SIDECAR_ROOT", tmp_path / "scheduled")
    monkeypatch.setattr(sch, "_LAUNCH_AGENTS_ROOT", tmp_path / "LaunchAgents")
    mock_run = MagicMock(return_value=MagicMock(returncode=0))
    monkeypatch.setattr(sch.subprocess, "run", mock_run)
    yield mock_run


class TestCreateDaily:
    def test_mac_creates_plist_and_sidecar(self, monkeypatch, _isolated_roots):
        monkeypatch.setattr(sch.sys, "platform", "darwin")

        task = sch.create("forex", "check forex rates", "daily", "09:00")

        assert task["name"] == "forex"
        assert task["enabled"] is True
        plist_path = sch._mac_plist_path("forex")
        assert plist_path.exists()
        _isolated_roots.assert_any_call(["launchctl", "load", str(plist_path)], check=False)

    def test_windows_creates_task_and_sidecar(self, monkeypatch, _isolated_roots):
        monkeypatch.setattr(sch.sys, "platform", "win32")

        task = sch.create("forex", "check forex rates", "daily", "09:00")

        assert task["name"] == "forex"
        create_call = _isolated_roots.call_args_list[0]
        cmd = create_call.args[0]
        assert "/SC" in cmd and "DAILY" in cmd
        assert sch._win_task_name("forex") in cmd

    def test_duplicate_name_rejected(self, monkeypatch):
        monkeypatch.setattr(sch.sys, "platform", "darwin")
        sch.create("forex", "prompt one", "daily", "09:00")

        with pytest.raises(ValueError, match="already exists"):
            sch.create("forex", "prompt two", "daily", "10:00")

    def test_invalid_time_rejected(self, monkeypatch):
        monkeypatch.setattr(sch.sys, "platform", "darwin")
        with pytest.raises(ValueError, match="HH:MM"):
            sch.create("forex", "prompt", "daily", "25:99")

    def test_invalid_name_rejected(self, monkeypatch):
        monkeypatch.setattr(sch.sys, "platform", "darwin")
        with pytest.raises(ValueError, match="alphanumeric"):
            sch.create("has spaces", "prompt", "daily", "09:00")


class TestCreateWeekly:
    def test_mac_weekly_intervals(self, monkeypatch):
        monkeypatch.setattr(sch.sys, "platform", "darwin")

        task = sch.create("forex", "check forex", "weekly", "09:00", ["MON", "WED", "FRI"])

        assert task["weekdays"] == ["MON", "WED", "FRI"]
        with open(sch._mac_plist_path("forex"), "rb") as f:
            import plistlib
            plist = plistlib.load(f)
        assert len(plist["StartCalendarInterval"]) == 3
        assert {i["Weekday"] for i in plist["StartCalendarInterval"]} == {1, 3, 5}

    def test_invalid_weekday_rejected(self, monkeypatch):
        monkeypatch.setattr(sch.sys, "platform", "darwin")
        with pytest.raises(ValueError, match="Invalid weekday"):
            sch.create("forex", "prompt", "weekly", "09:00", ["MONDAY"])

    def test_empty_weekdays_rejected(self, monkeypatch):
        monkeypatch.setattr(sch.sys, "platform", "darwin")
        with pytest.raises(ValueError, match="Invalid weekday"):
            sch.create("forex", "prompt", "weekly", "09:00", [])


class TestListOnlyShowsOwnedTasks:
    def test_list_reflects_only_sidecar_entries(self, monkeypatch):
        monkeypatch.setattr(sch.sys, "platform", "darwin")
        sch.create("forex", "check forex", "daily", "09:00")
        sch.create("news", "summarize news", "weekly", "08:00", ["MON"])

        names = {t["name"] for t in sch.list_tasks()}

        assert names == {"forex", "news"}

    def test_list_flags_task_missing_from_os(self, monkeypatch):
        monkeypatch.setattr(sch.sys, "platform", "darwin")
        sch.create("forex", "check forex", "daily", "09:00")
        sch._mac_plist_path("forex").unlink()  # simulate manual deletion outside our tooling

        tasks = sch.list_tasks()

        assert tasks[0]["registered"] is False


class TestEnableDisable:
    def test_disable_then_enable_mac(self, monkeypatch, _isolated_roots):
        monkeypatch.setattr(sch.sys, "platform", "darwin")
        sch.create("forex", "check forex", "daily", "09:00")

        disabled = sch.set_enabled("forex", False)
        assert disabled["enabled"] is False
        _isolated_roots.assert_any_call(
            ["launchctl", "unload", str(sch._mac_plist_path("forex"))], check=False
        )

        enabled = sch.set_enabled("forex", True)
        assert enabled["enabled"] is True

    def test_missing_task_raises(self, monkeypatch):
        monkeypatch.setattr(sch.sys, "platform", "darwin")
        with pytest.raises(ValueError, match="No scheduled task"):
            sch.set_enabled("does-not-exist", True)


class TestEdit:
    def test_edit_changes_prompt_and_time(self, monkeypatch):
        monkeypatch.setattr(sch.sys, "platform", "darwin")
        sch.create("forex", "old prompt", "daily", "09:00")

        updated = sch.edit("forex", prompt="new prompt", time_str="10:30")

        assert updated["prompt"] == "new prompt"
        assert updated["time"] == "10:30"
        assert updated["frequency"] == "daily"  # unchanged fields preserved


class TestDelete:
    def test_delete_removes_plist_and_sidecar(self, monkeypatch):
        monkeypatch.setattr(sch.sys, "platform", "darwin")
        sch.create("forex", "check forex", "daily", "09:00")
        plist_path = sch._mac_plist_path("forex")
        assert plist_path.exists()

        sch.delete("forex")

        assert not plist_path.exists()
        assert sch._read_sidecar("forex") is None
