import asyncio
import re
from collections.abc import Awaitable, Callable
from functools import wraps
from pathlib import Path
from typing import Any, TypeVar, cast
from urllib.parse import urljoin
from uuid import UUID

from playwright.async_api import BrowserContext, Route
from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.core.ports import FetchMangaPort
from src.domain.models import (
    DOMChangeError,
    Manga,
    NetworkError,
    ParseError,
    RawChapter,
    Source,
)
from src.infrastructure.scrapers.factory import register_scraper
from src.logger import get_logger

PAGE_LOAD_TIMEOUT_MS = 20000
CHAPTER_LOAD_TIMEOUT_MS = 15000

_CURRENT_DIR = Path(__file__).parent
CHAPTER_EXTRACTOR_SCRIPT = (_CURRENT_DIR / "extract_chapters.js").read_text(encoding="utf-8")
MANGA_EXTRACTOR_SCRIPT = (_CURRENT_DIR / "extract_manga.js").read_text(encoding="utf-8")


logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def async_retry(retries: int = 3, delay: float = 2.0) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(1, retries + 1):
                try:
                    return await func(*args, **kwargs)
                except (NetworkError, PlaywrightTimeoutError) as e:
                    if attempt == retries:
                        logger.error(f"Failed operation after {retries} retries", error=str(e))
                        raise

                    wait_time = delay * attempt
                    logger.warning(
                        f"Network failure in attempt {attempt}/{retries}. Retrying in {wait_time}s",
                        error=str(e),
                    )
                    await asyncio.sleep(wait_time)

            raise RuntimeError("Unreachable")

        return cast(F, wrapper)

    return decorator


async def _intercept_route(route: Route) -> None:
    if route.request.resource_type in {"image", "media", "font", "stylesheet"}:
        await route.abort()
    else:
        await route.fallback()


@register_scraper("mangadex")
class MangadexScraper(FetchMangaPort):
    def __init__(self, context: BrowserContext, **kwargs: Any) -> None:
        del kwargs
        self.context = context

    @property
    def provider_name(self) -> str:
        return "mangadex"

    @async_retry(retries=3, delay=2)
    async def fetch_metadata(self, target_url: str) -> Manga:
        uuid_match = re.search(r"/title/([0-9a-fA-F-]{36})", target_url)
        if not uuid_match:
            raise ParseError(f"Could not extract Manga UUID from URL: {target_url}")

        manga_id = UUID(uuid_match.group(1))

        logger.info("scraper_navigation_started", url=target_url, target_manga_id=str(manga_id))

        page = await self.context.new_page()
        try:
            await page.route("**/*", _intercept_route)

            try:
                await page.goto(target_url, wait_until="domcontentloaded")
            except PlaywrightTimeoutError as e:
                raise NetworkError(f"Network timeout reaching: {target_url}") from e
            except PlaywrightError as e:
                raise NetworkError(f"Network failure (DNS/Connection): {str(e)}") from e

            try:
                await page.wait_for_selector(
                    "div.layout-container.manga",
                    timeout=PAGE_LOAD_TIMEOUT_MS,
                )
            except PlaywrightTimeoutError as e:
                raise DOMChangeError("Manga container CSS missing. Possible DOM change") from e
            except PlaywrightError as e:
                raise DOMChangeError(f"Playwright DOM interaction failed: {e}") from e

            manga_data = await page.evaluate(MANGA_EXTRACTOR_SCRIPT)
            manga_name = manga_data["name"]
            thumbnail = manga_data["thumbnail"]

            if not manga_name or not thumbnail:
                raise ParseError("Could not get manga data")

            if thumbnail and not thumbnail.startswith("https"):
                thumbnail = urljoin(target_url, thumbnail)

            current_source = Source(provider_name=self.provider_name, target_url=target_url)

            manga = Manga(manga_id, manga_name, thumbnail, sources=(current_source,))

            logger.info(
                "scraper_manga_data_extracted",
                manga_id=str(manga_id),
                manga_name=manga_name,
            )

            return manga
        finally:
            await page.close()

    @async_retry(retries=3, delay=2)
    async def fetch_chapters(self, target_url: str) -> list[RawChapter]:
        page = await self.context.new_page()
        try:
            await page.route("**/*", _intercept_route)
            try:
                await page.goto(target_url, wait_until="domcontentloaded")
            except PlaywrightTimeoutError as e:
                raise NetworkError(f"Network timeout reaching: {target_url}") from e
            except PlaywrightError as e:
                raise NetworkError(f"Network failure (DNS/Connection): {str(e)}") from e

            try:
                await page.wait_for_selector(
                    ".chapter-header", state="attached", timeout=CHAPTER_LOAD_TIMEOUT_MS
                )

                chapters_list = await page.evaluate(CHAPTER_EXTRACTOR_SCRIPT)

                raw_chapters_data = []
                for chapter_dict in chapters_list:
                    href = chapter_dict.get("href", "")
                    if href and not href.startswith("https"):
                        chapter_dict["href"] = urljoin(target_url, href)

                    raw_chapters_data.append(RawChapter(**chapter_dict))

                logger.debug("scraper_raw_chapters_extracted", count=len(raw_chapters_data))
            except PlaywrightTimeoutError:
                raw_chapters_data = []
                logger.warning("scraper_zero_chapters_found", url=target_url)

            return raw_chapters_data
        finally:
            await page.close()
