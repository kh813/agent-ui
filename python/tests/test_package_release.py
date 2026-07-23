"""
Tests for package_release.py -- rebuilds the public GitHub release with
this org's own config.toml merged in, for internal (config-bundled) Drive
distribution. Covers build_package()'s fetch/merge/zip logic; upload() and
_get_service() are thin OAuth/Drive-API wrappers left untested, matching
this repo's existing convention for backup_config.py/drive_upload.py.

Run:
  pytest python/tests/test_package_release.py -v
"""
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python" / "scripts" / "tools"))
sys.path.insert(0, str(ROOT / "python" / "scripts" / "setup"))

import package_release as pr  # noqa: E402
import self_update as su  # noqa: E402


def _fake_release(tag: str) -> dict:
    return {
        "tag_name": tag,
        "assets": [
            {"name": "agent-deck-mac.zip", "browser_download_url": f"https://example.com/{tag}/mac.zip"},
            {"name": "agent-deck-win.zip", "browser_download_url": f"https://example.com/{tag}/win.zip"},
        ],
    }


def _make_mac_zip(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("agent-deck.app/Contents/MacOS/agent-deck", "#!/bin/sh\necho hi\n")
        zf.writestr("agent-deck.app/Contents/Info.plist", "<plist/>")
        zf.writestr("python/skills/translator/SKILL.md", "---\nname: translator\n---\n")
        zf.writestr("config/config.toml.template", "[oauth]\n")
        zf.writestr("agent_config.json", "{}")
        zf.writestr("preflight.sh", "#!/bin/bash\necho ok\n")
        zf.writestr("messages/no_python.txt", "no python")


def _make_win_zip(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("agent-deck.exe", "fake exe content")
        zf.writestr("python/skills/translator/SKILL.md", "---\nname: translator\n---\n")
        zf.writestr("config/config.toml.template", "[oauth]\n")
        zf.writestr("agent_config.json", "{}")
        zf.writestr("preflight.bat", "@echo off\r\necho ok\r\n")
        zf.writestr("messages/no_python.txt", "no python")


@pytest.fixture
def fake_org_config(tmp_path):
    cfg = tmp_path / "org-config.toml"
    cfg.write_text('[oauth]\nclient_id = "real-id"\nclient_secret = "real-secret"\n')
    return cfg


@pytest.fixture
def no_op_signing(monkeypatch):
    """Skip real xattr/codesign calls -- irrelevant to this module's own
    fetch/merge/zip logic, and codesign isn't guaranteed present everywhere
    tests run."""
    monkeypatch.setattr(pr.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0))


class TestBuildPackage:
    def test_merges_both_platforms_and_config_toml(self, tmp_path, fake_org_config, monkeypatch, no_op_signing):
        monkeypatch.setattr(su, "_fetch_release", lambda channel: _fake_release("v0.0.22-rc1"))

        def fake_download(url, dest):
            if "mac.zip" in url:
                _make_mac_zip(dest)
            else:
                _make_win_zip(dest)

        monkeypatch.setattr(pr, "_download", fake_download)

        out_zip = pr.build_package("test", tmp_path, config_toml=fake_org_config)

        assert out_zip.name == "agent-deck-test.zip"
        with zipfile.ZipFile(out_zip) as zf:
            names = zf.namelist()
        assert "config.toml" in names
        assert "agent-deck.app/Contents/MacOS/agent-deck" in names
        assert "agent-deck.exe" in names
        assert "python/skills/translator/SKILL.md" in names
        assert "preflight.sh" in names
        assert "preflight.bat" in names

    def test_prod_channel_uses_prod_zip_name(self, tmp_path, fake_org_config, monkeypatch, no_op_signing):
        monkeypatch.setattr(su, "_fetch_release", lambda channel: _fake_release("v0.0.21"))
        monkeypatch.setattr(pr, "_download", lambda url, dest: (
            _make_mac_zip(dest) if "mac.zip" in url else _make_win_zip(dest)
        ))

        out_zip = pr.build_package("prod", tmp_path, config_toml=fake_org_config)

        assert out_zip.name == "agent-deck.zip"

    def test_missing_asset_raises(self, tmp_path, fake_org_config, monkeypatch, no_op_signing):
        monkeypatch.setattr(su, "_fetch_release", lambda channel: {
            "tag_name": "v0.0.22-rc1",
            "assets": [{"name": "agent-deck-mac.zip", "browser_download_url": "https://example.com/mac.zip"}],
        })
        monkeypatch.setattr(pr, "_download", lambda url, dest: _make_mac_zip(dest))

        with pytest.raises(RuntimeError, match="agent-deck-win.zip"):
            pr.build_package("test", tmp_path, config_toml=fake_org_config)

    def test_aborts_when_signature_verification_fails(self, tmp_path, fake_org_config, monkeypatch):
        """Confirmed for real (2026-07-23): an invalid signature after the
        merge/re-sign round-trip means macOS refuses to even launch the app
        ("is damaged", error -47, no user override) -- must abort before
        zipping/uploading a build that can never launch."""
        monkeypatch.setattr(su, "_fetch_release", lambda channel: _fake_release("v0.0.22-rc1"))
        monkeypatch.setattr(pr, "_download", lambda url, dest: (
            _make_mac_zip(dest) if "mac.zip" in url else _make_win_zip(dest)
        ))

        def fake_run(cmd, *a, **kw):
            if cmd[0] == "codesign" and cmd[1] == "--verify":
                return subprocess.CompletedProcess(cmd, 1, stderr=b"invalid signature")
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(pr.subprocess, "run", fake_run)

        with pytest.raises(RuntimeError, match="signature verification failed"):
            pr.build_package("test", tmp_path, config_toml=fake_org_config)

    def test_missing_config_toml_raises(self, tmp_path, monkeypatch, no_op_signing):
        monkeypatch.setattr(su, "_fetch_release", lambda channel: _fake_release("v0.0.22-rc1"))
        monkeypatch.setattr(pr, "_download", lambda url, dest: (
            _make_mac_zip(dest) if "mac.zip" in url else _make_win_zip(dest)
        ))

        with pytest.raises(RuntimeError, match="config.toml"):
            pr.build_package("test", tmp_path, config_toml=tmp_path / "does-not-exist.toml")

    def test_zip_has_no_wrapper_folder(self, tmp_path, fake_org_config, monkeypatch, no_op_signing):
        """Matches the public release ZIP's own flat layout, so
        README/user_guide.md's extraction instructions apply unchanged
        regardless of whether the ZIP came from GitHub or this org's Drive."""
        monkeypatch.setattr(su, "_fetch_release", lambda channel: _fake_release("v0.0.22-rc1"))
        monkeypatch.setattr(pr, "_download", lambda url, dest: (
            _make_mac_zip(dest) if "mac.zip" in url else _make_win_zip(dest)
        ))

        out_zip = pr.build_package("test", tmp_path, config_toml=fake_org_config)

        with zipfile.ZipFile(out_zip) as zf:
            names = zf.namelist()
        assert all(not n.startswith("agent-deck/") for n in names)
