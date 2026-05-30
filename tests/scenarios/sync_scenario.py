from collections.abc import Sequence
from decimal import Decimal
from typing import Any, Self

from structlog.testing import capture_logs
from structlog.typing import EventDict

from src.core.services import MangaSyncService
from src.domain.models import Chapter, ChapterIdentifier, Manga, RawChapter
from tests.doubles.database import FailingDatabaseStub, FakeDatabase
from tests.doubles.parser import ConfigurableParserStub, FailingParserStub
from tests.doubles.scraper import ConfigurableScraperStub, FailingScraperStub


class MangaSyncScenario:
    def __init__(
        self,
        run_context,
        mock_notifier,
        make_manga,
        make_raw_chapter,
        make_chapter,
        make_db_metadata,
    ) -> None:
        self.run_context = run_context
        self.mock_notifier = mock_notifier
        self.make_db_metadata = make_db_metadata
        self.make_manga = make_manga
        self.make_raw_chapter = make_raw_chapter
        self.make_chapter = make_chapter

        self.target_manga: Manga = self.make_manga()
        self.is_cold_start = True
        self.scraped_chapters: list[RawChapter] = []
        self.parsed_chapters: list[Chapter] = []
        self.existing_chapters: list[Chapter] = []

        self.db_error = None
        self.scraper_error = None
        self.parser_error = None

        self.is_success = None
        self.db = None
        self.scraper = None
        self.parser = None

        self.captured_logs: Sequence[EventDict] = []

    def existing_series_with_chapters(self, *chapter_numbers: str) -> Self:
        self.is_cold_start = False
        self.existing_chapters = [
            self.make_chapter(manga_id=self.target_manga.uuid, number=Decimal(num))
            for num in chapter_numbers
        ]
        return self

    def scraper_returns_chapters(self, *chapter_numbers: str) -> Self:
        for num in chapter_numbers:
            self.scraped_chapters.append(self.make_raw_chapter(header_text=f"Chapter {num}"))
            self.parsed_chapters.append(
                self.make_chapter(manga_id=self.target_manga.uuid, number=Decimal(num))
            )
        return self

    def notification_fails_for(self, *chapter_numbers) -> Self:
        for num in chapter_numbers:
            self.mock_notifier.chapters_to_fail.add(Decimal(num))
        return self

    def database_fails_with(self, error: Exception) -> Self:
        self.db_error = error
        return self

    def scraper_fails_with(self, error: Exception) -> Self:
        self.scraper_error = error
        return self

    def parser_fails_with(self, error: Exception) -> Self:
        self.parser_error = error
        return self

    def execute(self) -> Self:
        if self.db_error:
            self.db = FailingDatabaseStub(self.db_error)
        else:
            metadata_kwargs: dict[str, Any] = {"is_cold_start": self.is_cold_start}
            if not self.is_cold_start and self.existing_chapters:
                metadata_kwargs.update(
                    {
                        "chapter_count": len(self.existing_chapters),
                        "max_chapter_number": max(ch.number for ch in self.existing_chapters),
                        "existing_chapter_identifiers": frozenset(
                            ChapterIdentifier(self.target_manga.uuid, ch.number, ch.language)
                            for ch in self.existing_chapters
                        ),
                    }
                )
            self.db = FakeDatabase(stub_metadata=self.make_db_metadata(**metadata_kwargs))

        self.scraper = (
            FailingScraperStub(self.scraper_error)
            if self.scraper_error
            else ConfigurableScraperStub(self.target_manga, tuple(self.scraped_chapters))
        )

        self.parser = (
            FailingParserStub(self.parser_error)
            if self.parser_error
            else ConfigurableParserStub(tuple(self.parsed_chapters))
        )

        service = MangaSyncService(
            db_repo=self.db,
            scraper=self.scraper,
            parser=self.parser,
            notifier=self.mock_notifier,
        )

        with capture_logs() as cap_logs:
            self.is_success = service.execute(self.target_manga.url, self.run_context)

        self.captured_logs = cap_logs

        return self

    def assert_success(self, expected: bool = True) -> Self:
        assert self.is_success is expected, f"Expected success: {expected}, got {self.is_success}"
        return self

    def assert_notified_about(self, *chapter_numbers: str) -> Self:
        notified = [str(n["number"]) for n in self.mock_notifier.notifications_sent]
        for num in chapter_numbers:
            assert num in notified, f"Expected notification for {num}. Sent: {notified}"
        return self

    def assert_no_notifications(self) -> Self:
        assert len(self.mock_notifier.notifications_sent) == 0, "Expected 0 notifications sent"
        assert len(self.mock_notifier.errors_sent) == 0, "Expected 0 notifications sent"
        return self

    def assert_marked_as_notified(self, *chapter_numbers: str) -> Self:
        marked = []
        if isinstance(self.db, FakeDatabase):
            for chapter_tuple in self.db.notified_chapters:
                for ch in chapter_tuple:
                    marked.append(ch.number)

        for num in chapter_numbers:
            assert Decimal(num) in marked, f"Expected chapter {num} to be marked. Marked: {marked}"

        return self

    def assert_not_marked_as_notified(self, *chapter_numbers: str) -> Self:
        marked = []
        if isinstance(self.db, FakeDatabase):
            for chapter_tuple in self.db.notified_chapters:
                for ch in chapter_tuple:
                    marked.append(ch.number)

        for num in chapter_numbers:
            assert Decimal(num) not in marked, (
                f"Critical failure: Chapter {num} was marked as notified. "
                f"Currently marked: {marked}"
            )

        return self

    def assert_plans_stored(self, count: int) -> Self:
        stored = getattr(self.db, "stored_plans", [])
        assert len(stored) == count, f"Expected {count} plans, got {len(stored)}"
        return self

    def assert_error_notified(self, expected_message: str, expected_color: int) -> Self:
        assert len(self.mock_notifier.errors_sent) > 0, "No errors were notified"
        error = self.mock_notifier.errors_sent[0]
        assert expected_message in error["message"]
        assert error["color"] == expected_color
        return self

    def assert_no_side_effects(self) -> Self:
        self.assert_plans_stored(0)

        assert len(self.mock_notifier.notifications_sent) == 0, (
            "Expected 0 notifications, but the following were sent: "
            f"{self.mock_notifier.notifications_sent}"
        )

        if isinstance(self.db, FakeDatabase):
            assert len(self.db.notified_chapters) == 0, (
                "The database was expected to remain unchanged, but the following were marked"
                f"{self.db.notified_chapters}"
            )

        return self

    def assert_logging(self, expected_event: str, expected_level: str, **expected_kwargs) -> Self:
        matching_logs = [log for log in self.captured_logs if log.get("event") == expected_event]

        assert matching_logs, (
            f"Log event '{expected_event}' not found. "
            f"Captured event: {[log.get('event') for log in self.captured_logs]}"
        )

        target_log = matching_logs[0]
        assert target_log.get("log_level") == expected_level, (
            f"Expected level '{expected_level}' for event '{expected_event}', "
            f"but got '{target_log.get('log_level')}'"
        )

        if expected_kwargs:
            assert expected_kwargs.items() <= target_log.items(), (
                f"Missed or mismatched kwargs in log '{expected_event}'.\n"
                f"Expected subset: {expected_kwargs}\n"
                f"Actual log: {target_log}"
            )

        return self
