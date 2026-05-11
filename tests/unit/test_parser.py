from decimal import Decimal
from uuid import uuid4

import pytest

from src.domain.models import RawChapter
from src.infrastructure.scrapers.parser import MangadexChapterParser


@pytest.fixture
def parser():
    return MangadexChapterParser()


@pytest.fixture
def manga_id():
    return uuid4()


class TestMangadexChapterParserSuccess:
    """Tests for successful chapter parsing."""

    def test_parses_chapter_with_header_text(self, parser, manga_id):
        """Should extract chapter number from header_text."""
        raw_chapters = (
            RawChapter(
                info_text="Ch. 1 - Introduction",
                header_text="1",
                href="/chapter/abc123",
                language_title="English",
            ),
        )

        result = parser(manga_id, raw_chapters)

        assert len(result) == 1
        chapter = result[0]
        assert chapter.number == Decimal("1")
        assert chapter.name == "Introduction"
        assert chapter.manga_id == manga_id
        assert chapter.link == "https://mangadex.org/chapter/abc123"
        assert chapter.language == "English"

    def test_parses_chapter_with_decimal_number(self, parser, manga_id):
        """Should handle decimal chapter numbers like 1.5."""
        raw_chapters = (
            RawChapter(
                info_text="Ch. 1.5 - Side Story",
                header_text="1.5",
                href="/chapter/xyz",
                language_title="English",
            ),
        )

        result = parser(manga_id, raw_chapters)

        assert result[0].number == Decimal("1.5")
        assert result[0].name == "Side Story"

    def test_parses_chapter_number_from_info_text_fallback(self, parser, manga_id):
        """Should extract number from info_text if header_text fails."""
        raw_chapters = (
            RawChapter(
                info_text="Chapter 42 - The Answer",
                header_text="",
                href="/chapter/def456",
                language_title="English",
            ),
        )

        result = parser(manga_id, raw_chapters)

        assert result[0].number == Decimal("42")
        assert result[0].name == "The Answer"

    def test_resolves_relative_chapter_links(self, parser, manga_id):
        """Should convert relative URLs to absolute."""
        raw_chapters = (
            RawChapter(
                info_text="Ch. 5",
                header_text="5",
                href="/chapter/rel-path",
                language_title="English",
            ),
        )

        result = parser(manga_id, raw_chapters)

        assert result[0].link == "https://mangadex.org/chapter/rel-path"

    def test_preserves_absolute_chapter_links(self, parser, manga_id):
        """Should not modify absolute URLs."""
        raw_chapters = (
            RawChapter(
                info_text="Ch. 10",
                header_text="10",
                href="https://custom.com/ch/abc",
                language_title="English",
            ),
        )

        result = parser(manga_id, raw_chapters)

        assert result[0].link == "https://custom.com/ch/abc"

    def test_custom_base_url(self, parser, manga_id):
        """Should use custom base_url for relative links."""
        raw_chapters = (
            RawChapter(
                info_text="Ch. 3",
                header_text="3",
                href="/chapter/123",
                language_title="French",
            ),
        )

        result = parser(manga_id, raw_chapters, base_url="https://example.org")

        assert result[0].link == "https://example.org/chapter/123"

    def test_parses_multiple_chapters(self, parser, manga_id):
        """Should parse multiple chapters correctly."""
        raw_chapters = (
            RawChapter("Ch. 1 - Start", "1", "/ch/1", "English"),
            RawChapter("Ch. 2 - Continues", "2", "/ch/2", "English"),
            RawChapter("Ch. 2 - Continúa", "2", "/ch/2-es", "Spanish"),
        )

        result = parser(manga_id, raw_chapters)

        assert len(result) == 3
        assert result[0].number == Decimal("1")
        assert result[1].number == Decimal("2")
        assert result[2].language == "Spanish"

    def test_strips_whitespace_from_names(self, parser, manga_id):
        """Should strip leading/trailing whitespace from chapter names."""
        raw_chapters = (
            RawChapter(
                info_text="  Ch. 7 -   Extra Content   ",
                header_text="7",
                href="/ch/7",
                language_title="English",
            ),
        )

        result = parser(manga_id, raw_chapters)

        assert result[0].name == "Extra Content"


class TestMangadexChapterParserEdgeCases:
    """Tests for edge cases and invalid input."""

    def test_missing_chapter_number_sets_negative_one(self, parser, manga_id):
        """Should set number to -1.0 if no valid number found."""
        raw_chapters = (
            RawChapter(
                info_text="Some random text",
                header_text="",
                href="/chapter/unknown",
                language_title="English",
            ),
        )

        result = parser(manga_id, raw_chapters)

        assert result[0].number == Decimal("-1.0")

    def test_empty_href_preserved_as_empty_string(self, parser, manga_id):
        """Should preserve empty href (validation happens elsewhere)."""
        raw_chapters = (
            RawChapter(
                info_text="Ch. 5",
                header_text="5",
                href="",
                language_title="English",
            ),
        )

        result = parser(manga_id, raw_chapters)

        assert result[0].link == ""

    def test_empty_language_preserved(self, parser, manga_id):
        """Should preserve empty language (validation happens elsewhere)."""
        raw_chapters = (
            RawChapter(
                info_text="Ch. 1",
                header_text="1",
                href="/ch/1",
                language_title="",
            ),
        )

        result = parser(manga_id, raw_chapters)

        assert result[0].language == ""

    def test_case_insensitive_chapter_keyword_matching(self, parser, manga_id):
        """Should match 'CHAPTER', 'Chapter', 'chapter', 'CH.', 'ch.', etc."""
        raw_chapters = (
            RawChapter("CHAPTER 1 - Upper", "1", "/ch/1", "English"),
            RawChapter("chapter 2 - Lower", "2", "/ch/2", "English"),
            RawChapter("Ch. 3 - Abbreviated", "3", "/ch/3", "English"),
        )

        result = parser(manga_id, raw_chapters)

        assert all(chapter.name for chapter in result)
        assert result[0].name == "Upper"
        assert result[1].name == "Lower"
        assert result[2].name == "Abbreviated"

    def test_handles_chapter_with_no_name(self, parser, manga_id):
        """Should default to info_text if no name pattern matches."""
        raw_chapters = (
            RawChapter(
                info_text="Ch. 99",
                header_text="99",
                href="/ch/99",
                language_title="English",
            ),
        )

        result = parser(manga_id, raw_chapters)

        assert result[0].name == "Ch. 99"

    def test_returns_tuple_not_list(self, parser, manga_id):
        """Should always return a tuple, not a list."""
        raw_chapters = (RawChapter("Ch. 1", "1", "/ch/1", "English"),)

        result = parser(manga_id, raw_chapters)

        assert isinstance(result, tuple)
