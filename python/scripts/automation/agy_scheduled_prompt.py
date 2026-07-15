#!/usr/bin/env python3
"""
Headless runner: send a single prompt to agy non-interactively (`agy --print`),
log the result, and deliver it to Chat via notify_chat.py.

Usage:
  python3 agy_scheduled_prompt.py "<prompt>" [--timeout SECONDS]

Not meant to be run interactively — this is the payload invoked by scheduled
tasks created through the `agy-schedule` skill (see agy_scheduler.py).
"""
import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR   = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parents[2]
_LOG_FILE     = _SCRIPT_DIR / "logs" / "agy_scheduled.log"

sys.path.insert(0, str(_SCRIPT_DIR))


def _agy_binary() -> str:
    win_bin = _PROJECT_ROOT / "app" / "bin" / "agy.exe"
    mac_bin = _PROJECT_ROOT / "app" / "bin" / "agy"
    if win_bin.exists():
        return str(win_bin)
    if mac_bin.exists():
        return str(mac_bin)
    return "agy"  # fall back to PATH


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    # Rotate at 10,000 lines (matches automate.py's convention).
    lines = _LOG_FILE.read_text(encoding="utf-8").splitlines()
    if len(lines) > 10_000:
        _LOG_FILE.write_text("\n".join(lines[-10_000:]) + "\n", encoding="utf-8")


def run(prompt: str, timeout_seconds: int = 300) -> int:
    from notify_chat import send

    _log(f"Running scheduled prompt: {prompt!r}")
    try:
        result = subprocess.run(
            [_agy_binary(), "--print", prompt, "--print-timeout", f"{timeout_seconds}s"],
            cwd=str(_PROJECT_ROOT),
            capture_output=True, text=True, timeout=timeout_seconds + 30,
        )
    except subprocess.TimeoutExpired:
        _log("agy --print timed out")
        send(f"⚠️ 定期実行がタイムアウトしました / Scheduled run timed out.\nPrompt: {prompt}")
        return 1

    output = (result.stdout or "").strip() or (result.stderr or "").strip()
    _log(f"agy exit={result.returncode} output={output[:500]!r}")

    if result.returncode != 0:
        send(
            f"⚠️ 定期実行が失敗しました / Scheduled run failed "
            f"(exit {result.returncode}).\n{output[:1500]}"
        )
        return result.returncode

    send(output[:4000] if output else "(空の応答でした / empty response)")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a prompt through agy headlessly and notify Chat."
    )
    parser.add_argument("prompt")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout in seconds (default 300)")
    args = parser.parse_args()
    sys.exit(run(args.prompt, args.timeout))


if __name__ == "__main__":
    main()
