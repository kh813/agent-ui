"""
Tests for gcalendar.py — locale handling and pure logic.

Run:
  cd <project-root>
  venv/bin/pip install pytest          # first time only
  venv/bin/pytest python/tests/test_gcalendar.py -v
"""

import sys
import pytest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

# ── path / mock setup (must happen before importing gcalendar) ─
_SRC_DIR  = Path(__file__).resolve().parents[1]
_AUTO_DIR = _SRC_DIR / "scripts" / "automation"
sys.path.insert(0, str(_AUTO_DIR))
sys.path.insert(0, str(_SRC_DIR))

for _mod in [
    "googleapiclient", "googleapiclient.discovery",
    "google", "google.oauth2", "google.oauth2.credentials",
    "google_auth_oauthlib", "google_auth_oauthlib.flow",
    "google.auth", "google.auth.transport", "google.auth.transport.requests",
]:
    sys.modules.setdefault(_mod, MagicMock())

_config_mock = MagicMock()
_config_mock.OAUTH_CLIENT_ID     = "test_id"
_config_mock.OAUTH_CLIENT_SECRET = "test_secret"
_config_mock.USER_EMAIL          = "test@example.com"
sys.modules["config"] = _config_mock

_logger_mock = MagicMock()
_logger_mock.get_logger.return_value = MagicMock()
_logger_mock.log_startup = MagicMock()
sys.modules["scripts"]        = MagicMock()
sys.modules["scripts.auth"]   = MagicMock()
sys.modules["scripts.logger"] = _logger_mock

import gcalendar  # noqa: E402


# ── _MY_TASKS_NAMES ────────────────────────────────────────────

# (language, expected list name returned by Google Tasks API)
_EXPECTED_MY_TASKS = [
    ("English",             "My Tasks"),
    ("Japanese",            "マイタスク"),
    ("Korean",              "내 할 일"),
    ("Simplified Chinese",  "我的任务"),
    ("Traditional Chinese", "我的工作"),
    ("French",              "Mes tâches"),
    ("German",              "Meine Aufgaben"),
    ("Portuguese (BR)",     "Minhas tarefas"),
    ("Spanish",             "Mis tareas"),
    ("Italian",             "Le mie attività"),
    ("Malay/Indonesian",    "Tugas Saya"),
    ("Dutch",               "Mijn taken"),
    ("Thai",                "งานของฉัน"),
    ("Arabic",              "مهامي"),
    ("Russian",             "Мои задачи"),
]


class TestMyTasksNames:
    @pytest.mark.parametrize("lang,name", _EXPECTED_MY_TASKS)
    def test_default_list_recognized(self, lang, name):
        assert name in gcalendar._MY_TASKS_NAMES, (
            f"{lang}: '{name}' not in _MY_TASKS_NAMES"
        )

    @pytest.mark.parametrize("name", [
        "Project Alpha", "仕事", "개인 업무", "工作", "Unknown List", "",
    ])
    def test_custom_list_not_recognized(self, name):
        assert name not in gcalendar._MY_TASKS_NAMES, (
            f"'{name}' should NOT be in _MY_TASKS_NAMES"
        )

    def test_no_duplicates(self):
        names = list(gcalendar._MY_TASKS_NAMES)
        assert len(names) == len(set(names)), "Duplicate entries in _MY_TASKS_NAMES"


# ── format_day: list_label ─────────────────────────────────────

_MONDAY = date(2026, 5, 18)  # known Monday


class TestFormatDayListLabel:
    @pytest.mark.parametrize("lang,list_name", _EXPECTED_MY_TASKS)
    def test_default_list_label_hidden(self, lang, list_name):
        lines = gcalendar.format_day(_MONDAY, [], [("Task A", list_name)], is_today=False)
        task_line = next(l for l in lines if "Task A" in l)
        assert f"[{list_name}]" not in task_line, (
            f"{lang}: default list name '{list_name}' should be hidden"
        )

    def test_custom_list_label_shown(self):
        lines = gcalendar.format_day(_MONDAY, [], [("Task B", "Project Alpha")], is_today=False)
        task_line = next(l for l in lines if "Task B" in l)
        assert "[Project Alpha]" in task_line

    def test_empty_list_name_hidden(self):
        lines = gcalendar.format_day(_MONDAY, [], [("Task C", "")], is_today=False)
        task_line = next(l for l in lines if "Task C" in l)
        assert "[" not in task_line

    def test_today_marker(self):
        lines = gcalendar.format_day(_MONDAY, [], [], is_today=True)
        assert "Today" in lines[0]

    def test_no_events_message(self):
        lines = gcalendar.format_day(_MONDAY, [], [], is_today=False)
        assert any("No events" in l for l in lines)

    def test_weekday_english(self):
        lines = gcalendar.format_day(_MONDAY, [], [], is_today=False)
        assert "Mon" in lines[0]


# ── WEEKDAY_EN: all 7 days ─────────────────────────────────────

class TestWeekdayEnglish:
    @pytest.mark.parametrize("offset,expected", [
        (0, "Mon"), (1, "Tue"), (2, "Wed"), (3, "Thu"),
        (4, "Fri"), (5, "Sat"), (6, "Sun"),
    ])
    def test_all_weekdays_in_output(self, offset, expected):
        from datetime import timedelta
        d = _MONDAY + timedelta(days=offset)
        lines = gcalendar.format_day(d, [], [], is_today=False)
        assert expected in lines[0], f"Expected '{expected}' in header for offset +{offset}d"

    def test_weekday_array_length(self):
        assert len(gcalendar.WEEKDAY_EN) == 7

    def test_weekday_array_no_japanese(self):
        for wd in gcalendar.WEEKDAY_EN:
            assert wd.isascii(), f"Non-ASCII weekday found: '{wd}'"


# ── format_day: calendar events ───────────────────────────────

def _timed_event(summary, start="2026-05-19T10:00:00", end="2026-05-19T11:00:00", location=""):
    ev = {"summary": summary,
          "start": {"dateTime": start}, "end": {"dateTime": end}}
    if location:
        ev["location"] = location
    return ev

def _allday_event(summary):
    return {"summary": summary,
            "start": {"date": "2026-05-19"}, "end": {"date": "2026-05-20"}}

_TUESDAY = date(2026, 5, 19)

class TestFormatDayEvents:
    def test_timed_event_shows_time_range(self):
        lines = gcalendar.format_day(
            _TUESDAY, [_timed_event("Meeting", "2026-05-19T10:00:00", "2026-05-19T11:30:00")],
            [], is_today=False,
        )
        assert any("10:00 - 11:30" in l for l in lines)

    def test_all_day_event_shows_all_day(self):
        lines = gcalendar.format_day(_TUESDAY, [_allday_event("Holiday")], [], is_today=False)
        assert any("All day" in l for l in lines)

    def test_deadline_event_shows_mark(self):
        lines = gcalendar.format_day(
            _TUESDAY, [_timed_event("Project deadline")], [], is_today=False
        )
        assert any("Deadline" in l for l in lines)

    def test_non_deadline_event_no_mark(self):
        lines = gcalendar.format_day(
            _TUESDAY, [_timed_event("Team meeting")], [], is_today=False
        )
        assert not any("Deadline" in l for l in lines)

    def test_location_shown(self):
        lines = gcalendar.format_day(
            _TUESDAY, [_timed_event("Sync", location="Tokyo Office")], [], is_today=False
        )
        assert any("Tokyo Office" in l for l in lines)

    def test_no_location_no_pin(self):
        lines = gcalendar.format_day(_TUESDAY, [_timed_event("Sync")], [], is_today=False)
        assert not any("📍" in l for l in lines)

    def test_missing_summary_falls_back(self):
        ev = {"start": {"dateTime": "2026-05-19T09:00:00"},
              "end":   {"dateTime": "2026-05-19T10:00:00"}}
        lines = gcalendar.format_day(_TUESDAY, [ev], [], is_today=False)
        assert any("No title" in l for l in lines)

    def test_event_and_task_both_shown(self):
        lines = gcalendar.format_day(
            _TUESDAY,
            [_timed_event("Standup")],
            [("My task", "My Tasks")],
            is_today=False,
        )
        assert any("Standup" in l for l in lines)
        assert any("My task" in l for l in lines)


# ── _is_deadline ───────────────────────────────────────────────

class TestIsDeadline:
    @pytest.mark.parametrize("summary", [
        "Project due", "Deadline tomorrow", "提出期限", "〆切", "納期確認",
        "締め切り", "Due: report", "DEADLINE", "期限: 5月末",
    ])
    def test_deadline_detected(self, summary):
        assert gcalendar._is_deadline(summary), f"Should detect deadline: '{summary}'"

    @pytest.mark.parametrize("summary", [
        "Team meeting", "Lunch with Alice", "1on1", "Birthday party", "Holiday",
        "Product review", "週次ミーティング",
    ])
    def test_non_deadline_not_detected(self, summary):
        assert not gcalendar._is_deadline(summary), f"Should not detect deadline: '{summary}'"


# ── _fmt_time ──────────────────────────────────────────────────

class TestFmtTime:
    def test_all_day_returns_all_day(self):
        assert gcalendar._fmt_time("2026-05-19", True) == "All day"

    def test_datetime_formats_as_hhmm(self):
        assert gcalendar._fmt_time("2026-05-19T09:30:00", False) == "09:30"

    def test_invalid_string_falls_back(self):
        assert gcalendar._fmt_time("not-a-date", False) == "not-a-date"

    def test_all_day_flag_overrides_value(self):
        assert gcalendar._fmt_time("2026-05-19T14:00:00", True) == "All day"
