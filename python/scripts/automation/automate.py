"""Cross-platform launcher for automation scripts."""
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

SCRIPT_DIR    = Path(__file__).resolve().parent
PROJECT_ROOT  = SCRIPT_DIR.parents[2]   # automation/ -> scripts/ -> python/ -> root
VENV_DIR      = PROJECT_ROOT / "venv"
REQUIREMENTS  = SCRIPT_DIR / "requirements.txt"
MARKER        = VENV_DIR / ".installed"
LOG_FILE      = SCRIPT_DIR / "logs" / "automator.log"

# Target scripts live under whichever root matches their distribution scope
# (this file itself is public, but some ACTIONS below dispatch to
# company-internal or personal scripts) — search all three in order.
AUTOMATION_DIRS = [
    SCRIPT_DIR,
    PROJECT_ROOT / "src-internal" / "scripts" / "automation",
    PROJECT_ROOT / "src-personal" / "scripts" / "automation",
]

ACTIONS = {
    "clockin":          "routine.py",
    "clockout":         "routine.py",
    "docusign":         "download.py",
    "actionpassport":   "download.py",
    "sansan":           "download.py",
    "ext-devices":      "download.py",
    "update-user-data": "download.py",
    "portal":           "portal_search.py",
    "calendar":         "gcalendar.py",
}


def _find_script(filename: str) -> Path:
    for automation_dir in AUTOMATION_DIRS:
        candidate = automation_dir / filename
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"{filename} not found in any of: {[str(d) for d in AUTOMATION_DIRS]}"
    )


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    # Rotate at 10,000 lines
    text = LOG_FILE.read_text(encoding="utf-8")
    lines = text.splitlines()
    if len(lines) > 10_000:
        LOG_FILE.write_text("\n".join(lines[-10_000:]) + "\n", encoding="utf-8")


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python3"


def setup_venv() -> None:
    python = venv_python()

    if not VENV_DIR.is_dir():
        log("venv を作成しています...")
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True,
                        stdin=subprocess.DEVNULL)

    if not MARKER.exists() or REQUIREMENTS.stat().st_mtime > MARKER.stat().st_mtime:
        log("依存ライブラリをインストールしています...")
        subprocess.run(
            [str(python), "-m", "pip", "install", "-q", "--no-cache-dir", "-r", str(REQUIREMENTS)],
            check=True, stdin=subprocess.DEVNULL,
        )
        subprocess.run(
            [str(python), "-m", "playwright", "install", "chromium"],
            capture_output=True, stdin=subprocess.DEVNULL,
        )
        MARKER.touch()
        log("インストール完了")


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print("\nUsage: python automate.py <action> [args...]")
        print("\n  出退勤:  clockin / clockout")
        print("  DL:     docusign / actionpassport / sansan / ext-devices / update-user-data")
        print("  検索:   portal <query>")
        print("  予定:   calendar [--days N]\n")
        sys.exit(0 if args else 1)

    action = args[0]
    if action not in ACTIONS:
        print(f"不明なオプションです: {action}")
        sys.exit(1)

    try:
        target = _find_script(ACTIONS[action])
    except FileNotFoundError as e:
        log(f"エラー: {e}")
        sys.exit(1)

    try:
        setup_venv()
    except subprocess.CalledProcessError as e:
        log(f"エラー: venv のセットアップに失敗しました: {e}")
        sys.exit(1)

    log(f"実行: {target.name} {' '.join(args)}")
    env = {**os.environ, "PYTHONWARNINGS": "ignore", "PYTHONIOENCODING": "utf-8"}

    result = subprocess.run(
        [str(venv_python()), str(target)] + args,
        cwd=str(SCRIPT_DIR),
        env=env,
        stdin=subprocess.DEVNULL,
    )

    if result.returncode == 0:
        log(f"完了: {action}")
    else:
        log(f"異常終了: exit={result.returncode}")

    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
