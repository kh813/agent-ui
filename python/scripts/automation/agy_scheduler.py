#!/usr/bin/env python3
"""
Cross-platform scheduler for headless agy prompts (create/list/edit/enable/
disable/delete).

Every task this module creates lives in a dedicated, agent-ui-owned
namespace, so list/enable/disable/delete only ever see and touch tasks
created here — never any other cron entry, LaunchAgent, or Scheduled Task
already on the machine:

  - macOS:   LaunchAgent label prefix "com.agent-ui.agy." under
             ~/Library/LaunchAgents/
  - Windows: Task Scheduler folder \\AgentUI\\AGY\\

A small JSON sidecar per task (under python/scripts/automation/scheduled/, not
committed to git) is the source of truth for display/editing — the OS-level
registration is derived from it and can be regenerated at any time.

Usage (see the `agy-schedule` skill for the guided flow):
  python3 agy_scheduler.py create <name> --prompt "..." --daily HH:MM
  python3 agy_scheduler.py create <name> --prompt "..." --weekly MON,WED,FRI HH:MM
  python3 agy_scheduler.py list
  python3 agy_scheduler.py enable <name>
  python3 agy_scheduler.py disable <name>
  python3 agy_scheduler.py delete <name>
"""
import argparse
import json
import plistlib
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR    = Path(__file__).resolve().parent
_PROJECT_ROOT  = _SCRIPT_DIR.parents[2]
_RUNNER_SCRIPT = _SCRIPT_DIR / "agy_scheduled_prompt.py"

_LABEL_PREFIX = "com.agent-ui.agy."
_TASK_FOLDER  = r"AgentUI\AGY"

# Overridable at module level (tests monkeypatch these instead of touching
# the real filesystem / real launchd / real Task Scheduler).
_SIDECAR_ROOT       = _SCRIPT_DIR / "scheduled"
_LAUNCH_AGENTS_ROOT = Path.home() / "Library" / "LaunchAgents"

_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_WEEKDAYS = {"MON": 1, "TUE": 2, "WED": 3, "THU": 4, "FRI": 5, "SAT": 6, "SUN": 0}


def _validate_name(name: str) -> None:
    if not _NAME_RE.match(name):
        raise ValueError("Task name must be alphanumeric with '-'/'_' only.")


def _validate_time(time_str: str):
    m = re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", time_str)
    if not m:
        raise ValueError("Time must be in 24h HH:MM format.")
    return int(m.group(1)), int(m.group(2))


def _python_for_task() -> str:
    venv_py = _PROJECT_ROOT / "venv" / ("Scripts" if sys.platform == "win32" else "bin") \
        / ("python.exe" if sys.platform == "win32" else "python3")
    return str(venv_py) if venv_py.exists() else sys.executable


# ── Sidecar metadata (source of truth for display) ─────────────────────────

def _sidecar_path(name: str) -> Path:
    _SIDECAR_ROOT.mkdir(parents=True, exist_ok=True)
    return _SIDECAR_ROOT / f"{name}.json"


def _write_sidecar(name, prompt, frequency, time_str, weekdays, enabled=True) -> dict:
    data = {
        "name": name, "prompt": prompt, "frequency": frequency,
        "time": time_str, "weekdays": weekdays or [], "enabled": enabled,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    _sidecar_path(name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


def _read_sidecar(name: str):
    p = _sidecar_path(name)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _all_sidecars():
    if not _SIDECAR_ROOT.exists():
        return []
    return sorted(_SIDECAR_ROOT.glob("*.json"))


# ── macOS (launchd) ─────────────────────────────────────────────────────────

def _mac_plist_path(name: str) -> Path:
    return _LAUNCH_AGENTS_ROOT / f"{_LABEL_PREFIX}{name}.plist"


def _mac_register(name, prompt, frequency, hour, minute, weekdays) -> None:
    if frequency == "daily":
        intervals = [{"Hour": hour, "Minute": minute}]
    else:
        intervals = [{"Weekday": _WEEKDAYS[d], "Hour": hour, "Minute": minute} for d in weekdays]

    log_dir = _SCRIPT_DIR / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    plist = {
        "Label": f"{_LABEL_PREFIX}{name}",
        "ProgramArguments": [_python_for_task(), str(_RUNNER_SCRIPT), prompt],
        "StartCalendarInterval": intervals,
        "RunAtLoad": False,
        "StandardOutPath": str(log_dir / f"{name}.out.log"),
        "StandardErrorPath": str(log_dir / f"{name}.err.log"),
        "WorkingDirectory": str(_PROJECT_ROOT),
    }
    path = _mac_plist_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        plistlib.dump(plist, f)
    subprocess.run(["launchctl", "load", str(path)], check=False)


def _mac_unregister(name: str) -> None:
    path = _mac_plist_path(name)
    if path.exists():
        subprocess.run(["launchctl", "unload", str(path)], check=False)
        path.unlink()


def _mac_set_enabled(name: str, enabled: bool) -> None:
    path = _mac_plist_path(name)
    if not path.exists():
        return
    subprocess.run(["launchctl", "load" if enabled else "unload", str(path)], check=False)


def _mac_exists(name: str) -> bool:
    return _mac_plist_path(name).exists()


# ── Windows (Task Scheduler) ────────────────────────────────────────────────

def _win_task_name(name: str) -> str:
    return f"\\{_TASK_FOLDER}\\{name}"


def _win_register(name, prompt, frequency, hour, minute, weekdays) -> None:
    tn = _win_task_name(name)
    tr = f'"{_python_for_task()}" "{_RUNNER_SCRIPT}" "{prompt}"'
    st = f"{hour:02d}:{minute:02d}"
    cmd = ["schtasks", "/Create", "/F", "/TN", tn, "/TR", tr, "/ST", st]
    if frequency == "daily":
        cmd += ["/SC", "DAILY"]
    else:
        cmd += ["/SC", "WEEKLY", "/D", ",".join(weekdays)]
    subprocess.run(cmd, check=True)


def _win_unregister(name: str) -> None:
    subprocess.run(["schtasks", "/Delete", "/TN", _win_task_name(name), "/F"], check=False)


def _win_set_enabled(name: str, enabled: bool) -> None:
    flag = "/ENABLE" if enabled else "/DISABLE"
    subprocess.run(["schtasks", "/Change", "/TN", _win_task_name(name), flag], check=False)


def _win_exists(name: str) -> bool:
    result = subprocess.run(
        ["schtasks", "/Query", "/TN", _win_task_name(name)],
        capture_output=True, check=False,
    )
    return result.returncode == 0


# ── Public API ──────────────────────────────────────────────────────────────

def create(name, prompt, frequency, time_str, weekdays=None) -> dict:
    _validate_name(name)
    if _read_sidecar(name) is not None:
        raise ValueError(f"A scheduled task named '{name}' already exists. Use edit or delete first.")
    hour, minute = _validate_time(time_str)

    if frequency == "daily":
        weekdays = []
    elif frequency == "weekly":
        weekdays = [w.strip().upper() for w in (weekdays or [])]
        bad = [w for w in weekdays if w not in _WEEKDAYS]
        if bad or not weekdays:
            raise ValueError(f"Invalid weekday(s): {bad or '(none given)'}. Use MON/TUE/WED/THU/FRI/SAT/SUN.")
    else:
        raise ValueError("frequency must be 'daily' or 'weekly'.")

    if sys.platform == "darwin":
        _mac_register(name, prompt, frequency, hour, minute, weekdays)
    elif sys.platform == "win32":
        _win_register(name, prompt, frequency, hour, minute, weekdays)
    else:
        raise RuntimeError("agy_scheduler only supports macOS and Windows.")

    return _write_sidecar(name, prompt, frequency, time_str, weekdays, enabled=True)


def edit(name, prompt=None, frequency=None, time_str=None, weekdays=None) -> dict:
    existing = _read_sidecar(name)
    if existing is None:
        raise ValueError(f"No scheduled task named '{name}'.")
    delete(name)
    return create(
        name,
        prompt if prompt is not None else existing["prompt"],
        frequency if frequency is not None else existing["frequency"],
        time_str if time_str is not None else existing["time"],
        weekdays if weekdays is not None else existing["weekdays"],
    )


def delete(name: str) -> None:
    if sys.platform == "darwin":
        _mac_unregister(name)
    elif sys.platform == "win32":
        _win_unregister(name)
    p = _sidecar_path(name)
    if p.exists():
        p.unlink()


def set_enabled(name: str, enabled: bool) -> dict:
    existing = _read_sidecar(name)
    if existing is None:
        raise ValueError(f"No scheduled task named '{name}'.")
    if sys.platform == "darwin":
        _mac_set_enabled(name, enabled)
    elif sys.platform == "win32":
        _win_set_enabled(name, enabled)
    existing["enabled"] = enabled
    _sidecar_path(name).write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return existing


def list_tasks() -> list:
    tasks = []
    for p in _all_sidecars():
        data = json.loads(p.read_text(encoding="utf-8"))
        if sys.platform == "darwin":
            data["registered"] = _mac_exists(data["name"])
        elif sys.platform == "win32":
            data["registered"] = _win_exists(data["name"])
        else:
            data["registered"] = False
        tasks.append(data)
    return tasks


# ── CLI ──────────────────────────────────────────────────────────────────────

def _print_task(t: dict) -> None:
    schedule = t["time"] if t["frequency"] == "daily" else f"{','.join(t['weekdays'])} {t['time']}"
    status = "enabled" if t["enabled"] else "disabled"
    if not t.get("registered", True):
        status += " (⚠ not registered with OS — recreate it)"
    print(f"- {t['name']} [{t['frequency']}: {schedule}] ({status})")
    print(f"    prompt: {t['prompt']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage scheduled headless agy prompts.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create")
    p_create.add_argument("name")
    p_create.add_argument("--prompt", required=True)
    p_create.add_argument("--daily", metavar="HH:MM")
    p_create.add_argument("--weekly", nargs=2, metavar=("DAYS", "HH:MM"))

    p_edit = sub.add_parser("edit")
    p_edit.add_argument("name")
    p_edit.add_argument("--prompt")
    p_edit.add_argument("--daily", metavar="HH:MM")
    p_edit.add_argument("--weekly", nargs=2, metavar=("DAYS", "HH:MM"))

    sub.add_parser("list")

    for cmd in ("enable", "disable", "delete"):
        p = sub.add_parser(cmd)
        p.add_argument("name")

    args = parser.parse_args()

    if args.command == "create":
        if bool(args.daily) == bool(args.weekly):
            parser.error("create requires exactly one of --daily HH:MM or --weekly DAYS HH:MM")
        if args.daily:
            task = create(args.name, args.prompt, "daily", args.daily)
        else:
            days, time_str = args.weekly
            task = create(args.name, args.prompt, "weekly", time_str, days.split(","))
        _print_task(task)

    elif args.command == "edit":
        frequency = time_str = weekdays = None
        if args.daily:
            frequency, time_str, weekdays = "daily", args.daily, []
        elif args.weekly:
            days, time_str = args.weekly
            frequency, weekdays = "weekly", days.split(",")
        task = edit(args.name, prompt=args.prompt, frequency=frequency, time_str=time_str, weekdays=weekdays)
        _print_task(task)

    elif args.command == "list":
        tasks = list_tasks()
        if not tasks:
            print("No scheduled agy tasks.")
        for t in tasks:
            _print_task(t)

    elif args.command == "enable":
        _print_task(set_enabled(args.name, True))

    elif args.command == "disable":
        _print_task(set_enabled(args.name, False))

    elif args.command == "delete":
        delete(args.name)
        print(f"Deleted: {args.name}")


if __name__ == "__main__":
    main()
