from decimal import Decimal
from typing import Self
from uuid import uuid4

from src.core.use_cases import calculate_sync_plan
from src.domain.models import Chapter, ChapterIdentifier, DBMetadata, SyncPlan


class SyncPlanScenario:
    def __init__(self, make_chapter, make_db_metadata):
        self.make_chapter = make_chapter
        self.make_db_metadata = make_db_metadata

        self.scraped_chapters: list[Chapter] = []
        self.db_kwargs: dict = {"is_cold_start": True}

        self.manga_id = uuid4()

        self.plan: SyncPlan | None = None
        self.raised_error: Exception | None = None

    def with_active_series(self, chapter_count: int, max_chapter_number: int) -> Self:
        self.db_kwargs.update(
            {
                "manga_id": self.manga_id,
                "is_cold_start": False,
                "chapter_count": chapter_count,
                "max_chapter_number": Decimal(max_chapter_number),
            }
        )
        return self

    def with_existing_chapters(self, *identifiers: tuple[str, str]) -> Self:
        parsed = frozenset(
            ChapterIdentifier(self.manga_id, Decimal(num), lang) for num, lang in identifiers
        )
        self.db_kwargs["existing_chapter_identifiers"] = parsed
        return self

    def scraper_finds_chapters(
        self,
        *numbers: str,
        language: str = "en",
        name: str = "default",
    ) -> Self:
        for num in numbers:
            kwargs = {
                "manga_id": self.manga_id,
                "number": Decimal(num),
                "language": language,
                "name": name,
            }
            self.scraped_chapters.append(self.make_chapter(**kwargs))
        return self

    def scraper_finds_invalid_chapter(
        self, link: str = "valid", language: str = "es", number: str = "1"
    ) -> Self:
        self.scraped_chapters.append(
            self.make_chapter(link=link, language=language, number=Decimal(number))
        )
        return self

    def calculate(self) -> Self:
        db_state: DBMetadata = self.make_db_metadata(**self.db_kwargs)
        try:
            self.plan = calculate_sync_plan(self.scraped_chapters, db_state)
        except Exception as e:
            self.raised_error = e
        return self

    def assert_error_raised(self, expected_error: type[Exception], expected_text: str) -> Self:
        assert self.raised_error is not None, "Expected an error, but calculation succeeded"
        assert isinstance(self.raised_error, expected_error), (
            f"Expected {expected_error.__name__}, got {self.raised_error.__class__.__name__}"
        )
        assert expected_text in str(self.raised_error), (
            f"Expected text '{expected_text}', not found in '{str(self.raised_error)}'"
        )
        return self

    def assert_inserts(self, *expected_numbers: str) -> Self:
        assert self.plan is not None, f"Plan calculation failed: {self.raised_error}"
        inserted = [str(ch.number) for ch in self.plan.chapters_to_insert]
        assert sorted(inserted) == sorted(list(expected_numbers)), (
            f"Expected inserts: {expected_numbers}, got: {inserted}"
        )
        return self

    def assert_notifies(self, *expected_numbers: str) -> Self:
        assert self.plan is not None, f"Plan calculation failed: {self.raised_error}"
        notified = [str(ch.number) for ch in self.plan.chapters_to_notify]
        assert sorted(notified) == sorted(list(expected_numbers)), (
            f"Expected notifications: {expected_numbers}, got: {notified}"
        )
        return self

    def assert_warnings_logged(self, *expected_events: str) -> Self:
        assert self.plan is not None, f"Plan calculation failed: {self.raised_error}"
        logged = [log.event_name for log in self.plan.log_events]
        for event in expected_events:
            assert event in logged, f"Expected warning '{event}' not found. Logged: {logged}"
        return self
