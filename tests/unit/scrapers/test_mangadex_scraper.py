from dataclasses import dataclass
from unittest.mock import patch
from uuid import UUID

import httpx
import pytest
import respx

from src.domain.models import NetworkError, ParseError
from src.infrastructure.scrapers.plugins.mangadex.scraper import MangadexScraper

MOCK_METADATA_JSON = {
    "total": 1,
    "data": {
        "attributes": {
            "title": {
                "ja-ro": "One Piece",
            },
        },
        "relationships": [
            {
                "type": "author",
                "attributes": "Mefisto",
            },
            {
                "type": "cover_art",
                "attributes": {
                    "fileName": "img.png",
                },
            },
        ],
    },
}

MOCK_FEED_JSON = {
    "total": 2,
    "data": [
        {
            "id": "uuid-chapter-1",
            "attributes": {
                "chapter": "1",
                "title": "Normal Chapter",
                "translatedLanguage": "en",
                "externalUrl": None,
            },
        },
        {
            "id": "uuid-chapter-2",
            "attributes": {
                "chapter": "2",
                "title": "External Chapter",
                "translatedLanguage": "en",
                "externalUrl": "https://mangaplus.shueisha.co.jp/viewer/123",
            },
        },
    ],
}


VALID_UUID = "84703c86-eb83-45ec-8fc5-f34a25115893"


@dataclass(frozen=True)
class UrlContext:
    uuid: str
    target: str
    api_manga: str
    api_feed: str


@pytest.fixture
def url_context():
    return UrlContext(
        uuid=VALID_UUID,
        target=f"https://mangadex.org/title/{VALID_UUID}",
        api_manga=f"https://api.mangadex.org/manga/{VALID_UUID}",
        api_feed=f"https://api.mangadex.org/manga/{VALID_UUID}/feed",
    )


class TestMangadexScraperHappyPath:
    async def test_scraper_extracts_metadata_from_valid_api_response(self, url_context: UrlContext):
        scraper = MangadexScraper()

        with respx.mock:
            respx.get(url_context.api_manga).mock(
                return_value=httpx.Response(status_code=200, json=MOCK_METADATA_JSON)
            )
            manga = await scraper.fetch_metadata(url_context.target)

        assert manga.uuid == UUID(url_context.uuid)
        assert manga.sources[0].target_url == url_context.target
        assert manga.name != "", "Scraper couldn't extract manga name"
        assert manga.thumbnail == f"https://uploads.mangadex.org/covers/{url_context.uuid}/img.png"

    async def test_scraper_extracts_chapters_and_resolves_external_urls(
        self, url_context: UrlContext
    ):
        scraper = MangadexScraper()

        with respx.mock:
            respx.get(url_context.api_feed).mock(
                return_value=httpx.Response(status_code=200, json=MOCK_FEED_JSON)
            )
            raw_chapters = await scraper.fetch_chapters(url_context.target)

        assert len(raw_chapters) == 2
        assert raw_chapters[0].href == "https://mangadex.org/chapter/uuid-chapter-1"
        assert raw_chapters[1].href == "https://mangaplus.shueisha.co.jp/viewer/123"

    async def test_scraper_handles_missings_art_cover_gracefully(self, url_context: UrlContext):
        scraper = MangadexScraper()

        json_without_cover = {
            "data": {
                "attributes": {"title": {"en": "No Cover Manga"}},
                "relationships": [
                    {
                        "type": "cover_art",
                        "attributes": {},
                    },
                ],
            }
        }

        with respx.mock:
            respx.get(url_context.api_manga).mock(
                return_value=httpx.Response(200, json=json_without_cover)
            )
            manga = await scraper.fetch_metadata(url_context.target)

        assert manga.name == "No Cover Manga"
        assert manga.thumbnail == ""

    async def test_scraper_returns_empty_list_on_zero_chapters(self, url_context: UrlContext):
        scraper = MangadexScraper()

        mock_empty_json = {"total": 0, "data": []}

        with respx.mock:
            respx.get(url_context.api_feed).mock(
                return_value=httpx.Response(status_code=200, json=mock_empty_json)
            )
            raw_chapters = await scraper.fetch_chapters(url_context.target)

        assert raw_chapters == []

    async def test_scraper_paginates_chapter_correctly(self, url_context: UrlContext):
        scraper = MangadexScraper()

        page_1 = {
            "total": 750,
            "data": [
                {
                    "id": f"uuid{i}",
                    "attributes": {
                        "chapter": str(i),
                        "title": "",
                        "translatedLanguage": "es",
                        "externalUrl": None,
                    },
                }
                for i in range(500)
            ],
        }

        page_2 = {
            "total": 750,
            "data": [
                {
                    "id": f"uuid{i}",
                    "attributes": {
                        "chapter": str(i),
                        "title": "",
                        "translatedLanguage": "es",
                        "externalUrl": None,
                    },
                }
                for i in range(500, 750)
            ],
        }

        with patch("asyncio.sleep"), respx.mock:
            route = respx.get(url_context.api_feed).mock(
                side_effect=[
                    httpx.Response(200, json=page_1),
                    httpx.Response(200, json=page_2),
                ]
            )
            raw_chapters = await scraper.fetch_chapters(url_context.target)

        assert route.call_count == 2
        assert len(raw_chapters) == 750

    async def test_scraper_skips_malformed_chapters_and_keeps_parsing(
        self, url_context: UrlContext
    ):
        scraper = MangadexScraper()

        mixed_feed = {
            "total": 2,
            "data": [
                {
                    "id": "valid_chapter",
                    "attributes": {
                        "chapter": "1",
                        "title": "Valid",
                        "translatedLanguage": "es",
                        "externalUrl": None,
                    },
                },
                {
                    "id": "malformed_chapter",
                    "attributes": {},
                },
            ],
        }

        with respx.mock:
            respx.get(url_context.api_feed).mock(return_value=httpx.Response(200, json=mixed_feed))
            raw_chapters = await scraper.fetch_chapters(url_context.target)

        assert len(raw_chapters) == 1
        assert raw_chapters[0].raw_title == "Valid"

    async def test_scraper_recovers_and_succeeds_after_retries(self, url_context: UrlContext):
        scraper = MangadexScraper()

        with patch("asyncio.sleep") as mock_sleep, respx.mock:
            respx.get(url_context.api_manga).mock(
                side_effect=[
                    httpx.Response(502),
                    httpx.Response(502),
                    httpx.Response(200, json=MOCK_METADATA_JSON),
                ]
            )

            manga = await scraper.fetch_metadata(url_context.target)

        assert mock_sleep.call_count == 2
        assert manga.name != ""


def mock_metadata(respx_mock: respx.MockRouter, uuid: str, **kwargs) -> str:
    api_url = f"https://api.mangadex.org/manga/{uuid}"
    respx_mock.get(api_url).mock(**kwargs)
    return api_url


def mock_chapters(respx_mock: respx.MockRouter, uuid: str, **kwargs) -> str:
    api_url = f"https://api.mangadex.org/manga/{uuid}/feed"
    respx_mock.get(api_url).mock(**kwargs)
    return api_url


class TestMangadexScraperErrors:
    @pytest.mark.parametrize(
        "fetch_method,mock_api",
        [
            (MangadexScraper.fetch_metadata, mock_metadata),
            (MangadexScraper.fetch_chapters, mock_chapters),
        ],
    )
    @pytest.mark.parametrize(
        "exception,status_code,message",
        [
            (httpx.TimeoutException, 408, "Network timeout reaching"),
            (httpx.RequestError, 0, "Network failure"),
        ],
    )
    async def test_handles_network_errors_correctly(
        self, url_context: UrlContext, fetch_method, mock_api, exception, status_code, message
    ):
        scraper = MangadexScraper()

        with patch("asyncio.sleep") as mock_sleep, respx.mock as respx_mock:
            mock_api(respx_mock, url_context.uuid, side_effect=exception)

            with pytest.raises(NetworkError) as exec_info:
                await fetch_method(scraper, url_context.target)

        assert mock_sleep.call_count == 2
        assert message in str(exec_info.value)
        assert exec_info.value.status_code == status_code

    @pytest.mark.parametrize(
        "fetch_method,mock_api",
        [
            (MangadexScraper.fetch_metadata, mock_metadata),
            (MangadexScraper.fetch_chapters, mock_chapters),
        ],
    )
    async def test_scraper_respects_retry_after_header_on_429(
        self, url_context: UrlContext, fetch_method, mock_api
    ):
        scraper = MangadexScraper()

        with patch("asyncio.sleep") as mock_sleep, respx.mock as mock_respx:
            api_url = mock_api(
                mock_respx,
                url_context.uuid,
                return_value=httpx.Response(status_code=429, headers={"Retry-After": "15"}),
            )

            with pytest.raises(NetworkError) as exec_info:
                await fetch_method(scraper, url_context.target)

        mock_sleep.assert_any_call(15)

        assert f"HTTP status 429 reaching {api_url}" in str(exec_info.value)
        assert exec_info.value.status_code == 429

    @pytest.mark.parametrize(
        "fetch_method,mock_api",
        [
            (MangadexScraper.fetch_metadata, mock_metadata),
            (MangadexScraper.fetch_chapters, mock_chapters),
        ],
    )
    async def test_scraper_raises_network_error_on_generic_http_failure(
        self, url_context: UrlContext, fetch_method, mock_api
    ):
        scraper = MangadexScraper()

        with patch("asyncio.sleep"), respx.mock as mock_respx:
            api_url = mock_api(
                mock_respx, url_context.uuid, return_value=httpx.Response(status_code=502)
            )

            with pytest.raises(NetworkError) as exec_info:
                await fetch_method(scraper, url_context.target)

        assert f"HTTP status 502 reaching {api_url}" in str(exec_info.value)
        assert exec_info.value.status_code == 502

    @pytest.mark.parametrize(
        "fetch_method,mock_api",
        [
            (MangadexScraper.fetch_metadata, mock_metadata),
            (MangadexScraper.fetch_chapters, mock_chapters),
        ],
    )
    async def test_scraper_raises_parse_error_on_invalid_json(
        self, url_context: UrlContext, fetch_method, mock_api
    ):
        scraper = MangadexScraper()

        response = httpx.Response(
            200,
            content=b"Invalid JSON",
            headers={"Content-Type": "application/json"},
        )

        with respx.mock as respx_mock:
            mock_api(respx_mock, url_context.uuid, return_value=response)

            with pytest.raises(ParseError, match="Invalid JSON response from API"):
                await fetch_method(scraper, url_context.target)

    async def test_unexpected_api_schema_raises_parse_error(self, url_context: UrlContext):
        scraper = MangadexScraper()

        bad_json = {"data": {"id": url_context.uuid}}

        with respx.mock:
            respx.get(url_context.api_manga).mock(return_value=httpx.Response(200, json=bad_json))

            with pytest.raises(ParseError, match="Unexpected API response structure missing key"):
                await scraper.fetch_metadata(url_context.target)

    @pytest.mark.parametrize(
        "fetch_method",
        [
            MangadexScraper.fetch_metadata,
            MangadexScraper.fetch_chapters,
        ],
    )
    async def test_scraper_raises_parse_error_on_invalid_url(self, fetch_method):
        scraper = MangadexScraper()
        bad_url = "https://mangadex.org/bad-url"

        with pytest.raises(ParseError, match="Could not extract Manga UUID"):
            await fetch_method(scraper, bad_url)
