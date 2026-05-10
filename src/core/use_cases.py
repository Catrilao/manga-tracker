from decimal import Decimal
from types import MappingProxyType

from src.domain.models import (
    Chapter,
    DatabaseError,
    DBMetadata,
    DOMChangeError,
    LogEvent,
    LogLevel,
    ParseError,
    SyncPlan,
)


def calculate_sync_plan(
    scraped_chapters: list[Chapter],
    db_state: DBMetadata,
) -> SyncPlan:
    """
    Calculates the exact database operations required to sync the state.

    CONTRACT: This function acts as the data quality gatekeeper. It expects
    the scraper to provide raw, potentially invalid Chapter models. It is
    responsible for filtering out missing links, languages, and invalid
    numbers, and generating the corresponding LogEvents for telemetry.
    """

    if not db_state.is_cold_start:
        if db_state.max_chapter_number is None:
            raise DatabaseError("'max_number_db' is None but not cold start")

        if scraped_chapters and len(scraped_chapters) < db_state.chapter_count * 0.5:
            raise DOMChangeError("Error: Found less than 50% of chapters than before")

    null_count_scraper = 0
    warnings_to_log = []
    valid_chapters: list[Chapter] = []
    for chapter in scraped_chapters:
        if not chapter.link:
            null_count_scraper += 1
            warnings_to_log.append(
                LogEvent(
                    level=LogLevel.WARNING,
                    event_name="null_chapter_link",
                    context=MappingProxyType(
                        {
                            "manga_id": chapter.manga_id,
                            "chapter_name": chapter.name,
                        }
                    ),
                )
            )
            continue
        if not chapter.language:
            null_count_scraper += 1
            warnings_to_log.append(
                LogEvent(
                    LogLevel.WARNING,
                    event_name="null_chapter_language",
                    context=MappingProxyType(
                        {
                            "manga_id": chapter.manga_id,
                            "chapter_name": chapter.name,
                        }
                    ),
                )
            )
            continue
        if chapter.number == Decimal("-1.0"):
            null_count_scraper += 1
            warnings_to_log.append(
                LogEvent(
                    LogLevel.WARNING,
                    event_name="null_chapter_number",
                    context=MappingProxyType(
                        {
                            "manga_id": chapter.manga_id,
                            "chapter_name": chapter.name,
                        }
                    ),
                )
            )
            continue
        valid_chapters.append(chapter)

    if not scraped_chapters:
        raise DOMChangeError("Scraper returned zero chapters. Possible DOM change")
    null_ratio = null_count_scraper / len(scraped_chapters)
    if null_ratio > 0.3:
        raise ParseError(f"High volume (>=30%) of null chapters ({null_count_scraper} chapters)")

    max_number_scrapped = max(
        (c.number for c in valid_chapters),
        default=Decimal("-1.0"),
    )
    if (
        not db_state.is_cold_start
        and db_state.max_chapter_number is not None
        and max_number_scrapped < db_state.max_chapter_number
    ):
        raise ParseError("Max chapter in DB is bigger than the scraper's")

    # For chapters with the same language but different translation groups
    already_seen = set()

    chapters_to_insert = []
    chapters_to_notify = []
    for chapter in valid_chapters:
        identifier = (chapter.manga_id, chapter.number, chapter.language)
        if (
            identifier not in db_state.existing_chapter_identifiers
            and identifier not in already_seen
        ):
            chapters_to_insert.append(chapter)
            chapters_to_notify.append(chapter)
            already_seen.add(identifier)

    if db_state.is_cold_start:
        chapters_to_notify = []

    return SyncPlan(
        chapters_to_insert=tuple(chapters_to_insert),
        chapters_to_notify=tuple(chapters_to_notify),
        log_events=tuple(warnings_to_log),
    )
