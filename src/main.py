import asyncio
import sys

from playwright.async_api import async_playwright

from src.core.controllers import MangaBatchController
from src.core.services import MangaSyncService
from src.domain.models import ConfigurationError
from src.infrastructure.database.connection import get_db_connection
from src.infrastructure.database.postgres import PostgresRepository
from src.infrastructure.notifications.discord import DiscordNotifier
from src.infrastructure.scrapers import plugins  # noqa: F401
from src.infrastructure.scrapers.factory import ScraperFactory
from src.infrastructure.scrapers.parser import GenericParser
from src.logger import (
    bind_run_context,
    configure_logging,
    get_logger,
)

log = get_logger(__name__)


async def run_application() -> int:
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

    notifier = DiscordNotifier(config.discord_webhook)

    try:
        with get_db_connection(config.database_url) as db_connection:
            db_repo = PostgresRepository(db_connection)

            async with async_playwright() as p:
                browser = await p.chromium.launch(executable_path=config.chromium_executable_path)
                context = await browser.new_context()

                scraper_factory = ScraperFactory(context=context)
                parser = GenericParser()

                sync_service = MangaSyncService(
                    db_repo=db_repo,
                    scraper_factory=scraper_factory,
                    parser=parser,
                    notifier=notifier,
                )

                controller = MangaBatchController(db_repo=db_repo, sync_service=sync_service)
                exit_code = await controller.run_all(run_context)

                await context.close()
                await browser.close()

            return exit_code
    except Exception as e:
        log.critical("infrastructure_initialization_failed", error=str(e))
        notifier.send_error_notification("Fatal: infrastructure failure", 0xC0392B, run_context)
        return 1


def main() -> None:
    exit_code = asyncio.run(run_application())
    sys.exit(exit_code)


if __name__ == "__main__":  # pragma: no cover
    main()
