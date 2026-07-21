import os
import sys
import platform
import subprocess
from pathlib import Path

# Windows pipe (agy.exe's pty etc.) makes stdout fall back to CP1252,
# corrupting or crashing on this file's Japanese output (see
# setup_config()'s prompts, skills_list()'s labels). Confirmed for real:
# a user's /update -> preflight.bat -> this script's "config" step printed
# mojibake instead of the intended Japanese text.
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = Path(SCRIPT_DIR).parents[2] / "config.toml"

def run_command(cmd, description=None):
    if description:
        print(f"==> {description}")
    try:
        subprocess.run(cmd, shell=True, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        return False
    return True

def build_skills():
    print("==> Building skill packages...")
    system = platform.system().lower()
    if system == "windows":
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", os.path.join(SCRIPT_DIR, "build-skills.ps1")],
            check=True, stdin=subprocess.DEVNULL,
        )
    else:
        subprocess.run(
            ["bash", os.path.join(SCRIPT_DIR, "build-skills.sh")],
            check=True, stdin=subprocess.DEVNULL,
        )

def setup_venv():
    """Create venv and pre-install all Python dependencies."""
    print("==> Setting up Python virtual environment...")
    project_root = Path(SCRIPT_DIR).parents[2]
    venv_dir = project_root / "venv"

    if not venv_dir.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True,
                        stdin=subprocess.DEVNULL)

    if platform.system().lower() == "windows":
        pip    = venv_dir / "Scripts" / "pip.exe"
        python = venv_dir / "Scripts" / "python.exe"
    else:
        pip    = venv_dir / "bin" / "pip"
        python = venv_dir / "bin" / "python3"

    pip_flags = ["-qq", "--disable-pip-version-check", "--no-cache-dir"]
    # Not used by any of agent-deck's own public skills (the corporate slide-
    # generation feature that used to live here moved entirely to agent-deck
    # in 0.0.11 — see python/scripts/slides/ removal). Kept anyway: a
    # wrapping project's own scripts (e.g. agent-deck's src/scripts/slides/
    # generate_pptx.py) reuse THIS venv rather than maintaining a second one
    # of their own, and expect python-pptx to already be here.
    subprocess.run([str(python), "-m", "pip", "install", *pip_flags, "python-pptx"], check=True,
                   stdin=subprocess.DEVNULL)
    subprocess.run([str(python), "-m", "pip", "install", *pip_flags,
                    "google-auth", "google-auth-oauthlib", "google-api-python-client"],
                   check=True, stdin=subprocess.DEVNULL)
    subprocess.run([str(python), "-m", "pip", "install", *pip_flags,
                    "markitdown[pdf,docx,pptx,xlsx]"], check=True, stdin=subprocess.DEVNULL)

    if platform.system().lower() == "windows":
        subprocess.run([str(python), "-m", "pip", "install", *pip_flags, "pywin32"],
                       check=True, stdin=subprocess.DEVNULL)

    automation_req = Path(SCRIPT_DIR).parent / "automation" / "requirements.txt"
    subprocess.run([str(python), "-m", "pip", "install", *pip_flags,
                    "-r", str(automation_req)], check=True, stdin=subprocess.DEVNULL)
    subprocess.run([str(python), "-m", "playwright", "install", "chromium"],
                   capture_output=True, stdin=subprocess.DEVNULL)

    (venv_dir / ".installed").touch()
    print("==> Virtual environment ready.")

_HOME_SKILLS_MANIFEST = ".installed-skills-manifest"

def install_skills():
    print("==> Installing skills to .gemini/skills/...")
    import zipfile
    import shutil
    skills_dir = "skills"
    gemini_skills_dir = os.path.join(".gemini", "skills")
    if os.path.exists(gemini_skills_dir):
        shutil.rmtree(gemini_skills_dir)
    os.makedirs(gemini_skills_dir)
    installed = []
    for skill_file in sorted(os.listdir(skills_dir)):
        if not skill_file.endswith(".skill"):
            continue
        skill_name = skill_file[:-6]
        dest = os.path.join(gemini_skills_dir, skill_name)
        os.makedirs(dest, exist_ok=True)
        with zipfile.ZipFile(os.path.join(skills_dir, skill_file)) as zf:
            zf.extractall(dest)
        print(f"  Installed: {skill_name}")
        installed.append(skill_name)

    # Also install to ~/.gemini/skills/ for Antigravity CLI (agy).
    #
    # A manifest of what THIS process installed last time lets a renamed or
    # retired skill be cleaned up here too — without it, a skill that no
    # longer exists in the current build (e.g. "calendar" consolidated into
    # "daily-schedule") is never touched again: the loop below only
    # overwrites entries matching CURRENT skill names, so the old directory
    # sits there forever, and an agent that stumbles onto it follows
    # stale, no-longer-correct instructions instead of the current skill.
    # Confirmed happening for real. A name never tracked by this manifest
    # (e.g. a skill a user created directly in ~/.gemini/skills/ some other
    # way) is left alone, matching sync_internal_skills.py's equivalent
    # manifest for the LOCAL .gemini/skills/ directory in agent-deck.
    home_gemini_skills = Path.home() / ".gemini" / "skills"
    home_gemini_skills.mkdir(parents=True, exist_ok=True)
    manifest_path = home_gemini_skills / _HOME_SKILLS_MANIFEST
    previously_installed = set(manifest_path.read_text().splitlines()) if manifest_path.exists() else set()
    current_names = set(installed)

    for stale_name in previously_installed - current_names:
        stale_dir = home_gemini_skills / stale_name
        if stale_dir.exists():
            shutil.rmtree(stale_dir)
            print(f"  Removed stale: {stale_name}")

    for skill_name in installed:
        home_skill = home_gemini_skills / skill_name
        if home_skill.exists():
            shutil.rmtree(home_skill)
        shutil.copytree(os.path.join(gemini_skills_dir, skill_name), str(home_skill))

    manifest_path.write_text("\n".join(sorted(current_names)))

def trust_project_folder():
    import json
    trusted_file = Path.home() / ".gemini" / "trustedFolders.json"
    project_root = str(Path(SCRIPT_DIR).parents[2].resolve())
    try:
        data = json.loads(trusted_file.read_text(encoding="utf-8")) if trusted_file.exists() else {}
    except (json.JSONDecodeError, OSError):
        data = {}
    if data.get(project_root) != "TRUST_FOLDER":
        data[project_root] = "TRUST_FOLDER"
        trusted_file.parent.mkdir(parents=True, exist_ok=True)
        trusted_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"==> Trusted project folder: {project_root}")

def setup_files_folder():
    files_dir = Path("files")
    files_dir.mkdir(exist_ok=True)
    print("==> files/ folder ready.")

def install_gemini_policies():
    print("==> Installing Gemini CLI policies to ~/.gemini/policies/...")
    import shutil
    src_policies = Path(SCRIPT_DIR).parents[1] / "config" / "gemini" / "policies"
    dst_policies = Path.home() / ".gemini" / "policies"
    dst_policies.mkdir(parents=True, exist_ok=True)
    for toml_file in src_policies.glob("*.toml"):
        shutil.copy2(toml_file, dst_policies / toml_file.name)
        print(f"  Installed: {toml_file.name}")

# ── setup skills ──────────────────────────────────────────────
#
# Two skill roots:
#   python/skills/           bundled   — ships with every agent-deck install
#   python/skills-personal/  personal — per-installation, gitignored, created by `my-skills create`
# Each root may have its own `disabled/` subfolder for temporarily-disabled skills.

_SKILL_ROOT_NAMES = ["skills", "skills-personal"]

def _skill_roots(project_root):
    return [project_root / "python" / name for name in _SKILL_ROOT_NAMES]

def _find_skill_dir(skill_name, search_root):
    """Return the directory containing SKILL.md whose basename matches skill_name."""
    for skill_md in sorted(Path(search_root).rglob("SKILL.md")):
        if skill_md.parent.name == skill_name:
            return skill_md.parent
    return None

def skills_list():
    project_root = Path(SCRIPT_DIR).parents[2]

    enabled = []
    disabled = []
    for root in _skill_roots(project_root):
        if not root.exists():
            continue
        for skill_md in root.rglob("SKILL.md"):
            rel = skill_md.relative_to(root)
            (disabled if "disabled" in rel.parts else enabled).append(skill_md.parent.name)

    print("Enabled skills / 有効なスキル:")
    for name in sorted(enabled):
        print(f"  ✓ {name}")
    if disabled:
        print("\nDisabled skills / 無効なスキル:")
        for name in sorted(disabled):
            print(f"  ✗ {name}")

def sync_catalog_skills():
    """Best-effort: pull auto-distributed skills (the catalog's _default/
    folder) into skills-personal/ before building, so they're part of the
    same rebuild. skills_catalog.py itself no-ops instantly unless
    config.toml points at a real catalog_folder_id, and handles its own
    venv re-exec for the google-api deps.

    Never fails the rebuild: offline, auth declined/timed out, or any
    other problem just means skills stay as they are until the next
    launch (skills_catalog.py sync already prints its own [WARN] with the
    reason in those cases)."""
    script = os.path.join(SCRIPT_DIR, "skills_catalog.py")
    try:
        result = subprocess.run([sys.executable, script, "sync"],
                                stdin=subprocess.DEVNULL)
        if result.returncode != 0:
            print("  [WARN] Catalog sync failed — continuing with existing skills.")
    except Exception as e:
        print(f"  [WARN] Catalog sync failed ({e}) — continuing with existing skills.")

def skills_rebuild():
    sync_catalog_skills()
    build_skills()
    install_skills()
    print("==> Skills rebuilt and reinstalled.")

def skills_disable(skill_name):
    import shutil
    project_root = Path(SCRIPT_DIR).parents[2]

    for root in _skill_roots(project_root):
        if not root.exists():
            continue
        skill_dir = _find_skill_dir(skill_name, root)
        if not skill_dir or "disabled" in skill_dir.relative_to(root).parts:
            continue

        disabled_dir = root / "disabled"
        disabled_dir.mkdir(exist_ok=True)
        dest = disabled_dir / skill_name
        if dest.exists():
            print(f"Error: '{dest}' already exists — already disabled?")
            sys.exit(1)

        shutil.move(str(skill_dir), str(dest))
        print(f"==> Disabled: {skill_name}")
        build_skills()
        install_skills()
        print(f"==> Done. Run /skills reload in Gemini to apply.")
        return

    roots_desc = "/".join(f"python/{n}/" for n in _SKILL_ROOT_NAMES)
    print(f"Error: skill '{skill_name}' not found in {roots_desc}")
    sys.exit(1)

def skills_enable(skill_name):
    import shutil
    project_root = Path(SCRIPT_DIR).parents[2]

    for root in _skill_roots(project_root):
        disabled_dir = root / "disabled"
        if not disabled_dir.exists():
            continue
        skill_dir = _find_skill_dir(skill_name, disabled_dir)
        if not skill_dir:
            continue

        dest = root / skill_name
        if dest.exists():
            print(f"Error: '{dest}' already exists — already enabled?")
            sys.exit(1)

        shutil.move(str(skill_dir), str(dest))
        print(f"==> Enabled: {skill_name}")
        build_skills()
        install_skills()
        print(f"==> Done. Run /skills reload in Gemini to apply.")
        return

    roots_desc = "/".join(f"python/{n}/disabled/" for n in _SKILL_ROOT_NAMES)
    print(f"Error: skill '{skill_name}' not found in {roots_desc}")
    sys.exit(1)

# ── setup config ──────────────────────────────────────────────

def _prompt(msg):
    """input() that degrades to an empty answer when running non-interactively.

    setup_config() can run non-interactively (invoked by agent-deck's
    pre_launch_command via preflight.sh/.bat, with no real user attached),
    where a bare input() would either raise EOFError or, confirmed for real
    on Windows, block forever (Tauri's pre_launch_command there apparently
    leaves stdin in a state where sys.stdin.isatty() is NOT a reliable
    signal either -- an isatty()-based guard alone still hung indefinitely
    on a genuinely fresh Windows install). Missing credentials/email are
    already handled as "not yet configured" (re-prompted next time this
    runs interactively), so degrading to an empty answer is safe here.

    The one deterministic signal is AGENT_DECK_NONINTERACTIVE, which
    preflight.sh/.bat export before calling `setup.py config` -- this
    doesn't depend on guessing how any given platform/shell wires up
    stdin for a spawned child process. isatty()/EOFError remain as a
    fallback for other invocation contexts (e.g. running this file
    directly without that env var set).
    """
    if os.environ.get("AGENT_DECK_NONINTERACTIVE"):
        return ""
    if not sys.stdin.isatty():
        return ""
    try:
        return input(msg)
    except EOFError:
        return ""


def setup_config():
    """Prompt for missing OAuth credentials and email; save to config.toml."""
    import re
    import getpass
    if not CONFIG_PATH.exists():
        return
    text = CONFIG_PATH.read_text(encoding="utf-8")

    def _get(key):
        m = re.search(rf'^{key}\s*=\s*"([^"]*)"', text, re.MULTILINE)
        return m.group(1).strip() if m else ""

    def _set(key, value):
        nonlocal text
        text = re.sub(rf'^({key}\s*=\s*)"[^"]*"', f'\\1"{value}"', text, flags=re.MULTILINE)

    # ── OAuth credentials ──────────────────────────────────────
    client_id     = _get("client_id")
    client_secret = _get("client_secret")
    if not client_id or not client_secret:
        print("==> OAuth 認証情報の設定 / OAuth credentials setup")
        print("    Google Cloud Console → APIs & Services → Credentials → OAuth 2.0 Client IDs")
        print()
        if not client_id:
            client_id = _prompt("  Client ID     : ").strip()
            _set("client_id", client_id)
        if not client_secret:
            client_secret = _prompt("  Client Secret : ").strip()
            _set("client_secret", client_secret)
        CONFIG_PATH.write_text(text, encoding="utf-8")
        text = CONFIG_PATH.read_text(encoding="utf-8")
        print("==> config.toml を更新しました / Saved to config.toml.")

    # ── Email ──────────────────────────────────────────────────
    if not _get("email"):
        print("==> メールアドレスの確認 / Email address setup")
        print("    Google 認証時に正しいアカウントを自動選択するために使用します。")
        print("    Used to pre-select your account on the Google sign-in screen.")
        print()
        email = _prompt("  メールアドレス / Email: ").strip()

        if email:
            user_re  = re.compile(r'^\[user\]', re.MULTILINE)
            email_re = re.compile(r'^(# *)?email\s*=.*$', re.MULTILINE)
            if user_re.search(text):
                if email_re.search(text):
                    text = email_re.sub(f'email = "{email}"', text, count=1)
                else:
                    text = user_re.sub(f'[user]\nemail = "{email}"', text, count=1)
            else:
                text = text.rstrip() + f'\n\n[user]\nemail = "{email}"\n'
            CONFIG_PATH.write_text(text, encoding="utf-8")
            print(f"==> メールアドレスを保存しました / Email saved: {email}")

def clear_email():
    """Clear the email field in config.toml so setup_config() will re-prompt."""
    import re
    if not CONFIG_PATH.exists():
        return
    text = CONFIG_PATH.read_text(encoding="utf-8")
    email_re = re.compile(r'^(# *)?email\s*=.*$', re.MULTILINE)
    text = email_re.sub('# email = ""', text)
    CONFIG_PATH.write_text(text, encoding="utf-8")
    print("==> メールアドレスをリセットしました / Email cleared from config.toml.")

# ── entrypoint ────────────────────────────────────────────────

def _usage():
    print("Usage: setup.py [init|config [clear-email]|trust|skills [list|rebuild|enable <name>|disable <name>]]")
    sys.exit(1)

if __name__ == "__main__":
    args = sys.argv[1:]
    cmd  = args[0] if args else "init"

    if cmd == "init":
        setup_config()
        setup_venv()
        build_skills()
        install_skills()
        install_gemini_policies()
        trust_project_folder()
        setup_files_folder()
        print("==> Setup completed successfully.")

    elif cmd == "skills":
        sub = args[1] if len(args) > 1 else "rebuild"
        if sub == "list":
            skills_list()
        elif sub == "rebuild":
            skills_rebuild()
        elif sub == "enable":
            if len(args) < 3:
                print("Error: specify a skill name.  e.g. setup.py skills enable downloads")
                sys.exit(1)
            skills_enable(args[2])
        elif sub == "disable":
            if len(args) < 3:
                print("Error: specify a skill name.  e.g. setup.py skills disable downloads")
                sys.exit(1)
            skills_disable(args[2])
        else:
            _usage()

    elif cmd == "config":
        sub = args[1] if len(args) > 1 else ""
        if sub == "clear-email":
            clear_email()
        else:
            setup_config()

    elif cmd == "trust":
        trust_project_folder()

    else:
        _usage()
