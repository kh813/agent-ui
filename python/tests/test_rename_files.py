"""
Tests for rename_files.py — pure rename logic functions.

Run:
  venv/bin/pytest python/tests/test_rename_files.py -v
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime

_SRC_DIR   = Path(__file__).resolve().parents[1]
_TOOLS_DIR = _SRC_DIR / "scripts" / "tools"
sys.path.insert(0, str(_TOOLS_DIR))

import rename_files  # noqa: E402


# ── helpers ────────────────────────────────────────────────────

def _paths(*names: str) -> list:
    """Build Path objects under a fixed fake directory (no filesystem access needed)."""
    return [Path(f"/tmp/testdir/{n}") for n in names]


# ── _sequential ────────────────────────────────────────────────

class TestSequential:
    def test_custom_prefix(self):
        files = _paths("a.jpg", "b.jpg")
        pairs = rename_files._sequential(files, prefix="img", start=1, width=3, sep="_")
        assert pairs[0][1].name == "img_001.jpg"
        assert pairs[1][1].name == "img_002.jpg"

    def test_no_prefix_uses_stem(self):
        files = _paths("photo.jpg", "document.pdf")
        pairs = rename_files._sequential(files, prefix="", start=1, width=3, sep="_")
        assert pairs[0][1].name == "photo_001.jpg"
        assert pairs[1][1].name == "document_002.pdf"

    def test_start_number(self):
        files = _paths("x.txt")
        pairs = rename_files._sequential(files, prefix="f", start=5, width=2, sep="_")
        assert pairs[0][1].name == "f_05.txt"

    def test_custom_separator(self):
        files = _paths("x.txt")
        pairs = rename_files._sequential(files, prefix="doc", start=1, width=1, sep="-")
        assert pairs[0][1].name == "doc-1.txt"

    def test_width_pads_with_zeros(self):
        files = _paths("x.txt")
        pairs = rename_files._sequential(files, prefix="f", start=1, width=5, sep="_")
        assert pairs[0][1].name == "f_00001.txt"

    def test_width_does_not_truncate(self):
        # start=999 with width=2 → str(999).zfill(2) = "999" (no truncation)
        files = _paths("x.txt")
        pairs = rename_files._sequential(files, prefix="f", start=999, width=2, sep="_")
        assert pairs[0][1].name == "f_999.txt"

    def test_preserves_parent_directory(self):
        files = _paths("photo.jpg")
        pairs = rename_files._sequential(files, prefix="img", start=1, width=3, sep="_")
        assert pairs[0][1].parent == Path("/tmp/testdir")

    def test_empty_files_returns_empty(self):
        assert rename_files._sequential([], prefix="f", start=1, width=3, sep="_") == []

    def test_no_extension(self):
        files = _paths("README")
        pairs = rename_files._sequential(files, prefix="doc", start=1, width=2, sep="_")
        assert pairs[0][1].name == "doc_01"

    def test_consecutive_numbering(self):
        files = _paths("a.png", "b.png", "c.png")
        pairs = rename_files._sequential(files, prefix="p", start=1, width=2, sep="_")
        names = [p[1].name for p in pairs]
        assert names == ["p_01.png", "p_02.png", "p_03.png"]


# ── _replace ───────────────────────────────────────────────────

class TestReplace:
    def test_basic_replacement(self):
        files = _paths("report_2024.pdf", "photo_2024.jpg")
        pairs = rename_files._replace(files, "2024", "2025")
        assert pairs[0][1].name == "report_2025.pdf"
        assert pairs[1][1].name == "photo_2025.jpg"

    def test_no_match_returns_original(self):
        files = _paths("document.pdf")
        pairs = rename_files._replace(files, "XXXX", "YYYY")
        assert pairs[0][1].name == "document.pdf"

    def test_does_not_touch_extension(self):
        files = _paths("file.txt")
        pairs = rename_files._replace(files, "txt", "md")  # only stem is replaced
        assert pairs[0][1].name == "file.txt"

    def test_replaces_only_stem(self):
        files = _paths("old_name.old")
        pairs = rename_files._replace(files, "old", "new")
        assert pairs[0][1].name == "new_name.old"

    def test_multiple_occurrences_all_replaced(self):
        files = _paths("a_a_a.txt")
        pairs = rename_files._replace(files, "a", "b")
        assert pairs[0][1].name == "b_b_b.txt"

    def test_empty_files_returns_empty(self):
        assert rename_files._replace([], "old", "new") == []


# ── _regex ─────────────────────────────────────────────────────

class TestRegex:
    def test_basic_pattern(self):
        files = _paths("IMG_001.jpg", "IMG_002.jpg")
        pairs = rename_files._regex(files, r"IMG_(\d+)", r"photo_\1")
        assert pairs[0][1].name == "photo_001.jpg"
        assert pairs[1][1].name == "photo_002.jpg"

    def test_no_match_returns_original(self):
        files = _paths("document.pdf")
        pairs = rename_files._regex(files, r"XXXX", r"YYYY")
        assert pairs[0][1].name == "document.pdf"

    def test_does_not_touch_extension(self):
        files = _paths("file.txt")
        pairs = rename_files._regex(files, r"file", r"doc")
        assert pairs[0][1].name == "doc.txt"

    def test_partial_match(self):
        files = _paths("report_2024_final.docx")
        pairs = rename_files._regex(files, r"\d{4}", r"YYYY")
        assert pairs[0][1].name == "report_YYYY_final.docx"

    def test_remove_spaces(self):
        files = _paths("my document.pdf")
        pairs = rename_files._regex(files, r" ", r"_")
        assert pairs[0][1].name == "my_document.pdf"

    def test_invalid_pattern_exits(self):
        files = _paths("file.txt")
        with pytest.raises(SystemExit):
            rename_files._regex(files, r"[invalid", r"x")

    def test_empty_files_returns_empty(self):
        assert rename_files._regex([], r"\d+", r"N") == []


# ── _date_prefix (today mode) ──────────────────────────────────

class TestDatePrefixToday:
    def test_today_mode_uses_fixed_date(self):
        files = _paths("photo.jpg")
        fixed = datetime(2026, 5, 19)
        with patch("rename_files.datetime") as mock_dt:
            mock_dt.today.return_value = fixed
            mock_dt.fromtimestamp = datetime.fromtimestamp
            pairs = rename_files._date_prefix(files, "%Y%m%d", "_", "today")
        assert pairs[0][1].name == "20260519_photo.jpg"

    def test_custom_date_format(self):
        files = _paths("doc.pdf")
        fixed = datetime(2026, 1, 5)
        with patch("rename_files.datetime") as mock_dt:
            mock_dt.today.return_value = fixed
            mock_dt.fromtimestamp = datetime.fromtimestamp
            pairs = rename_files._date_prefix(files, "%y%m%d", "_", "today")
        assert pairs[0][1].name == "260105_doc.pdf"

    def test_custom_separator(self):
        files = _paths("file.txt")
        fixed = datetime(2026, 5, 19)
        with patch("rename_files.datetime") as mock_dt:
            mock_dt.today.return_value = fixed
            mock_dt.fromtimestamp = datetime.fromtimestamp
            pairs = rename_files._date_prefix(files, "%Y%m%d", "-", "today")
        assert pairs[0][1].name == "20260519-file.txt"

    def test_all_files_get_same_date_in_today_mode(self):
        files = _paths("a.txt", "b.txt", "c.txt")
        fixed = datetime(2026, 5, 19)
        with patch("rename_files.datetime") as mock_dt:
            mock_dt.today.return_value = fixed
            mock_dt.fromtimestamp = datetime.fromtimestamp
            pairs = rename_files._date_prefix(files, "%Y%m%d", "_", "today")
        prefixes = {p[1].name[:8] for p in pairs}
        assert prefixes == {"20260519"}

    def test_empty_files_returns_empty(self):
        with patch("rename_files.datetime") as mock_dt:
            mock_dt.today.return_value = datetime(2026, 5, 19)
            mock_dt.fromtimestamp = datetime.fromtimestamp
            assert rename_files._date_prefix([], "%Y%m%d", "_", "today") == []
