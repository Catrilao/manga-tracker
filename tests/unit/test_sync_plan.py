from decimal import Decimal
from uuid import uuid4

import pytest

from src.core.use_cases import calculate_sync_plan
from src.domain.models import (
    Chapter,
    DatabaseError,
    DBMetadata,
    DOMChangeError,
    ParseError,
)


@pytest.fixture
def manga_id():
    return uuid4()


@pytest.fixture
def cold_start_db_state():
    return DBMetadata(
        is_cold_start=True,
        chapter_count=0,
        max_chapter_number=None,
        existing_chapter_identifiers=frozenset(),
    )


@pytest.fixture
def warm_start_db_state(manga_id):
    return DBMetadata(
        is_cold_start=False,
        chapter_count=5,
        max_chapter_number=Decimal("5.0"),
        existing_chapter_identifiers=frozenset(
            [
                (manga_id, Decimal("1.0"), "en"),
                (manga_id, Decimal("2.0"), "en"),
                (manga_id, Decimal("3.0"), "en"),
                (manga_id, Decimal("4.0"), "en"),
                (manga_id, Decimal("5.0"), "en"),
            ]
        ),
    )


class TestCalculateSyncPlanSuccess:
    """Tests for successful sync plan calculations."""

    def test_cold_start_with_valid_chapters(self, manga_id, cold_start_db_state):
        """Should insert and notify all chapters on cold start."""
        chapters = [
            Chapter(manga_id, Decimal("1.0"), "Ch 1", "link1", "en"),
            Chapter(manga_id, Decimal("2.0"), "Ch 2", "link2", "en"),
        ]

        result = calculate_sync_plan(chapters, cold_start_db_state)

        assert len(result.chapters_to_insert) == 2
        assert len(result.chapters_to_notify) == 0  # Cold start doesn't notify

        assert len(result.log_events) == 0

    def test_warm_start_with_new_chapters(self, manga_id, warm_start_db_state):
        """Should insert and notify only new chapters on warm start."""
        chapters = [
            Chapter(manga_id, Decimal("1.0"), "Ch 1", "link1", "en"),
            Chapter(manga_id, Decimal("2.0"), "Ch 2", "link2", "en"),
            Chapter(manga_id, Decimal("3.0"), "Ch 3", "link3", "en"),
            Chapter(manga_id, Decimal("4.0"), "Ch 4", "link4", "en"),
            Chapter(manga_id, Decimal("5.0"), "Ch 5", "link5", "en"),
            Chapter(manga_id, Decimal("6.0"), "Ch 6", "link6", "en"),
        ]

        result = calculate_sync_plan(chapters, warm_start_db_state)

        assert len(result.chapters_to_insert) == 1
        assert len(result.chapters_to_notify) == 1
        assert result.chapters_to_insert[0].number == Decimal("6.0")

    def test_multiple_languages_same_chapter(self, manga_id, cold_start_db_state):
        """Should handle multiple languages for the same chapter number."""
        chapters = [
            Chapter(manga_id, Decimal("1.0"), "Ch 1", "link1", "en"),
            Chapter(manga_id, Decimal("1.0"), "Ch 1", "link2", "fr"),
        ]

        result = calculate_sync_plan(chapters, cold_start_db_state)

        assert len(result.chapters_to_insert) == 2

    def test_duplicate_chapters_in_scrape(self, manga_id, cold_start_db_state):
        """Should deduplicate chapters with same identifier in scraper output."""
        chapters = [
            Chapter(manga_id, Decimal("1.0"), "Ch 1", "link1", "en"),
            Chapter(manga_id, Decimal("1.0"), "Ch 1", "link1", "en"),
        ]

        result = calculate_sync_plan(chapters, cold_start_db_state)

        assert len(result.chapters_to_insert) == 1


class TestCalculateSyncPlanFiltering:
    """Tests for chapter filtering logic."""

    def test_filters_chapters_with_null_link(self, manga_id, cold_start_db_state):
        """Should filter out chapters with missing links and log warning."""
        chapters = [
            Chapter(manga_id, Decimal("1.0"), "Ch 1", "link1", "en"),
            Chapter(manga_id, Decimal("2.0"), "Ch 2", "", "en"),
            Chapter(manga_id, Decimal("3.0"), "Ch 3", "link3", "en"),
            Chapter(manga_id, Decimal("4.0"), "Ch 4", "link4", "en"),
            Chapter(manga_id, Decimal("5.0"), "Ch 5", "link5", "en"),
        ]

        result = calculate_sync_plan(chapters, cold_start_db_state)

        assert len(result.chapters_to_insert) == 4
        assert len(result.log_events) == 1
        assert result.log_events[0].event_name == "null_chapter_link"

    def test_filters_chapters_with_null_language(self, manga_id, cold_start_db_state):
        """Should filter out chapters with missing language and log warning."""
        chapters = [
            Chapter(manga_id, Decimal("1.0"), "Ch 1", "link1", "en"),
            Chapter(manga_id, Decimal("2.0"), "Ch 2", "link2", "en"),
            Chapter(manga_id, Decimal("3.0"), "Ch 3", "link3", ""),
            Chapter(manga_id, Decimal("4.0"), "Ch 4", "link4", "en"),
            Chapter(manga_id, Decimal("5.0"), "Ch 5", "link5", "en"),
        ]

        result = calculate_sync_plan(chapters, cold_start_db_state)

        assert len(result.chapters_to_insert) == 4
        assert len(result.log_events) == 1
        assert result.log_events[0].event_name == "null_chapter_language"

    def test_filters_chapters_with_invalid_number(self, manga_id, cold_start_db_state):
        """Should filter out chapters with -1.0 number and log warning."""
        chapters = [
            Chapter(manga_id, Decimal("1.0"), "Ch 1", "link1", "en"),
            Chapter(manga_id, Decimal("2.0"), "Ch 2", "link2", "en"),
            Chapter(manga_id, Decimal("3.0"), "Ch 3", "link3", "en"),
            Chapter(manga_id, Decimal("-1.0"), "Ch ?", "link4", "en"),
            Chapter(manga_id, Decimal("5.0"), "Ch 5", "link5", "en"),
        ]

        result = calculate_sync_plan(chapters, cold_start_db_state)

        assert len(result.chapters_to_insert) == 4
        assert len(result.log_events) == 1
        assert result.log_events[0].event_name == "null_chapter_number"


class TestCalculateSyncPlanErrors:
    """Tests for error conditions."""

    def test_raises_error_on_zero_chapters(self, manga_id, cold_start_db_state):
        """Should raise DOMChangeError when scraper returns zero chapters."""
        with pytest.raises(DOMChangeError, match="Scraper returned zero chapters"):
            calculate_sync_plan([], cold_start_db_state)

    def test_raises_error_on_chapter_count_below_threshold(self, manga_id, warm_start_db_state):
        """Should raise DOMChangeError when chapters < 50% of previous count."""
        chapters = [
            Chapter(manga_id, Decimal("1.0"), "Ch 1", "link1", "en"),
            Chapter(manga_id, Decimal("6.0"), "Ch 6", "link6", "en"),
        ]

        with pytest.raises(DOMChangeError, match="less than 50%"):
            calculate_sync_plan(chapters, warm_start_db_state)

    def test_raises_error_on_high_null_ratio(self, manga_id, cold_start_db_state):
        """Should raise ParseError when null ratio exceeds 30%."""
        chapters = [
            Chapter(manga_id, Decimal("1.0"), "Ch 1", "link1", "en"),
            Chapter(manga_id, Decimal("2.0"), "Ch 2", "", "en"),
            Chapter(manga_id, Decimal("3.0"), "Ch 3", "", "en"),
            Chapter(manga_id, Decimal("4.0"), "Ch 4", "", "en"),
        ]

        with pytest.raises(ParseError, match="High volume"):
            calculate_sync_plan(chapters, cold_start_db_state)

    def test_raises_error_on_max_chapter_less_than_db(self, manga_id, warm_start_db_state):
        """Should raise ParseError when max scraped chapter < max in DB."""
        chapters = [
            Chapter(manga_id, Decimal("1.0"), "Ch 1", "link1", "en"),
            Chapter(manga_id, Decimal("2.0"), "Ch 2", "link2", "en"),
            Chapter(manga_id, Decimal("3.0"), "Ch 3", "link3", "en"),
        ]

        with pytest.raises(ParseError, match="Max chapter in DB is bigger"):
            calculate_sync_plan(chapters, warm_start_db_state)

    def test_raises_error_on_none_max_number_not_cold_start(self, manga_id):
        """Should raise DatabaseError when max_number is None but not cold start."""
        db_state = DBMetadata(
            is_cold_start=False,
            chapter_count=10,
            max_chapter_number=None,
            existing_chapter_identifiers=frozenset(),
        )
        chapters = [
            Chapter(manga_id, Decimal("1.0"), "Ch 1", "link1", "en"),
        ]

        with pytest.raises(DatabaseError, match="'max_number_db' is None"):
            calculate_sync_plan(chapters, db_state)
