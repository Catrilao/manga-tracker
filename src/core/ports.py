from typing import Protocol
from uuid import UUID

from src.domain.models import Chapter, DBMetadata, Manga, RawChapter, RunContext, SyncPlan


class FetchMangaPort(Protocol):
    """
    Port to retrieve the raw data from the manga and its chapters

    Raises:
        NetworkError: If the target URL cannot be reached
        DOMChangeError: If the expected selectors are missing from the page
        ParseError: If there is data missing
    """

    def __call__(self, target_url: str) -> tuple[Manga, tuple[RawChapter, ...]]: ...


class ChapterParserPort(Protocol):
    """
    Protocol to transform raw scraped data into domain Chapters

    Raises:
        ParseError: If the raw data cannot be coerced into the required types
    """

    def __call__(
        self,
        manga_id: UUID,
        raw_chapters: tuple[RawChapter, ...],
    ) -> tuple[Chapter, ...]: ...


class DatabasePort(Protocol):
    """Unified contract for DB operations"""

    def get_metadata(self, manga_id: UUID) -> DBMetadata: ...
    def store_chapters(self, manga: Manga, plan: SyncPlan) -> None: ...
    def mark_as_notified(self, chapters: tuple[Chapter, ...]) -> None: ...
    def get_tracked_urls(self) -> tuple[str, ...]: ...


class NotifierPort(Protocol):
    """Protocol to send notifications"""

    def send_notification(
        self,
        manga_name: str,
        thumbnail: str,
        chapter: Chapter,
    ) -> bool: ...

    def send_error_notification(
        self,
        error_message: str,
        color: int,
        run_context: RunContext,
    ) -> None: ...
