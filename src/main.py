import sys
from contextlib import closing

import psycopg
from playwright.sync_api import sync_playwright

from src.core.services import MangaSyncService
from src.domain.models import ConfigurationError
from src.infrastructure.database.postgres import PostgresRepository
from src.infrastructure.notifications.discord import DiscordNotifier
from src.infrastructure.scrapers.mangadex import MangadexScraper
from src.infrastructure.scrapers.parser import MangadexChapterParser
from src.logger import (
    bind_run_context,
    configure_logging,
    get_logger,
)

log = get_logger(__name__)


def main() -> None:
    configure_logging()
    run_context = bind_run_context()
    log.info("tracker_booting")

    try:
        from src.config import config
    except ConfigurationError as e:
        # GitHub actions would send the notification
        # to Discord with curl if load_config fails
        log.critical("configuration_failed", error=str(e))
        sys.exit(1)

    notifier = DiscordNotifier(config.discord_webhook_url)

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
        browser = p.chromium.launch(headless=True, executable_path=config.chromium_executable_path)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/118.0.5993.117 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            color_scheme="light",
        )

        db_repo = PostgresRepository(db_connection)
        scraper = MangadexScraper(context)
        parser = MangadexChapterParser()

        sync_service = MangaSyncService(
            db_repo=db_repo,
            scraper=scraper,
            parser=parser,
            notifier=notifier,
        )

        target_urls = db_repo.get_tracked_urls()
        if not target_urls:
            log.warning("no_urls_found_in_database")
            sys.exit(0)

        for url in target_urls:
            mangas_attempted += 1
            is_success = sync_service.execute(
                url,
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
