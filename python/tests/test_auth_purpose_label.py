"""
Regression test: run_auth_flow's optional `purpose` label.

The bug: a user's first launch can trigger two separate, unrelated Google
sign-in prompts back to back -- this repo's own Drive OAuth (skill-catalog
sync, via run_auth_flow) and agy's own separate sign-in (baked into the
agy binary itself, entirely outside this codebase). Confirmed for real
that a user reasonably read the second prompt as a duplicate/bug, since
neither was labeled. run_auth_flow now accepts an optional `purpose`
string, printed alongside the generic sign-in prompt so a user can tell
which flow is which; skills_catalog.py's launch-time sync passes one.

Run:
  pytest python/tests/test_auth_purpose_label.py -v
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from scripts.auth import run_auth_flow  # noqa: E402


class _FakeFlow:
    def run_local_server(self, **kwargs):
        return "fake-creds"


class TestRunAuthFlowPurposeLabel:
    def test_no_purpose_prints_generic_prompt_only(self, capsys):
        run_auth_flow(_FakeFlow())
        out = capsys.readouterr().out
        assert "Chrome が開きます。" in out
        assert "Chrome will open —" in out

    def test_purpose_is_included_in_both_languages(self, capsys):
        run_auth_flow(_FakeFlow(), purpose="スキルカタログ / Skill catalog")
        out = capsys.readouterr().out
        assert "スキルカタログ / Skill catalog" in out
        assert out.count("スキルカタログ / Skill catalog") == 2, (
            "purpose label should appear in both the Japanese and English prompt lines"
        )


class TestSkillsCatalogPassesAPurposeLabel:
    def test_get_credentials_labels_its_auth_flow(self):
        source = (ROOT / "python" / "scripts" / "setup" / "skills_catalog.py").read_text()
        match = re.search(r"run_auth_flow\(flow[^)]*\)", source, re.DOTALL)
        assert match and "purpose=" in match.group(0), (
            "skills_catalog.py's _get_credentials() no longer passes a purpose "
            "label to run_auth_flow -- without it, this launch-time Drive auth "
            "prompt is indistinguishable from agy's own separate sign-in prompt "
            "that can immediately follow it."
        )
