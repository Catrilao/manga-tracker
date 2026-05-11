from typing import Protocol
from uuid import UUID

from src.domain.models import Chapter, DBMetadata, Manga, RawChapter, SyncPlan


class FetchMangaPort(Protocol):
    """
    Port to retrieve the raw data from the manga and its chapters

    Raises:
        NetworkError: If the target URL cannot be reached
        DOMChangeError: If the expected selectors are missing from the page
        ParseError: If there is data missing
    """

    def __call__(self, target_url: str) -> tuple[Manga, tuple[RawChapter, ...]]: ...


class GetDBMetadataPort(Protocol):
    """
    Port to retrieve the current state of a manga in the DB

    Raises:
        DatabaseError: If the connection fails or the query is invalid
    """

    def __call__(self, manga_id: UUID) -> DBMetadata: ...


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


class StoreChaptersPort(Protocol):
    """Protocol to store new chapters in the DB

    Raises:
        DatabaseError: If the connection fails or the query is invalid
    """

    def __call__(self, manga: Manga, plan: SyncPlan) -> None: ...


class MarkNotifiedChaptersPort(Protocol):
    """Protocol that mark which chapters were notified

    Raises:
        DatabaseError: If the connection fails or the query is invalid
    """

    def __call__(self, chapters: tuple[Chapter, ...]) -> None: ...
