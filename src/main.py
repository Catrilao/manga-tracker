import sys

from src.core.controllers import MangaBatchController
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

    try:
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

            controller = MangaBatchController(db_repo, sync_service)
            exit_code = controller.run_all(run_context)

    except Exception as e:
        log.critical("infrastructure_initialization_failed", error=str(e))
        notifier.send_error_notification("Fatal: infrastructure failure", 0xC0392B, run_context)
        sys.exit(1)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
