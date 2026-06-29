import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
import pytest_asyncio
from playwright.async_api import BrowserContext, Route, async_playwright
from playwright.async_api import Error as PlaywrightError

import src.infrastructure.scrapers.plugins.mangadex.scraper as scraper_module
from src.domain.models import DOMChangeError, NetworkError, ParseError
from src.infrastructure.scrapers.plugins.mangadex.scraper import MangadexScraper

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "mangadex_sample.html"


@pytest_asyncio.fixture()
async def async_browser_context():
    async with async_playwright() as p:
        chromium_path = os.getenv("CHROMIUM_EXECUTABLE_PATH")
        browser = await p.chromium.launch(executable_path=chromium_path)
        context = await browser.new_context()

        yield context

        await context.close()
        await browser.close()


@pytest.fixture
def dummy_html() -> str:
    """Read the static downloaded HTML to inject it in the browser"""

    if not FIXTURE_PATH.exists():
        return """
            <html>
                <body>
                    <div class="layout-container manga"></div>
                    <div class="line-clamp-1">Chapter List</div>
                </body>
            </html>
            """
    return FIXTURE_PATH.read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def bypass_async_retry_sleep(monkeypatch: pytest.MonkeyPatch):
    async def mock_sleep(*args, **kwargs):
        del args
        del kwargs
        pass

    monkeypatch.setattr(asyncio, "sleep", mock_sleep)


class TestMangadexScraper:
    async def test_scraper_raises_parse_error_on_invalid_url(
        self, async_browser_context: BrowserContext
    ):
        scraper = MangadexScraper(async_browser_context)
        bad_url = "https://mangadex.org/bad-url"

        with pytest.raises(ParseError) as exec_info:
            await scraper.fetch_metadata(bad_url)

        assert "Could not extract Manga UUID" in str(exec_info.value)

    async def test_scraper_raises_network_error_on_connection_failure(
        self, async_browser_context: BrowserContext
    ):
        scraper = MangadexScraper(async_browser_context)
        target_url = "https://mangadex.org/title/a96676e5-8ae2-425e-b549-7f15dd34a6d8"

        async def handle_route(route: Route):
            await route.abort("connectionrefused")

        await async_browser_context.route("https://mangadex.org/title/*", handle_route)

        with pytest.raises(NetworkError) as exec_info:
            await scraper.fetch_metadata(target_url)

        assert "Network failure" in str(exec_info.value)

    async def test_scraper_raises_network_error_on_timeout(
        self, async_browser_context: BrowserContext
    ):
        target_url = "https://mangadex.org/title/a96676e5-8ae2-425e-b549-7f15dd34a6d8"

        async_browser_context.set_default_navigation_timeout(50)

        async def handle_route(route):
            del route
            pass

        await async_browser_context.route("**/*", handle_route)

        scraper = MangadexScraper(async_browser_context)
        with pytest.raises(NetworkError, match="Network timeout"):
            await scraper.fetch_metadata(target_url)

    async def test_scraper_raises_dom_error_on_missing_selector(
        self, async_browser_context: BrowserContext
    ):
        target_url = "https://mangadex.org/title/a96676e5-8ae2-425e-b549-7f15dd34a6d8"

        async def handle_route(route):
            await route.fulfill(
                status=200, body="<html><body><h1>Cualquier cosa</h1></body></html>"
            )

        await async_browser_context.route("**/*", handle_route)

        scraper = MangadexScraper(async_browser_context)
        with pytest.raises(DOMChangeError, match="Possible DOM change"):
            await scraper.fetch_metadata(target_url)

    async def test_raises_dom_change_error_if_container_missing(
        self,
        async_browser_context: BrowserContext,
        monkeypatch: pytest.MonkeyPatch,
    ):
        scraper = MangadexScraper(async_browser_context)
        target_url = "https://mangadex.org/title/a96676e5-8ae2-425e-b549-7f15dd34a6d8"
        bad_html = "<html><body><h1>diferente</h1></body></html>"

        async def handle_route(route: Route):
            await route.fulfill(status=200, content_type="text/html", body=bad_html)

        await async_browser_context.route("https://mangadex.org/title/*", handle_route)

        monkeypatch.setattr(scraper_module, "PAGE_LOAD_TIMEOUT_MS", 2000)

        with pytest.raises(DOMChangeError) as exec_info:
            await scraper.fetch_metadata(target_url)

        assert "Manga container CSS missing. Possible DOM change" in str(exec_info.value)

    async def test_missing_manga_data_raises_parse_error(
        self, async_browser_context: BrowserContext, monkeypatch: pytest.MonkeyPatch
    ):
        scraper = MangadexScraper(async_browser_context)
        target_url = "https://mangadex.org/title/a96676e5-8ae2-425e-b549-7f15dd34a6d8"

        bad_html = "<html><body><div class='layout-container manga'>Algo</div></body></html>"

        async def handle_route(route: Route):
            await route.fulfill(status=200, content_type="text/html", body=bad_html)

        await async_browser_context.route("https://mangadex.org/title/*", handle_route)

        monkeypatch.setattr(scraper_module, "PAGE_LOAD_TIMEOUT_MS", 2000)

        with pytest.raises(ParseError) as exec_info:
            await scraper.fetch_metadata(target_url)

        assert "Could not get manga data" in str(exec_info.value)

    async def test_fetch_metadata_raises_dom_error_on_playwright_failure(
        self, async_browser_context: BrowserContext, monkeypatch: pytest.MonkeyPatch
    ):
        scraper = MangadexScraper(async_browser_context)
        target_url = "https://mangadex.org/title/a96676e5-8ae2-425e-b549-7f15dd34a6d8"

        mock_page = AsyncMock()
        mock_page.wait_for_selector.side_effect = PlaywrightError("Generic Playwright DOM Error")

        monkeypatch.setattr(async_browser_context, "new_page", AsyncMock(return_value=mock_page))

        with pytest.raises(
            DOMChangeError, match="Playwright DOM interaction failed: Generic Playwright DOM Error"
        ):
            await scraper.fetch_metadata(target_url)

    async def test_fetch_chapters_raises_network_error_on_playwright_timeout(
        self, async_browser_context: BrowserContext, monkeypatch: pytest.MonkeyPatch
    ):
        from playwright.async_api import TimeoutError as PlaywrightTimeoutError

        scraper = MangadexScraper(async_browser_context)
        target_url = "https://mangadex.org/title/a96676e5-8ae2-425e-b549-7f15dd34a6d8"

        mock_page = AsyncMock()
        mock_page.goto.side_effect = PlaywrightTimeoutError("Navigation time exceeded")

        monkeypatch.setattr(async_browser_context, "new_page", AsyncMock(return_value=mock_page))

        with pytest.raises(NetworkError, match=f"Network timeout reaching: {target_url}"):
            await scraper.fetch_chapters(target_url)

    async def test_fetch_chapters_raises_network_error_on_generic_playwright_error(
        self, async_browser_context: BrowserContext, monkeypatch: pytest.MonkeyPatch
    ):
        scraper = MangadexScraper(async_browser_context)
        target_url = "https://mangadex.org/title/a96676e5-8ae2-425e-b549-7f15dd34a6d8"

        mock_page = AsyncMock()
        mock_page.goto.side_effect = PlaywrightError("net::ERR_NAME_NOT_RESOLVED")

        monkeypatch.setattr(async_browser_context, "new_page", AsyncMock(return_value=mock_page))

        with pytest.raises(
            NetworkError, match="Network failure \\(DNS/Connection\\): net::ERR_NAME_NOT_RESOLVED"
        ):
            await scraper.fetch_chapters(target_url)

    async def test_scraper_extracts_metadata_from_valid_html(
        self, async_browser_context: BrowserContext, dummy_html: str
    ):
        scraper = MangadexScraper(async_browser_context)
        test_uuid = "a96676e5-8ae2-425e-b549-7f15dd34a6d8"
        target_url = f"http://mock.local/title/{test_uuid}/komi-san"

        async def handle_network(route: Route):
            if route.request.resource_type == "document":
                await route.fulfill(status=200, content_type="text/html", body=dummy_html)
            else:
                await route.fulfill(status=200, content_type="application/javascript", body="")

        await async_browser_context.route("**/*", handle_network)

        manga = await scraper.fetch_metadata(target_url)

        assert manga.uuid == UUID(test_uuid)
        assert manga.sources[0].target_url == target_url
        assert manga.name != "", "Scraper couldn't extract manga name"

    async def test_scraper_extracts_chapters_from_valid_html(
        self, async_browser_context: BrowserContext, dummy_html: str
    ):
        scraper = MangadexScraper(async_browser_context)
        test_uuid = "a96676e5-8ae2-425e-b549-7f15dd34a6d8"
        target_url = f"http://mock.local/title/{test_uuid}/komi-san"

        async def handle_network(route: Route):
            if route.request.resource_type == "document":
                await route.fulfill(status=200, content_type="text/html", body=dummy_html)
            else:
                await route.fulfill(status=200, content_type="application/javascript", body="")

        await async_browser_context.route("**/*", handle_network)

        raw_chapters = await scraper.fetch_chapters(target_url)

        assert len(raw_chapters) > 0, "Scraper couldn't extract manga chapters"

    async def test_chapter_load_timeout_returns_zero_chapters(
        self, async_browser_context: BrowserContext, monkeypatch: pytest.MonkeyPatch
    ):
        scraper = MangadexScraper(async_browser_context)
        target_url = "https://mangadex.org/title/a96676e5-8ae2-425e-b549-7f15dd34a6d8"

        soft_fail_html = """
        <html>
            <body>
                <div class="layout-container manga">
                    <div class="title">
                        <p>Fake Manga</p>
                    </div>
                    <div style='grid-area: art'>
                        <img alt='Cover image' src='https://fake.com/cover.jpg'>
                    </div>
                </div>
            </body>
        </html>
        """

        async def handle_route(route: Route):
            await route.fulfill(status=200, content_type="text/html", body=soft_fail_html)

        await async_browser_context.route("https://mangadex.org/title/*", handle_route)

        monkeypatch.setattr(scraper_module, "CHAPTER_LOAD_TIMEOUT_MS", 2000)

        raw_chapters = await scraper.fetch_chapters(target_url)

        assert len(raw_chapters) == 0

    async def test_relative_thumbnail_url_is_resolved(self, async_browser_context: BrowserContext):
        scraper = MangadexScraper(async_browser_context)
        target_url = "https://mangadex.org/title/a96676e5-8ae2-425e-b549-7f15dd34a6d8"

        relative_thumbnail_html = """
        <html>
            <body>
                <div class="layout-container manga">
                    <div class="title">
                        <p>Fake Manga</p>
                    </div>
                    <div style='grid-area: art'>
                        <img alt='Cover image' src='/cover.jpg'>
                    </div>
                </div>
            </body>
        </html>
        """

        async def handle_route(route: Route):
            await route.fulfill(status=200, content_type="text/html", body=relative_thumbnail_html)

        await async_browser_context.route("https://mangadex.org/title/*", handle_route)

        manga = await scraper.fetch_metadata(target_url)

        assert manga.thumbnail == "https://mangadex.org/cover.jpg"

    async def test_absolute_thumbnail_url(self, async_browser_context: BrowserContext):
        scraper = MangadexScraper(async_browser_context)
        target_url = "https://mangadex.org/title/a96676e5-8ae2-425e-b549-7f15dd34a6d8"

        relative_thumbnail_html = """
        <html>
            <body>
                <div class="layout-container manga">
                    <div class="title">
                        <p>Fake Manga</p>
                    </div>
                    <div style='grid-area: art'>
                        <img alt='Cover image' src='https://mangadex.org/cover.jpg'>
                    </div>
                </div>
            </body>
        </html>
        """

        async def handle_route(route: Route):
            await route.fulfill(status=200, content_type="text/html", body=relative_thumbnail_html)

        await async_browser_context.route("https://mangadex.org/title/*", handle_route)

        manga = await scraper.fetch_metadata(target_url)

        assert manga.thumbnail == "https://mangadex.org/cover.jpg"

    async def test_chapter_relative_href_is_resolved(self):
        mock_context = AsyncMock()
        scraper = MangadexScraper(mock_context)

        mock_page = AsyncMock()
        mock_page.evaluate.return_value = [
            {"info_text": "1", "header_text": "", "href": "/ruta-relativa", "language_title": "en"}
        ]
        mock_context.new_page.return_value = mock_page

        chapters = await scraper.fetch_chapters("https://mangadex.org/title/dummy")

        assert chapters[0].href == "https://mangadex.org/ruta-relativa"
