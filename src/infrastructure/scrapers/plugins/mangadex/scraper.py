import asyncio
import re
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar, cast
from uuid import UUID

import httpx

from src.core.ports import FetchMangaPort
from src.domain.models import (
    Manga,
    NetworkError,
    ParseError,
    RawChapter,
    Source,
)
from src.infrastructure.scrapers.factory import register_scraper
from src.logger import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Awaitable[Any]])


def async_retry(retries: int = 3, delay: float = 2.0) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            for attempt in range(1, retries + 1):
                try:
                    return await func(*args, **kwargs)
                except NetworkError as e:
                    if attempt == retries:
                        logger.error(f"Failed operation after {retries} retries", error=str(e))
                        raise

                    retry_after = getattr(e, "retry_after", None)
                    try:
                        wait_time = (
                            float(retry_after) if retry_after is not None else (delay * attempt)
                        )
                    except (TypeError, ValueError):
                        wait_time = delay * attempt

                    logger.warning(
                        f"Network failure in attempt {attempt}/{retries}. Retrying in {wait_time}s",
                        error=str(e),
                    )
                    await asyncio.sleep(wait_time)

            raise RuntimeError("Unreachable")  # pragma: no cover

        return cast(F, wrapper)

    return decorator


@register_scraper("mangadex")
class MangadexScraper(FetchMangaPort):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__()

    @property
    def provider_name(self) -> str:
        return "mangadex"

    def _extract_uuid(self, target_url: str) -> UUID:
        uuid_match = re.search(r"/title/([0-9a-fA-F-]{36})", target_url)
        if not uuid_match:
            raise ParseError(f"Could not extract Manga UUID from URL: {target_url}")
        return UUID(uuid_match.group(1))

    async def _http_get(
        self, client: httpx.AsyncClient, url: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            response = await client.get(url, params=params, timeout=15)

            if not response.is_success:
                error = NetworkError(
                    f"HTTP status {response.status_code} reaching {url}",
                    status_code=response.status_code,
                )
                if response.status_code == 429:
                    error.retry_after = response.headers.get("Retry-After", 5)
                raise error

            return cast(dict[str, Any], response.json())
        except httpx.TimeoutException as e:
            raise NetworkError(f"Network timeout reaching {url}", status_code=408) from e
        except httpx.RequestError as e:
            raise NetworkError(f"Network failure: {str(e)}", status_code=0) from e
        except ValueError as e:
            raise ParseError(f"Invalid JSON response from API: {str(e)}") from e

    @async_retry(retries=3, delay=2)
    async def fetch_metadata(self, target_url: str) -> Manga:
        manga_id = self._extract_uuid(target_url)
        logger.info("scraper_api_navigation_started", url=target_url, target_manga_id=str(manga_id))

        api_url = f"https://api.mangadex.org/manga/{manga_id}"

        headers = {"User-Agent": "MangaTracker/1.0 (GitHub Actions Bot)"}
        async with httpx.AsyncClient(headers=headers) as client:
            data = await self._http_get(client, api_url, params={"includes[]": "cover_art"})

            try:
                attributes = data["data"]["attributes"]

                title_dict = attributes.get("title", {})
                manga_name = next(iter(title_dict.values()), "Unknown") if title_dict else "Unknown"

                thumbnail = ""
                for rel in data["data"].get("relationships", []):
                    if rel.get("type") == "cover_art":
                        file_name = rel.get("attributes", {}).get("fileName")
                        if file_name:
                            thumbnail = (
                                f"https://uploads.mangadex.org/covers/{manga_id}/{file_name}"
                            )
                            break

                if not thumbnail:
                    logger.warning("scraper_manga_no_thumbnail", manga_id=str(manga_id))

            except (KeyError, TypeError) as e:
                raise ParseError(f"Unexpected API response structure missing key: {e}") from e

            current_source = Source(provider_name=self.provider_name, target_url=target_url)
            manga = Manga(manga_id, manga_name, thumbnail, sources=(current_source,))

            logger.info(
                "scraper_manga_data_extracted", manga_name=manga_name, manga_id=str(manga_id)
            )

            return manga

    @async_retry(retries=3, delay=2)
    async def fetch_chapters(self, target_url: str) -> list[RawChapter]:
        manga_id = self._extract_uuid(target_url)
        api_url = f"https://api.mangadex.org/manga/{manga_id}/feed"

        raw_chapters_data = []
        limit = 500
        offset = 0
        total = 1

        headers = {"User-Agent": "MangaTracker/1.0 (GitHub Actions Bot)"}
        async with httpx.AsyncClient(headers=headers) as client:
            while offset < total:
                params = {
                    "limit": limit,
                    "offset": offset,
                }

                data = await self._http_get(client, api_url, params)

                total = data.get("total", 0)
                items = data.get("data", [])

                if not items and offset == 0:
                    logger.warning("scraper_zero_chapters_found", url=target_url)
                    break

                for item in items:
                    try:
                        chapter_id = item["id"]
                        attributes = item["attributes"]

                        number = attributes["chapter"] or ""
                        name = attributes["title"] or ""
                        language = attributes["translatedLanguage"] or ""
                        link = (
                            attributes["externalUrl"]
                            or f"https://mangadex.org/chapter/{chapter_id}"
                        )

                        raw_chapters_data.append(
                            RawChapter(
                                raw_title=str(name),
                                raw_number=str(number),
                                href=link,
                                language_title=str(language),
                            )
                        )

                    except KeyError as e:
                        logger.warning(
                            "scraper_chapter_parse_error", chapter_id=item.get("id"), error=str(e)
                        )
                        continue

                offset += limit

                if offset < total:
                    await asyncio.sleep(0.2)

            logger.debug("scraper_raw_chapters_extracted", count=len(raw_chapters_data))
            return raw_chapters_data
