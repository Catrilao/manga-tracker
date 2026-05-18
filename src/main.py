import sys
from contextlib import closing

import psycopg
from playwright.sync_api import sync_playwright

from src.config import load_config
from src.core.use_cases import calculate_sync_plan
from src.domain.models import ConfigurationError, RunContext, TrackerBaseException
from src.infrastructure.database.postgres import PostgresRepository
from src.infrastructure.notifications.discord import DiscordNotifier
from src.infrastructure.scrapers.mangadex import MangadexScraper
from src.infrastructure.scrapers.parser import MangadexChapterParser
from src.logger import (
    bind_run_context,
    configure_logging,
    execute_log_event,
    get_logger,
    manga_log_context,
)

log = get_logger(__name__)


def process_manga_url(
    url: str,
    db_repo: PostgresRepository,
    scraper: MangadexScraper,
    parser: MangadexChapterParser,
    notifier: DiscordNotifier,
    run_context: RunContext,
) -> bool:
    """
    Coordinates the side-effects and passes the result
    into the functional core
    """

    try:
        manga, raw_chapters = scraper(url)

        with manga_log_context(manga.uuid, manga.name, manga.url):
            parsed_chapters = parser(manga.uuid, raw_chapters)

            db_metadata = db_repo.get_metadata(manga.uuid)

            plan = calculate_sync_plan(parsed_chapters, db_metadata)

            for event in plan.log_events:
                execute_log_event(event)

            db_repo.store_chapters(manga, plan)

            notified_chapters = []
            for chapter in plan.chapters_to_notify:
                success = notifier.send_notification(manga.name, manga.thumbnail, chapter)
                if success:
                    notified_chapters.append(chapter)

            if notified_chapters:
                db_repo.mark_as_notified(tuple(notified_chapters))

            log.info("manga_sync_completed", new_chapters=len(plan.chapters_to_insert))
            return True
    except TrackerBaseException as e:
        log.error("manga_sync_failed", error=str(e), error_class=type(e).__name__)
        notifier.send_error_notification(str(e), e.color_code, run_context)
        return False
    except Exception as e:
        log.critical("manga_sync_crashed", error=str(e), error_class=type(e).__name__)
        notifier.send_error_notification(f"Critical crash: {str(e)}", 0xC0392B, run_context)
        return False


def main() -> None:
    configure_logging()
    run_context = bind_run_context()
    log.info("tracker_booting")

    try:
        config = load_config()
    except ConfigurationError as e:
        # GitHub actions would send the notification
        # to Discord with curl if load_config fails
        log.critical("configuration_failed", error=str(e))
        sys.exit(1)

    notifier = DiscordNotifier(config.discord_webhook_url)
    parser = MangadexChapterParser()

    try:
        raw_connection = psycopg.connect(config.database_url)
        raw_connection.autocommit = True
    except Exception as e:
        log.critical("database_connection_failed", error=str(e))
        notifier.send_error_notification("Fatal: could not connect to DB", 0xC0392B, run_context)
        sys.exit(1)

    mangas_attempted = 0
    mangas_succeeded = 0

    with closing(raw_connection) as db_connection, sync_playwright() as p:
        db_repo = PostgresRepository(db_connection)

        target_urls = db_repo.get_tracked_urls()
        if not target_urls:
            log.warning("no_urls_found_in_database")
            sys.exit(0)

        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/118.0.5993.117 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            color_scheme="light",
        )

        scraper = MangadexScraper(context)

        for url in target_urls:
            mangas_attempted += 1
            is_success = process_manga_url(
                url,
                db_repo,
                scraper,
                parser,
                notifier,
                run_context,
            )
            if is_success:
                mangas_succeeded += 1

        context.close()
        browser.close()

    if mangas_succeeded == 0 and mangas_attempted > 0:
        log.critical("run_failed_completely", attempted=mangas_attempted)
        sys.exit(1)
    elif mangas_succeeded < mangas_attempted:
        log.warning(
            "run_completed_with_failures",
            attempted=mangas_attempted,
            succeeded=mangas_succeeded,
        )
        sys.exit(1)
    else:
        log.info("run_completed_successfully", attempted=mangas_attempted)
        sys.exit(0)


if __name__ == "__main__":
    main()
