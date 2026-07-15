"""
Tests for notify_chat.py — Google Chat webhook delivery.

Covers:
  - send() skips gracefully when chat_webhook_url is unset
  - send() posts the expected JSON payload when configured
  - send() reports failure on a non-2xx response

config and requests are mocked so no network or config.toml is required.

Run:
  venv/bin/pytest python/tests/test_notify_chat.py -v
"""

import sys
import importlib
import pytest
from pathlib import Path
from unittest.mock import MagicMock

_SRC_DIR        = Path(__file__).resolve().parents[1]
_AUTOMATION_DIR = _SRC_DIR / "scripts" / "automation"
sys.path.insert(0, str(_AUTOMATION_DIR))
sys.path.insert(0, str(_SRC_DIR))


def _load_notify_chat(webhook_url: str, requests_mock: MagicMock):
    """Import notify_chat.py fresh with config/requests mocked to the given values."""
    config_mock = MagicMock()
    config_mock.CHAT_WEBHOOK_URL = webhook_url
    sys.modules["config"] = config_mock
    sys.modules["requests"] = requests_mock

    sys.modules.pop("notify_chat", None)
    import notify_chat  # noqa
    return notify_chat


class TestSendSkipsWhenUnconfigured:
    def test_returns_false_and_does_not_post(self):
        requests_mock = MagicMock()
        notify_chat = _load_notify_chat("", requests_mock)

        result = notify_chat.send("hello")

        assert result is False
        requests_mock.post.assert_not_called()


class TestSendPostsExpectedPayload:
    def test_posts_text_payload_to_configured_url(self):
        requests_mock = MagicMock()
        requests_mock.post.return_value = MagicMock(status_code=200)
        url = "https://chat.googleapis.com/v1/spaces/AAA/messages?key=K&token=T"
        notify_chat = _load_notify_chat(url, requests_mock)

        result = notify_chat.send("結果: OK")

        assert result is True
        args, kwargs = requests_mock.post.call_args
        assert args[0] == url
        assert kwargs["json"] == {"text": "結果: OK"}


class TestSendReportsFailure:
    def test_non_2xx_response_returns_false(self):
        requests_mock = MagicMock()
        requests_mock.post.return_value = MagicMock(status_code=404, text="Not Found")
        notify_chat = _load_notify_chat("https://chat.googleapis.com/v1/spaces/x", requests_mock)

        result = notify_chat.send("hello")

        assert result is False
