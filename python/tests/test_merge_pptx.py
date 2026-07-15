"""
Tests for merge_pptx.py — pure Markdown parsing and text processing.

Covers:
  - strip_md_formatting(): bold/italic/underscore removal
  - parse_markdown(): slide splitting, type detection, bullet parsing

python-pptx and lxml are mocked so these tests run without the venv's
optional slide-generation dependencies installed.

Run:
  venv/bin/pytest python/tests/test_merge_pptx.py -v
"""

import sys
import pytest
import textwrap
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

_SRC_DIR    = Path(__file__).resolve().parents[1]
_SLIDES_DIR = _SRC_DIR / "scripts" / "slides"
sys.path.insert(0, str(_SLIDES_DIR))

# Mock pptx / lxml so module-level constants (RGBColor etc.) can be set
# without the packages installed.  The pure logic under test (parse_markdown,
# strip_md_formatting) never touches these objects.
for _mod in [
    "pptx", "pptx.util", "pptx.dml", "pptx.dml.color",
    "pptx.oxml", "pptx.oxml.ns", "lxml", "lxml.etree",
]:
    sys.modules.setdefault(_mod, MagicMock())

import merge_pptx  # noqa: E402


# ── helpers ────────────────────────────────────────────────────

def _parse(md_text: str) -> list:
    """Write md_text to a temp file and return parse_markdown() result."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md",
                                     encoding="utf-8", delete=False) as f:
        f.write(textwrap.dedent(md_text))
        tmp = Path(f.name)
    try:
        return merge_pptx.parse_markdown(str(tmp))
    finally:
        tmp.unlink(missing_ok=True)


# ── strip_md_formatting ────────────────────────────────────────

class TestStripMdFormatting:
    """Markdown inline formatting is stripped; plain text is untouched."""

    def test_plain_text_unchanged(self):
        assert merge_pptx.strip_md_formatting("Hello World") == "Hello World"

    def test_bold_asterisks_removed(self):
        assert merge_pptx.strip_md_formatting("**bold**") == "bold"

    def test_italic_asterisk_removed(self):
        assert merge_pptx.strip_md_formatting("*italic*") == "italic"

    def test_bold_underscores_removed(self):
        assert merge_pptx.strip_md_formatting("__bold__") == "bold"

    def test_italic_underscore_removed(self):
        assert merge_pptx.strip_md_formatting("_italic_") == "italic"

    def test_mixed_formatting_removed(self):
        result = merge_pptx.strip_md_formatting("**bold** and *italic*")
        assert result == "bold and italic"

    def test_surrounding_whitespace_stripped(self):
        assert merge_pptx.strip_md_formatting("  hello  ") == "hello"

    def test_empty_string(self):
        assert merge_pptx.strip_md_formatting("") == ""

    def test_formatting_inside_sentence(self):
        result = merge_pptx.strip_md_formatting("This is **important** text")
        assert result == "This is important text"


# ── parse_markdown: slide count and splitting ──────────────────

class TestParseMarkdownSplitting:
    """``---`` on its own line separates slides; empty slides are dropped."""

    def test_single_slide(self):
        slides = _parse("# Title\n## Subtitle\n")
        assert len(slides) == 1

    def test_two_slides_split_by_separator(self):
        slides = _parse("# Slide 1\n\n---\n\n# Slide 2\n")
        assert len(slides) == 2

    def test_empty_slides_are_dropped(self):
        slides = _parse("# Real slide\n\n---\n\n---\n\n# Another real slide\n")
        assert len(slides) == 2

    def test_whitespace_only_slide_dropped(self):
        slides = _parse("# A\n\n---\n\n   \n\n---\n\n# B\n")
        assert len(slides) == 2


# ── parse_markdown: slide type detection ──────────────────────

class TestParseMarkdownTypeDetection:
    """Slide type is inferred from position and _class annotations."""

    def test_first_slide_defaults_to_title(self):
        slides = _parse("# Cover\n## Subtitle\n")
        assert slides[0]["type"] == "title"

    def test_second_slide_defaults_to_content(self):
        slides = _parse("# Cover\n\n---\n\n# Content Slide\n")
        assert slides[1]["type"] == "content"

    def test_explicit_title_class_on_later_slide(self):
        md = """\
            # Cover

            ---

            <!-- _class: title -->
            # Re-title slide
        """
        slides = _parse(md)
        assert slides[1]["type"] == "title"

    def test_explicit_section_class(self):
        md = """\
            # Cover

            ---

            <!-- _class: section -->
            # Section Break
        """
        slides = _parse(md)
        assert slides[1]["type"] == "section"

    def test_frontmatter_title_class(self):
        md = """\
            ---
            _class: title
            ---

            # Title from frontmatter
        """
        slides = _parse(md)
        assert slides[0]["type"] == "title"

    def test_html_comment_is_stripped_from_content(self):
        md = """\
            # Cover

            ---

            <!-- _class: section -->
            # Section
        """
        slides = _parse(md)
        # The comment must not appear in title or bullets
        assert "<!-- _class" not in slides[1]["title"]
        for b in slides[1]["bullets"]:
            assert "<!-- _class" not in b


# ── parse_markdown: field extraction ──────────────────────────

class TestParseMarkdownFields:
    """title, subtitle, and bullets are extracted correctly."""

    def test_h1_sets_title(self):
        slides = _parse("# My Title\n")
        assert slides[0]["title"] == "My Title"

    def test_h2_sets_subtitle(self):
        slides = _parse("# T\n## My Subtitle\n")
        assert slides[0]["subtitle"] == "My Subtitle"

    def test_dash_bullet(self):
        slides = _parse("# T\n- item one\n- item two\n")
        assert "item one" in slides[0]["bullets"]
        assert "item two" in slides[0]["bullets"]

    def test_asterisk_bullet(self):
        slides = _parse("# T\n* star item\n")
        assert "star item" in slides[0]["bullets"]

    def test_numbered_list(self):
        slides = _parse("# T\n1. first\n2. second\n")
        assert "first" in slides[0]["bullets"]
        assert "second" in slides[0]["bullets"]

    def test_h3_becomes_bullet(self):
        slides = _parse("# T\n### sub heading\n")
        assert "sub heading" in slides[0]["bullets"]

    def test_h4_becomes_bullet(self):
        slides = _parse("# T\n#### deep heading\n")
        assert "deep heading" in slides[0]["bullets"]

    def test_second_h2_becomes_bullet(self):
        """Only the first ## is a subtitle; subsequent ## are bullets."""
        slides = _parse("# T\n## Subtitle\n## Extra\n")
        assert slides[0]["subtitle"] == "Subtitle"
        assert "Extra" in slides[0]["bullets"]

    def test_plain_paragraph_becomes_bullet(self):
        slides = _parse("# T\nplain text line\n")
        assert "plain text line" in slides[0]["bullets"]

    def test_markdown_formatting_stripped_in_title(self):
        slides = _parse("# **Bold** Title\n")
        assert slides[0]["title"] == "Bold Title"

    def test_markdown_formatting_stripped_in_bullet(self):
        slides = _parse("# T\n- **strong** item\n")
        assert "strong item" in slides[0]["bullets"]

    def test_empty_title_when_no_h1(self):
        slides = _parse("## Only subtitle\n")
        assert slides[0]["title"] == ""

    def test_empty_bullets_when_no_list(self):
        slides = _parse("# T\n## S\n")
        assert slides[0]["bullets"] == []

    def test_blank_lines_ignored(self):
        slides = _parse("# Title\n\n## Subtitle\n\n- bullet\n")
        assert slides[0]["title"] == "Title"
        assert slides[0]["subtitle"] == "Subtitle"
        assert "bullet" in slides[0]["bullets"]
