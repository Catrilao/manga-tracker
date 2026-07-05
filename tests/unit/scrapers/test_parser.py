from dataclasses import dataclass
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest

from src.domain.models import ParseError
from src.infrastructure.scrapers.parser import GenericParser


@pytest.fixture
def parser():
    return GenericParser()


@pytest.fixture
def manga_id():
    return uuid4()


@dataclass(frozen=True)
class ExtractionCase:
    raw_number: str
    raw_title: str
    expected_number: Decimal
    expected_name: str


EXTRACTION_SCENARIOS = [
    pytest.param(
        ExtractionCase(
            raw_number="1",
            raw_title="Ch. 1 - Introduction",
            expected_number=Decimal("1"),
            expected_name="Introduction",
        ),
        id="integer_number",
    ),
    pytest.param(
        ExtractionCase(
            raw_number="1.5",
            raw_title="Ch. 1.5 - Side Story",
            expected_number=Decimal("1.5"),
            expected_name="Side Story",
        ),
        id="float_number",
    ),
    pytest.param(
        ExtractionCase(
            raw_number="",
            raw_title="Chapter 42 - The Answer",
            expected_number=Decimal("42"),
            expected_name="The Answer",
        ),
        id="empty_number",
    ),
    pytest.param(
        ExtractionCase(
            raw_number="Oneshot",
            raw_title="Chapter 0 - Prologue",
            expected_number=Decimal("0"),
            expected_name="Prologue",
        ),
        id="chapter_zero",
    ),
    pytest.param(
        ExtractionCase(
            raw_number="10",
            raw_title="Ch. 10",
            expected_number=Decimal("10"),
            expected_name="Ch. 10",
        ),
        id="title_is_a_number_no_dash",
    ),
    pytest.param(
        ExtractionCase(
            raw_number="20",
            raw_title="chapter 20 -lower case",
            expected_number=Decimal("20"),
            expected_name="lower case",
        ),
        id="weird_title",
    ),
    pytest.param(
        ExtractionCase(
            raw_number="Extras",
            raw_title="Artbook",
            expected_number=Decimal("-1.0"),
            expected_name="Artbook",
        ),
        id="no_number",
    ),
    pytest.param(
        ExtractionCase(
            raw_number="1",
            raw_title="",
            expected_number=Decimal("1"),
            expected_name="No name",
        ),
        id="no_title",
    ),
]


class TestGenericChapterParserExtraction:
    """Tests the core regex and text parsing engine."""

    @pytest.mark.parametrize("case", EXTRACTION_SCENARIOS)
    def test_regex_extraction_matrix(
        self, parser, manga_id, make_raw_chapter, case: ExtractionCase
    ):
        raw_chapter = make_raw_chapter(
            raw_number=case.raw_number,
            raw_title=case.raw_title,
            href="https://mangadex.org/chapter/valid",
        )

        result = parser(manga_id, (raw_chapter,))

        assert len(result) == 1
        chapter = result[0]
        assert chapter.number == case.expected_number
        assert chapter.name == case.expected_name
        assert chapter.manga_id == manga_id

    def test_parses_multiple_chapters_simultaneously(self, parser, manga_id, make_raw_chapter):
        raw_chapters = (
            make_raw_chapter(
                raw_number="1",
                raw_title="Ch. 1 - Start",
                language_title="English",
                href="https://mangadex.org/chapter/valid",
            ),
            make_raw_chapter(
                raw_number="3",
                raw_title="Ch. 2 - Continúa",
                language_title="Spanish",
                href="https://mangadex.org/chapter/valid",
            ),
        )

        result = parser(manga_id, raw_chapters)

        assert len(result) == 2
        assert result[0].number == Decimal("1")
        assert result[1].number == Decimal("3")


class TestGenericChapterParserLinks:
    """Tests URL resolution and formatting."""

    def test_preserves_relative_chapter_links(self, parser, manga_id, make_raw_chapter):
        raw = make_raw_chapter(href="/chapter/rel-path")
        result = parser(manga_id, (raw,))
        assert len(result) == 1
        assert result[0].link == "/chapter/rel-path"

    def test_preserves_absolute_chapter_links(self, parser, manga_id, make_raw_chapter):
        raw = make_raw_chapter(href="https://custom.com/ch/abc")
        result = parser(manga_id, (raw,))
        assert result[0].link == "https://custom.com/ch/abc"

    def test_preserves_empty_href(self, parser, manga_id, make_raw_chapter):
        raw = make_raw_chapter(href="")
        result = parser(manga_id, (raw,))
        assert len(result) == 1
        assert result[0].link == ""


class TestGenericChapterParserEdgeCases:
    """Tests structural edge cases and error handling."""

    def test_empty_language_preserved(self, parser, manga_id, make_raw_chapter):
        raw = make_raw_chapter(language_title="", href="https://valid.url")
        result = parser(manga_id, (raw,))
        assert result[0].language == ""

    def test_returns_tuple_not_list(self, parser, manga_id, make_raw_chapter):
        raw = make_raw_chapter()
        result = parser(manga_id, (raw,))
        assert isinstance(result, tuple)

    def test_raises_parse_error_on_model_validation_failure(
        self, parser, manga_id, make_raw_chapter
    ):
        """Si la data cruda rompe la validación estricta de Chapter, el error debe ser envuelto."""

        class InvalidStringObject:
            def __str__(self):
                raise ValueError("I cannot be a string")

        raw = make_raw_chapter(language_title=InvalidStringObject(), href="https://valid.url")

        with patch(
            "src.infrastructure.scrapers.parser.Chapter", side_effect=ValueError("Invalid data")
        ):
            with pytest.raises(ParseError) as exc_info:
                parser(manga_id, (raw,))

        assert "Failed to coerce raw data" in str(exc_info.value)
