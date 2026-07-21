"""
Regression test: first-time setup's pip install steps must suppress
"script ... is installed in ... which is not on PATH" warnings.

Confirmed for real (2026-07-22): a fresh Windows install's console showed
a yellow-looking "WARNING: The script virtualenv.exe is installed in
'...\\App\\python\\Scripts' which is not on PATH" during first-time setup.
It's harmless -- neither the embedded Python bootstrap nor the venv it
builds are ever meant to be used with these Scripts/bin directories on
PATH -- but it reads as an alarming error to a non-technical user during
what should look like a clean setup. get-pip.py's own invocation already
passed --no-warn-script-location for this exact reason; the other pip
install calls (virtualenv itself, and the venv's own package installs)
didn't.

Run:
  pytest python/tests/test_pip_no_warn_script_location.py -v
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETUP_BAT = ROOT / "python" / "scripts" / "setup" / "setup.bat"
SETUP_PY = ROOT / "python" / "scripts" / "setup" / "setup.py"


class TestSetupBatSuppressesPipScriptWarnings:
    def test_every_pip_install_line_has_the_flag(self):
        text = SETUP_BAT.read_text()
        pip_install_lines = [
            line for line in text.splitlines() if "pip install" in line
        ]
        assert pip_install_lines, "expected at least one 'pip install' line in setup.bat"
        missing = [line for line in pip_install_lines if "--no-warn-script-location" not in line]
        assert not missing, (
            "setup.bat has pip install line(s) missing --no-warn-script-location: "
            f"{missing}"
        )


class TestSetupPySuppressesPipScriptWarnings:
    def test_pip_flags_include_the_flag(self):
        text = SETUP_PY.read_text()
        match = re.search(r"pip_flags\s*=\s*\[([^\]]*)\]", text)
        assert match, "expected a pip_flags = [...] list in setup.py"
        assert "--no-warn-script-location" in match.group(1), (
            "setup.py's pip_flags no longer includes --no-warn-script-location -- "
            "every pip install call built from it (python-pptx, google-auth, "
            "markitdown, pywin32, automation requirements) would print a "
            "confusing 'script is installed ... which is not on PATH' warning "
            "during first-time setup."
        )
