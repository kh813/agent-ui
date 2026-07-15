"""
Tests for markitdown_convert.py — pure logic functions.

Covers:
  - _is_convertible(): extension allow/block list
  - _find_convertible_files(): directory scanning behaviour
  - _convert_file(): dry-run path (no MarkItDown needed)

Run:
  venv/bin/pytest python/tests/test_markitdown_convert.py -v
"""

import sys
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

_SRC_DIR   = Path(__file__).resolve().parents[1]
_TOOLS_DIR = _SRC_DIR / "scripts" / "tools"
sys.path.insert(0, str(_TOOLS_DIR))

# Mock markitdown before import so _ensure_markitdown() returns immediately
# without attempting to install the package or re-exec the process.
sys.modules.setdefault("markitdown", MagicMock())

import markitdown_convert  # noqa: E402


# ── _is_convertible ────────────────────────────────────────────

class TestIsConvertible:
    """Extension allow/block list and edge cases."""

    @pytest.mark.parametrize("filename", [
        "report.pdf",
        "doc.docx", "legacy.doc",
        "slides.pptx", "old.ppt",
        "data.xlsx", "sheet.xls", "table.csv",
        "page.html", "page.htm",
        "data.xml", "config.json",
        "notes.txt", "rich.rtf", "book.epub",
        "archive.zip",
        "photo.png", "img.jpg", "img.jpeg",
        "anim.gif", "image.webp", "bitmap.bmp", "scan.tiff",
        "audio.mp3", "sound.wav", "voice.m4a", "music.ogg",
    ])
    def test_supported_extensions(self, filename):
        assert markitdown_convert._is_convertible(Path(filename))

    @pytest.mark.parametrize("filename", [
        "README.md",          # .md is the output format — must be excluded
        "script.py",
        "binary.exe",
        "data.parquet",
        "video.mp4",
        "noextension",
    ])
    def test_unsupported_extensions(self, filename):
        assert not markitdown_convert._is_convertible(Path(filename))

    @pytest.mark.parametrize("filename", [
        "DOCUMENT.PDF",
        "Photo.PNG",
        "Sheet.XLSX",
    ])
    def test_case_insensitive(self, filename):
        assert markitdown_convert._is_convertible(Path(filename))


# ── _find_convertible_files ────────────────────────────────────

class TestFindConvertibleFiles:
    """Directory scanning: which files are returned and in what order."""

    def test_empty_directory(self, tmp_path):
        assert markitdown_convert._find_convertible_files(tmp_path) == []

    def test_nonexistent_directory(self, tmp_path):
        assert markitdown_convert._find_convertible_files(tmp_path / "no_such_dir") == []

    def test_returns_convertible_files(self, tmp_path):
        (tmp_path / "a.pdf").touch()
        (tmp_path / "b.docx").touch()
        result = markitdown_convert._find_convertible_files(tmp_path)
        names = [f.name for f in result]
        assert "a.pdf" in names
        assert "b.docx" in names

    def test_excludes_md_files(self, tmp_path):
        (tmp_path / "notes.md").touch()
        (tmp_path / "report.pdf").touch()
        result = markitdown_convert._find_convertible_files(tmp_path)
        names = [f.name for f in result]
        assert "notes.md" not in names
        assert "report.pdf" in names

    def test_excludes_dotfiles(self, tmp_path):
        (tmp_path / ".hidden.pdf").touch()
        (tmp_path / "visible.pdf").touch()
        result = markitdown_convert._find_convertible_files(tmp_path)
        names = [f.name for f in result]
        assert ".hidden.pdf" not in names
        assert "visible.pdf" in names

    def test_excludes_unsupported_extensions(self, tmp_path):
        (tmp_path / "script.py").touch()
        (tmp_path / "video.mp4").touch()
        (tmp_path / "doc.pdf").touch()
        result = markitdown_convert._find_convertible_files(tmp_path)
        names = [f.name for f in result]
        assert "script.py" not in names
        assert "video.mp4" not in names
        assert "doc.pdf" in names

    def test_excludes_subdirectories(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "file.pdf").touch()
        result = markitdown_convert._find_convertible_files(tmp_path)
        names = [f.name for f in result]
        assert "subdir" not in names
        assert "file.pdf" in names

    def test_result_is_sorted(self, tmp_path):
        for name in ["c.pdf", "a.docx", "b.xlsx"]:
            (tmp_path / name).touch()
        result = markitdown_convert._find_convertible_files(tmp_path)
        names = [f.name for f in result]
        assert names == sorted(names)


# ── _convert_file (dry_run) ────────────────────────────────────

class TestConvertFileDryRun:
    """Dry-run mode never calls MarkItDown and always succeeds."""

    def test_dry_run_returns_success(self, tmp_path):
        src = tmp_path / "report.pdf"
        src.touch()
        ok, out, msg, size_kb = markitdown_convert._convert_file(src, dry_run=True)
        assert ok is True
        assert msg == "[DRY-RUN]"
        assert size_kb == 0

    def test_dry_run_output_path_has_md_suffix(self, tmp_path):
        src = tmp_path / "document.docx"
        src.touch()
        _, out, _, _ = markitdown_convert._convert_file(src, dry_run=True)
        assert out.suffix == ".md"
        assert out.stem == "document"

    def test_dry_run_default_output_dir_is_same_as_input(self, tmp_path):
        src = tmp_path / "data.xlsx"
        src.touch()
        _, out, _, _ = markitdown_convert._convert_file(src, dry_run=True)
        assert out.parent == tmp_path

    def test_dry_run_custom_output_dir(self, tmp_path):
        src = tmp_path / "slides.pptx"
        src.touch()
        out_dir = tmp_path / "output"
        _, out, _, _ = markitdown_convert._convert_file(src, out_dir, dry_run=True)
        assert out.parent == out_dir

    def test_dry_run_does_not_create_files(self, tmp_path):
        src = tmp_path / "report.pdf"
        src.touch()
        markitdown_convert._convert_file(src, dry_run=True)
        # Only the source should exist — no .md file created
        assert list(tmp_path.glob("*.md")) == []
