"""
Tests for agy_scheduled_prompt.py — the headless runner invoked by scheduled
agy tasks.

subprocess.run (the agy --print call) and notify_chat.send are both mocked;
no real agy binary or Chat webhook is touched. The log file is redirected to
tmp_path so tests never write into this repo's real logs/ directory.

Run:
  venv/bin/pytest python/tests/test_agy_scheduled_prompt.py -v
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock

_AUTOMATION_DIR = Path(__file__).resolve().parents[1] / "scripts" / "automation"
sys.path.insert(0, str(_AUTOMATION_DIR))

_notify_chat_mock = MagicMock()
sys.modules["notify_chat"] = _notify_chat_mock

import agy_scheduled_prompt as runner  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_log(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "_LOG_FILE", tmp_path / "agy_scheduled.log")
    _notify_chat_mock.send.reset_mock()
    yield


class TestSuccessfulRun:
    def test_sends_agy_output_to_chat(self, monkeypatch):
        monkeypatch.setattr(
            runner.subprocess, "run",
            MagicMock(return_value=MagicMock(returncode=0, stdout="ドル円は150円です", stderr="")),
        )

        exit_code = runner.run("今日のドル円レートを確認して")

        assert exit_code == 0
        _notify_chat_mock.send.assert_called_once_with("ドル円は150円です")

    def test_empty_output_sends_placeholder(self, monkeypatch):
        monkeypatch.setattr(
            runner.subprocess, "run",
            MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr="")),
        )

        runner.run("prompt")

        sent = _notify_chat_mock.send.call_args.args[0]
        assert "空の応答" in sent


class TestFailedRun:
    def test_nonzero_exit_reports_failure(self, monkeypatch):
        monkeypatch.setattr(
            runner.subprocess, "run",
            MagicMock(return_value=MagicMock(returncode=1, stdout="", stderr="agy crashed")),
        )

        exit_code = runner.run("prompt")

        assert exit_code == 1
        sent = _notify_chat_mock.send.call_args.args[0]
        assert "失敗" in sent
        assert "agy crashed" in sent


class TestTimeout:
    def test_timeout_reports_and_returns_nonzero(self, monkeypatch):
        import subprocess as real_subprocess

        def _raise(*a, **k):
            raise real_subprocess.TimeoutExpired(cmd="agy", timeout=300)

        monkeypatch.setattr(runner.subprocess, "run", _raise)

        exit_code = runner.run("prompt", timeout_seconds=300)

        assert exit_code == 1
        sent = _notify_chat_mock.send.call_args.args[0]
        assert "タイムアウト" in sent
