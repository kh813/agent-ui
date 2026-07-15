"""
Tests for python/config/__init__.py's [notifications] chat_webhook_url handling.

Loads the real config/__init__.py against a temporary project layout with its
own config.toml, so the actual toml-parsing logic is exercised — not mocked.
This also guards backward compatibility: every config.toml that existed
before today predates the [notifications] section entirely, and must not
break on the next /update.

Run:
  pytest python/tests/test_config_notifications.py -v
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_REAL_CONFIG_INIT = _ROOT / "python" / "config" / "__init__.py"

_BASE_TOML = """
[oauth]
client_id = "x"
client_secret = "x"

[drive]
catalog_folder_id = "x"

[template]
name = "x.pptx"
url = "https://example.com"
"""


def _load_config_module(tmp_path: Path, toml_text: str):
    (tmp_path / "config.toml").write_text(toml_text, encoding="utf-8")

    pkg_dir = tmp_path / "python" / "config"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text(
        _REAL_CONFIG_INIT.read_text(encoding="utf-8"), encoding="utf-8"
    )

    sys.modules.pop("config", None)
    spec = importlib.util.spec_from_file_location("config", pkg_dir / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["config"] = module
    spec.loader.exec_module(module)
    return module


class TestChatWebhookUrl:
    def test_reads_configured_value(self, tmp_path):
        toml_text = _BASE_TOML + (
            '\n[notifications]\nchat_webhook_url = '
            '"https://chat.googleapis.com/v1/spaces/x"\n'
        )
        module = _load_config_module(tmp_path, toml_text)

        assert module.CHAT_WEBHOOK_URL == "https://chat.googleapis.com/v1/spaces/x"

    def test_defaults_to_empty_when_section_missing(self, tmp_path):
        """Every config.toml written before this feature has no [notifications]
        section at all — must not raise or crash on the next /update."""
        module = _load_config_module(tmp_path, _BASE_TOML)

        assert module.CHAT_WEBHOOK_URL == ""

    def test_defaults_to_empty_when_key_missing(self, tmp_path):
        toml_text = _BASE_TOML + "\n[notifications]\n"
        module = _load_config_module(tmp_path, toml_text)

        assert module.CHAT_WEBHOOK_URL == ""

    def test_strips_whitespace(self, tmp_path):
        toml_text = _BASE_TOML + '\n[notifications]\nchat_webhook_url = "  https://x  "\n'
        module = _load_config_module(tmp_path, toml_text)

        assert module.CHAT_WEBHOOK_URL == "https://x"


class TestConfigTemplateHasNotificationsSection:
    def test_template_declares_chat_webhook_url(self):
        template = (_ROOT / "config" / "config.toml.template").read_text(encoding="utf-8")

        assert "[notifications]" in template
        assert "chat_webhook_url" in template
