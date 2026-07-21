"""
Regression test for Windows stdout/stderr UTF-8 reconfiguration.

The bug: on Windows, piping a script's stdout through agy.exe's pty makes
Python fall back to the CP932/CP1252 codepage, corrupting Japanese output
(or raising UnicodeEncodeError). Confirmed for real twice: (1) a user's
/update -> preflight.bat -> `setup.py config` step printed mojibake instead
of the intended Japanese prompts; (2) later, a user's launch-time catalog
sync crashed outright with `UnicodeEncodeError: 'cp932' codec can't encode
character '—'` (an em-dash) in auth.py's run_auth_flow() print, and
then crashed AGAIN in skills_catalog.py's own [WARN] handler (which embeds
the caught exception's message, itself containing that same em-dash) —
turning a should-be-graceful "skip this launch, retry next time" into a
hard traceback.

Known wider gap (2026-07-16, not fully closed): scanning this repo for
Japanese print() output turned up over a dozen other scripts with the same
exposure. setup.py, auth.py, and skills_catalog.py are fixed and covered
here so far, since those are the ones confirmed to have broken for a real
user. Every python/scripts/automation/*.py and python/scripts/tools/*.py
script still has the same exposure — extending this same guard (and this
test) to the rest is tracked as follow-up work, not rushed in alongside
each urgent single-file fix.

Run:
  pytest python/tests/test_windows_utf8.py -v
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class TestWindowsUtf8Reconfigure:
    def _check(self, relpath: str) -> None:
        src = (ROOT / relpath).read_text(encoding="utf-8")

        assert "sys.platform == 'win32'" in src, (
            f"{relpath} no longer branches on sys.platform == 'win32' for "
            "the stdout/stderr UTF-8 reconfiguration."
        )
        assert "sys.stdout.reconfigure(encoding='utf-8'" in src, (
            f"{relpath} no longer reconfigures sys.stdout to UTF-8 on "
            "Windows. Without this, piping stdout through agy.exe's pty "
            "falls back to CP1252 and Japanese output raises "
            "UnicodeEncodeError or renders as mojibake."
        )
        assert "sys.stderr.reconfigure(encoding='utf-8'" in src, (
            f"{relpath} no longer reconfigures sys.stderr to UTF-8 on Windows."
        )
        assert "errors='replace'" in src, (
            f"{relpath}'s UTF-8 reconfigure dropped errors='replace' — "
            "without it, any character still unencodable raises instead of "
            "degrading gracefully."
        )

    def test_setup_py(self):
        self._check("python/scripts/setup/setup.py")

    def test_auth_py(self):
        self._check("python/scripts/auth.py")

    def test_skills_catalog_py(self):
        self._check("python/scripts/setup/skills_catalog.py")
