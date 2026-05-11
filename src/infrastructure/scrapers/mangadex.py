import re
from pathlib import Path
from urllib.parse import urljoin
from uuid import UUID

from playwright.sync_api import BrowserContext, Route
from playwright.sync_api import (
    Error as PlaywrightError,
)
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from src.domain.models import (
    DOMChangeError,
    Manga,
    NetworkError,
    ParseError,
    RawChapter,
)
from src.logger import get_logger

PAGE_LOAD_TIMEOUT_MS = 20000
CHAPTER_LOAD_TIMEOUT_MS = 3000

JS_DIR = Path(__file__).parent / "js"
CHAPTER_EXTRACTOR_PATH = JS_DIR / "extract_chapters.js"
MANGA_EXTRACTOR_PATH = JS_DIR / "extract_manga.js"

CHAPTER_EXTRACTOR_SCRIPT = CHAPTER_EXTRACTOR_PATH.read_text(encoding="utf-8")
MANGA_EXTRACTOR_SCRIPT = MANGA_EXTRACTOR_PATH.read_text(encoding="utf-8")


logger = get_logger(__name__)


def _intercept_route(route: Route) -> None:
    if route.request.resource_type in {"image", "media", "font", "stylesheet"}:
        route.abort()
    else:
        route.continue_()


class MangadexScraper:
    def __init__(self, context: BrowserContext) -> None:
        self.context = context

    def __call__(self, target_url: str) -> tuple[Manga, tuple[RawChapter, ...]]:
        raw_chapters_data: list[RawChapter] = []

        uuid_match = re.search(r"/title/([0-9a-fA-F-]{36})", target_url)
        if not uuid_match:
            raise ParseError(f"Could not extract Manga UUID from URL: {target_url}")

        manga_id = UUID(uuid_match.group(1))

        logger.info("scraper_navigation_started", url=target_url, target_manga_id=str(manga_id))

        with self.context.new_page() as page:
            page.route("**/*", _intercept_route)

            try:
                page.goto(target_url)
                page.wait_for_selector(
                    "div.layout-container.manga",
                    timeout=PAGE_LOAD_TIMEOUT_MS,
                )
            except PlaywrightTimeoutError as e:
                raise NetworkError(f"Page timeout loading: {target_url}") from e
            except PlaywrightError as e:
                raise DOMChangeError(f"Playwright navigation failed: {e}") from e

            manga_data = page.evaluate(MANGA_EXTRACTOR_SCRIPT)
            manga_name = manga_data["name"]
            thumbnail = manga_data["thumbnail"]

            if not manga_name or not thumbnail:
                raise ParseError("Could not get manga data")

            if thumbnail and not thumbnail.startswith("https"):
                thumbnail = urljoin(target_url, thumbnail)

            manga = Manga(manga_id, manga_name, thumbnail, target_url)

            logger.info(
                "scraper_manga_data_extracted",
                manga_id=str(manga_id),
                manga_name=manga_name,
            )

            try:
                page.wait_for_selector(".line-clamp-1", timeout=CHAPTER_LOAD_TIMEOUT_MS)
                chapters_list = page.evaluate(CHAPTER_EXTRACTOR_SCRIPT)
                raw_chapters_data = [RawChapter(**chapter) for chapter in chapters_list]

                logger.debug("scraper_raw_chapters_extracted", count=len(raw_chapters_data))
            except PlaywrightTimeoutError:
                raw_chapters_data = []

                logger.warning("scraper_zero_chapters_found", manga_id=str(manga_id))

        return manga, tuple(raw_chapters_data)
