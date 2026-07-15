"""
Tests for drive_download.py — pure logic functions.

Covers:
  - _parse_url(): Drive URL pattern recognition
  - _scan_conflicts(): local conflict detection

Google API, config, and logger are mocked so no network or OAuth is required.

Run:
  venv/bin/pytest python/tests/test_drive_download.py -v
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock

_SRC_DIR   = Path(__file__).resolve().parents[1]
_TOOLS_DIR = _SRC_DIR / "scripts" / "tools"
sys.path.insert(0, str(_TOOLS_DIR))
sys.path.insert(0, str(_SRC_DIR))

# Mock external dependencies so module-level code doesn't fail on import.
for _mod in [
    "googleapiclient", "googleapiclient.discovery", "googleapiclient.http",
    "google", "google.oauth2", "google.oauth2.credentials",
    "google_auth_oauthlib", "google_auth_oauthlib.flow",
    "google.auth", "google.auth.transport", "google.auth.transport.requests",
]:
    sys.modules.setdefault(_mod, MagicMock())

_config_mock = MagicMock()
_config_mock.OAUTH_CLIENT_ID     = "test_client_id"
_config_mock.OAUTH_CLIENT_SECRET = "test_client_secret"
_config_mock.USER_EMAIL          = "test@example.com"
sys.modules["config"] = _config_mock

_logger_mock = MagicMock()
_logger_mock.get_logger.return_value = MagicMock()
_logger_mock.log_startup = MagicMock()
sys.modules["scripts"]        = MagicMock()
sys.modules["scripts.auth"]   = MagicMock()
sys.modules["scripts.logger"] = _logger_mock

import drive_download  # noqa: E402


# ── _parse_url ─────────────────────────────────────────────────

class TestParseUrl:
    """Drive URL patterns → (resource_id, resource_type)."""

    # ── Google native editors ──────────────────────────────────

    def test_google_docs_url(self):
        url = "https://docs.google.com/document/d/ABC123/edit"
        rid, rtype = drive_download._parse_url(url)
        assert rid == "ABC123"
        assert rtype == "google_native"

    def test_google_sheets_url(self):
        url = "https://docs.google.com/spreadsheets/d/SHEET456/edit#gid=0"
        rid, rtype = drive_download._parse_url(url)
        assert rid == "SHEET456"
        assert rtype == "google_native"

    def test_google_slides_url(self):
        url = "https://docs.google.com/presentation/d/PRES789/edit"
        rid, rtype = drive_download._parse_url(url)
        assert rid == "PRES789"
        assert rtype == "google_native"

    def test_google_forms_url(self):
        url = "https://docs.google.com/forms/d/FORM000/edit"
        rid, rtype = drive_download._parse_url(url)
        assert rid == "FORM000"
        assert rtype == "google_native"

    def test_google_drawings_url(self):
        url = "https://docs.google.com/drawings/d/DRAW111/edit"
        rid, rtype = drive_download._parse_url(url)
        assert rid == "DRAW111"
        assert rtype == "google_native"

    # ── Folder ────────────────────────────────────────────────

    def test_folder_url(self):
        url = "https://drive.google.com/drive/folders/FOLDER_ID_XYZ"
        rid, rtype = drive_download._parse_url(url)
        assert rid == "FOLDER_ID_XYZ"
        assert rtype == "folder"

    def test_folder_url_with_query_string(self):
        url = "https://drive.google.com/drive/folders/FOLDER_ID_XYZ?usp=sharing"
        rid, rtype = drive_download._parse_url(url)
        assert rid == "FOLDER_ID_XYZ"
        assert rtype == "folder"

    # ── File ──────────────────────────────────────────────────

    def test_file_url_with_file_d(self):
        url = "https://drive.google.com/file/d/FILE_ID_ABC/view?usp=sharing"
        rid, rtype = drive_download._parse_url(url)
        assert rid == "FILE_ID_ABC"
        assert rtype == "file"

    def test_file_url_open_with_id_param(self):
        url = "https://drive.google.com/open?id=FILE_ID_QQQ"
        rid, rtype = drive_download._parse_url(url)
        assert rid == "FILE_ID_QQQ"
        assert rtype == "file"

    def test_file_url_id_in_query(self):
        url = "https://drive.google.com/uc?export=download&id=FILE_ID_ZZZ"
        rid, rtype = drive_download._parse_url(url)
        assert rid == "FILE_ID_ZZZ"
        assert rtype == "file"

    # ── Invalid ───────────────────────────────────────────────

    def test_unrecognized_url_returns_none(self):
        rid, rtype = drive_download._parse_url("https://example.com/something")
        assert rid is None
        assert rtype is None

    def test_empty_string_returns_none(self):
        rid, rtype = drive_download._parse_url("")
        assert rid is None
        assert rtype is None

    def test_plain_text_returns_none(self):
        rid, rtype = drive_download._parse_url("not a url at all")
        assert rid is None
        assert rtype is None


# ── _scan_conflicts ────────────────────────────────────────────

class TestScanConflicts:
    """Detect which items already exist locally."""

    def _item(self, rel_path: str, is_native: bool = False) -> dict:
        return {
            "rel_path": rel_path,
            "file_id": "dummy_id",
            "size_kb": 10,
            "mime_type": "application/octet-stream",
            "is_native": is_native,
        }

    def test_no_conflicts_when_dest_empty(self, tmp_path):
        items = [self._item("file.pdf"), self._item("doc.docx")]
        conflicts = drive_download._scan_conflicts(items, tmp_path)
        assert conflicts == []

    def test_detects_existing_file(self, tmp_path):
        (tmp_path / "existing.pdf").touch()
        items = [self._item("existing.pdf")]
        conflicts = drive_download._scan_conflicts(items, tmp_path)
        assert "existing.pdf" in conflicts

    def test_no_conflict_for_new_file(self, tmp_path):
        items = [self._item("new_file.pdf")]
        conflicts = drive_download._scan_conflicts(items, tmp_path)
        assert conflicts == []

    def test_mixed_existing_and_new(self, tmp_path):
        (tmp_path / "exists.pdf").touch()
        items = [self._item("exists.pdf"), self._item("new.docx")]
        conflicts = drive_download._scan_conflicts(items, tmp_path)
        assert "exists.pdf" in conflicts
        assert "new.docx" not in conflicts

    def test_native_files_excluded_from_conflicts(self, tmp_path):
        # Even if a file with the same name exists, native Drive files are
        # skipped by the download logic and must not appear as conflicts.
        (tmp_path / "gdoc.gdoc").touch()
        items = [self._item("gdoc.gdoc", is_native=True)]
        conflicts = drive_download._scan_conflicts(items, tmp_path)
        assert conflicts == []

    def test_all_existing_files_returned(self, tmp_path):
        for name in ["a.pdf", "b.xlsx", "c.docx"]:
            (tmp_path / name).touch()
        items = [self._item(n) for n in ["a.pdf", "b.xlsx", "c.docx"]]
        conflicts = drive_download._scan_conflicts(items, tmp_path)
        assert set(conflicts) == {"a.pdf", "b.xlsx", "c.docx"}

    def test_returns_rel_path_strings(self, tmp_path):
        (tmp_path / "report.pdf").touch()
        items = [self._item("report.pdf")]
        conflicts = drive_download._scan_conflicts(items, tmp_path)
        # Must be plain strings, not Path objects
        assert all(isinstance(c, str) for c in conflicts)
