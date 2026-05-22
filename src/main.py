import sys

from src.core.services import MangaSyncService
from src.domain.models import ConfigurationError
from src.infrastructure.database.connection import get_db_connection
from src.infrastructure.database.postgres import PostgresRepository
from src.infrastructure.notifications.discord import DiscordNotifier
from src.infrastructure.scrapers.browser import get_browser_context
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

    mangas_attempted = 0
    mangas_succeeded = 0

    with (
        get_db_connection(config.database_url) as db_connection,
        get_browser_context(config.chromium_executable_path) as browser_context,
    ):
        db_repo = PostgresRepository(db_connection)
        scraper = MangadexScraper(browser_context)
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
