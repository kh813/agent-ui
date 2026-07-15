#!/usr/bin/env python3
"""
Google Calendar + Google Tasks 今日・今後の予定・タスク取得スクリプト
Usage:
  python3 gcalendar.py            # 今日 + 次の3営業日
  python3 gcalendar.py --days 5  # 今日 + 次の5営業日
"""

import sys
import os
from datetime import datetime, timedelta, date
from pathlib import Path

# Re-exec with venv Python if google packages are not available.
def _reexec_with_venv():
    try:
        import googleapiclient  # noqa: F401
    except ImportError:
        script_dir = Path(__file__).resolve().parent
        project_root = script_dir.parents[2]
        if sys.platform == "win32":
            venv_python = project_root / "venv" / "Scripts" / "python.exe"
        else:
            venv_python = project_root / "venv" / "bin" / "python3"
        if venv_python.exists():
            os.environ["PYTHONWARNINGS"] = "ignore"
            os.execv(str(venv_python), [str(venv_python)] + sys.argv)
        else:
            print("[ERROR] venv not found. Please run setup first.")
            sys.exit(1)

_reexec_with_venv()

# ============================================================
# Configuration (same OAuth app as Drive integration)
# ============================================================
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR.parents[2] / "python"))
from config import OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET, USER_EMAIL  # noqa: E402
from scripts.auth import run_auth_flow  # noqa: E402
from scripts.logger import get_logger, log_startup  # noqa: E402

_log = get_logger("gcalendar")
log_startup(_log)
# ============================================================

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/tasks.readonly",
]
TOKEN_PATH = Path.home() / ".gemini" / "agent_ui_calendar_token.json"

CLIENT_CONFIG = {
    "installed": {
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"],
    }
}

WEEKDAY_EN = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

DEADLINE_KEYWORDS = ["締め切り", "期限", "due", "deadline", "〆切", "提出", "納期"]

# Google Tasks default list name varies by account language.
# Add entries here if a language is missing.
_MY_TASKS_NAMES = {
    "My Tasks",         # English
    "マイタスク",        # Japanese
    "내 할 일",          # Korean
    "我的任务",          # Simplified Chinese
    "我的工作",          # Traditional Chinese (Taiwan)
    "Mes tâches",       # French
    "Meine Aufgaben",   # German
    "Minhas tarefas",   # Portuguese (Brazil)
    "Mis tareas",       # Spanish
    "Le mie attività",  # Italian
    "Tugas Saya",       # Malay / Indonesian
    "Mijn taken",       # Dutch
    "งานของฉัน",        # Thai
    "مهامي",            # Arabic
    "Мои задачи",       # Russian
}


def _get_credentials():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request

    creds = None
    if TOKEN_PATH.exists():
        # Load without passing SCOPES to avoid scope mismatch on refresh
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH))
        # Delete token and re-auth if it doesn't cover all required scopes
        if creds.scopes and not all(s in creds.scopes for s in SCOPES):
            TOKEN_PATH.unlink()
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                _log.warning("token refresh failed, re-authenticating: %s", e)
                creds = None
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
            creds = run_auth_flow(flow, login_hint=USER_EMAIL or None)
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())

    return creds


def _business_days_range(start: date, n_extra: int) -> list[date]:
    """Return start date + n_extra subsequent business days (Mon-Fri)."""
    days = [start]
    current = start
    while len(days) - 1 < n_extra:
        current += timedelta(days=1)
        if current.weekday() < 5:
            days.append(current)
    return days


def _is_deadline(summary: str) -> bool:
    lower = summary.lower()
    return any(kw in lower for kw in DEADLINE_KEYWORDS)


def _fmt_time(dt_str: str, is_all_day: bool) -> str:
    if is_all_day:
        return "All day"
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%H:%M")
    except Exception:
        return dt_str


# ── Calendar ──────────────────────────────────────────────────

def fetch_events(cal_service, target_date: date) -> list[dict]:
    start = datetime.combine(target_date, datetime.min.time()).isoformat() + "Z"
    end   = datetime.combine(target_date, datetime.max.time()).isoformat() + "Z"

    result = cal_service.events().list(
        calendarId="primary",
        timeMin=start,
        timeMax=end,
        singleEvents=True,
        orderBy="startTime",
        maxResults=50,
    ).execute()

    return result.get("items", [])


def format_day(target_date: date, events: list[dict],
               tasks_today: list[tuple], is_today: bool) -> list[str]:
    wd = WEEKDAY_EN[target_date.weekday()]
    label = f"📅 {target_date.strftime('%m/%d')} ({wd}){'  ← Today' if is_today else ''}"
    lines = [label]

    if not events and not tasks_today:
        lines.append("  No events or tasks")
        return lines

    for ev in events:
        start_info = ev.get("start", {})
        end_info   = ev.get("end", {})
        is_all_day = "date" in start_info and "dateTime" not in start_info

        start_str = _fmt_time(start_info.get("dateTime", start_info.get("date", "")), is_all_day)
        end_str   = _fmt_time(end_info.get("dateTime", end_info.get("date", "")), is_all_day)
        summary   = ev.get("summary", "(No title)")
        location  = ev.get("location", "")

        time_part     = "All day" if is_all_day else f"{start_str} - {end_str}"
        deadline_mark = " ⚠️ Deadline" if _is_deadline(summary) else ""
        loc_part      = f"  📍{location}" if location else ""

        lines.append(f"  {time_part}  {summary}{deadline_mark}{loc_part}")

    for title, list_name in tasks_today:
        list_label = f" [{list_name}]" if list_name and list_name not in _MY_TASKS_NAMES else ""
        lines.append(f"  ☑ {title}{list_label}")

    return lines


# ── Tasks ─────────────────────────────────────────────────────

def fetch_tasks(tasks_service, target_dates: list[date]) -> dict:
    """
    Returns:
      overdue:      [(due_date, title, list_name), ...]  — overdue tasks
      due_by_date:  {date: [(title, list_name), ...]}    — tasks due within range
    """
    today     = target_dates[0]
    last_date = target_dates[-1]

    overdue: list[tuple] = []
    due_by_date: dict[date, list[tuple]] = {}

    try:
        tl_result = tasks_service.tasklists().list(maxResults=20).execute()
    except Exception as e:
        print(f"  [WARN] Failed to fetch Google Tasks: {e}")
        print("  Please check that the Google Tasks API is enabled.")
        return {"overdue": overdue, "due_by_date": due_by_date}

    for tl in tl_result.get("items", []):
        tl_id    = tl["id"]
        tl_title = tl.get("title", "")

        try:
            t_result = tasks_service.tasks().list(
                tasklist=tl_id,
                showCompleted=False,
                showHidden=False,
                maxResults=100,
            ).execute()
        except Exception:
            continue

        for task in t_result.get("items", []):
            if task.get("status") == "completed":
                continue
            title = task.get("title", "").strip()
            if not title:
                continue

            due_str = task.get("due", "")
            if not due_str:
                continue

            try:
                due_date = date.fromisoformat(due_str[:10])
            except ValueError:
                continue

            if due_date < today:
                overdue.append((due_date, title, tl_title))
            elif due_date <= last_date:
                due_by_date.setdefault(due_date, []).append((title, tl_title))

    overdue.sort(key=lambda x: x[0])
    return {"overdue": overdue, "due_by_date": due_by_date}


# ── Main ──────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    n_days = 3
    if "--days" in args:
        idx = args.index("--days")
        try:
            n_days = int(args[idx + 1])
        except (IndexError, ValueError):
            print("Please specify a number after --days.")
            sys.exit(1)

    today        = date.today()
    target_dates = _business_days_range(today, n_days)

    print(f"\n=== Schedule & Tasks (Today + {n_days} business days) ===\n")

    creds = _get_credentials()
    from googleapiclient.discovery import build
    cal_service   = build("calendar", "v3", credentials=creds, cache_discovery=False)
    tasks_service = build("tasks",    "v1", credentials=creds, cache_discovery=False)

    # Fetch tasks for the whole range
    task_data    = fetch_tasks(tasks_service, target_dates)
    due_by_date  = task_data["due_by_date"]
    overdue      = task_data["overdue"]

    # Show overdue tasks first
    if overdue:
        print("=== 🔴 Overdue Tasks ===")
        for due_date, title, list_name in overdue:
            wd         = WEEKDAY_EN[due_date.weekday()]
            list_label = f" [{list_name}]" if list_name and list_name not in _MY_TASKS_NAMES else ""
            print(f"  {due_date.strftime('%m/%d')} ({wd}) ☑ {title}{list_label}")
        print()

    all_deadlines = []

    for i, d in enumerate(target_dates):
        events      = fetch_events(cal_service, d)
        tasks_today = due_by_date.get(d, [])
        lines       = format_day(d, events, tasks_today, is_today=(i == 0))
        print("\n".join(lines))
        print()

        for ev in events:
            summary = ev.get("summary", "")
            if _is_deadline(summary):
                start_info = ev.get("start", {})
                is_all_day = "date" in start_info and "dateTime" not in start_info
                start_str  = _fmt_time(
                    start_info.get("dateTime", start_info.get("date", "")), is_all_day
                )
                all_deadlines.append((d, start_str, summary))

    if all_deadlines:
        print("=== ⚠️  Deadline List ===")
        for dl_date, dl_time, dl_name in all_deadlines:
            wd = WEEKDAY_EN[dl_date.weekday()]
            print(f"  {dl_date.strftime('%m/%d')} ({wd}) {dl_time}  {dl_name}")
        print()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        _log.error("unhandled exception", exc_info=True)
        raise
