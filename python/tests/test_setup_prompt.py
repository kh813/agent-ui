"""
Regression test for setup.py's _prompt() non-interactive handling.

The bug: _prompt() relied on input() raising EOFError when stdin has no
more data to degrade to an empty answer for setup_config()'s email/OAuth
prompts during preflight's non-interactive invocation. This works when
stdin is closed (immediate EOF) -- confirmed fine on Mac -- but confirmed
for real on Windows: a genuinely fresh install's first-time setup hung
indefinitely at the email prompt. A first attempt added a sys.stdin.isatty()
guard, reasoning it would be False for both a closed and an "open but
inert" stdin -- but confirmed for real that this ALSO still hung: isatty()
is apparently not a reliable signal in whatever way Tauri's
pre_launch_command wires up a spawned child's stdin on Windows.

Fix: stop trying to infer non-interactivity from stdin's own properties
at all. preflight.sh/.bat now export AGENT_DECK_NONINTERACTIVE=1 before
calling `setup.py config`/`init` -- an explicit, deterministic signal from
the caller that doesn't depend on guessing platform-specific stdio
plumbing. isatty()/EOFError remain as a fallback for other invocation
contexts (e.g. running this file directly without that env var set).

Run:
  pytest python/tests/test_setup_prompt.py -v
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python" / "scripts" / "setup"))

import setup as agent_setup  # noqa: E402


class TestPromptNonInteractive:
    def test_returns_empty_without_calling_input_when_env_var_set(self, monkeypatch):
        """The deterministic path: preflight.sh/.bat set this before calling
        setup.py, regardless of what stdin looks like."""
        monkeypatch.setenv("AGENT_DECK_NONINTERACTIVE", "1")
        # Even if stdin looks interactive, the env var must win outright --
        # this is exactly the scenario that made the isatty()-only guard
        # insufficient on a real Windows machine.
        monkeypatch.setattr(agent_setup.sys.stdin, "isatty", lambda: True)

        def _fail_if_called(msg):
            raise AssertionError(
                "_prompt() called input() despite AGENT_DECK_NONINTERACTIVE "
                "being set -- this is exactly what hung forever on a "
                "genuinely fresh Windows install."
            )

        monkeypatch.setattr("builtins.input", _fail_if_called)

        assert agent_setup._prompt("  Email: ") == ""

    def test_returns_empty_without_calling_input_when_stdin_is_not_a_tty(self, monkeypatch):
        monkeypatch.delenv("AGENT_DECK_NONINTERACTIVE", raising=False)
        monkeypatch.setattr(agent_setup.sys.stdin, "isatty", lambda: False)

        def _fail_if_called(msg):
            raise AssertionError(
                "_prompt() called input() despite a non-interactive stdin."
            )

        monkeypatch.setattr("builtins.input", _fail_if_called)

        assert agent_setup._prompt("  Email: ") == ""

    def test_still_returns_empty_on_eof_when_stdin_looks_interactive(self, monkeypatch):
        """Belt-and-suspenders: even if isatty() somehow reports True but the
        read still hits EOF (e.g. a redirected-but-tty-like stream in some
        test harness), _prompt() must not crash."""
        monkeypatch.delenv("AGENT_DECK_NONINTERACTIVE", raising=False)
        monkeypatch.setattr(agent_setup.sys.stdin, "isatty", lambda: True)

        def _raise_eof(msg):
            raise EOFError

        monkeypatch.setattr("builtins.input", _raise_eof)

        assert agent_setup._prompt("  Email: ") == ""


class TestPreflightSetsNonInteractiveEnvVar:
    def test_preflight_sh_exports_it(self):
        src = (ROOT / "preflight.sh").read_text(encoding="utf-8")
        assert "AGENT_DECK_NONINTERACTIVE=1" in src, (
            "preflight.sh no longer sets AGENT_DECK_NONINTERACTIVE -- "
            "setup.py's _prompt() would fall back to isatty(), which was "
            "confirmed insufficient on Windows."
        )
        # Must be exported (not just a local shell var) so the child
        # python3 process actually inherits it.
        assert "export AGENT_DECK_NONINTERACTIVE" in src

    def test_preflight_bat_sets_it(self):
        src = (ROOT / "preflight.bat").read_bytes().decode("ascii")
        assert 'AGENT_DECK_NONINTERACTIVE=1' in src, (
            "preflight.bat no longer sets AGENT_DECK_NONINTERACTIVE -- "
            "setup.py's _prompt() would fall back to isatty(), which was "
            "confirmed insufficient on Windows."
        )
