import asyncio
from pathlib import Path
from uuid import UUID

import pytest
from playwright.async_api import BrowserContext, Route

import src.infrastructure.scrapers.plugins.mangadex as md_module
from src.domain.models import DOMChangeError, NetworkError, ParseError
from src.infrastructure.scrapers.plugins.mangadex.scraper import MangadexScraper

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "mangadex_sample.html"


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
    async def test_scraper_raises_parse_error_on_invalid_url(self, context: BrowserContext):
        scraper = MangadexScraper(context)
        bad_url = "https://mangadex.org/bad-url"

        with pytest.raises(ParseError) as exec_info:
            await scraper.fetch_metadata(bad_url)

        assert "Could not extract Manga UUID" in str(exec_info.value)

    async def test_scraper_raises_network_error_on_connection_failure(
        self, context: BrowserContext
    ):
        scraper = MangadexScraper(context)
        target_url = "https://mangadex.org/title/a96676e5-8ae2-425e-b549-7f15dd34a6d8"

        async def handle_route(route: Route):
            await route.abort("connectionrefused")

        await context.route("https://mangadex.org/title/*", handle_route)

        with pytest.raises(NetworkError) as exec_info:
            await scraper.fetch_metadata(target_url)

        assert "Network failure" in str(exec_info.value)

    async def test_scraper_raises_network_error_on_timeout(self, context: BrowserContext):
        target_url = "https://mangadex.org/title/a96676e5-8ae2-425e-b549-7f15dd34a6d8"

        context.set_default_navigation_timeout(50)

        async def handle_route(route):
            del route
            pass

        await context.route("**/*", handle_route)

        scraper = MangadexScraper(context)
        with pytest.raises(NetworkError, match="Network timeout"):
            await scraper.fetch_metadata(target_url)

    async def test_scraper_raises_dom_error_on_missing_selector(self, context: BrowserContext):
        target_url = "https://mangadex.org/title/a96676e5-8ae2-425e-b549-7f15dd34a6d8"

        async def handle_route(route):
            await route.fulfill(
                status=200, body="<html><body><h1>Cualquier cosa</h1></body></html>"
            )

        await context.route("**/*", handle_route)

        scraper = MangadexScraper(context)
        with pytest.raises(DOMChangeError, match="Possible DOM change"):
            await scraper.fetch_metadata(target_url)

    async def test_raises_dom_change_error_if_container_missing(
        self,
        context: BrowserContext,
        monkeypatch: pytest.MonkeyPatch,
    ):
        scraper = MangadexScraper(context)
        target_url = "https://mangadex.org/title/a96676e5-8ae2-425e-b549-7f15dd34a6d8"
        bad_html = "<html><body><h1>diferente</h1></body></html>"

        async def handle_route(route: Route):
            await route.fulfill(status=200, content_type="text/html", body=bad_html)

        await context.route("https://mangadex.org/title/*", handle_route)

        monkeypatch.setattr(md_module, "PAGE_LOAD_TIMEOUT_MS", 2000)

        with pytest.raises(DOMChangeError) as exec_info:
            await scraper.fetch_metadata(target_url)

        assert "Manga container CSS missing. Possible DOM change" in str(exec_info.value)

    async def test_missing_manga_data_raises_parse_error(
        self, context: BrowserContext, monkeypatch: pytest.MonkeyPatch
    ):
        scraper = MangadexScraper(context)
        target_url = "https://mangadex.org/title/a96676e5-8ae2-425e-b549-7f15dd34a6d8"

        bad_html = "<html><body><div class='layout-container manga'>Algo</div></body></html>"

        async def handle_route(route: Route):
            await route.fulfill(status=200, content_type="text/html", body=bad_html)

        await context.route("https://mangadex.org/title/*", handle_route)

        monkeypatch.setattr(md_module, "PAGE_LOAD_TIMEOUT_MS", 2000)

        with pytest.raises(ParseError) as exec_info:
            await scraper.fetch_metadata(target_url)

        assert "Could not get manga data" in str(exec_info.value)

    async def test_scraper_extracts_metadata_from_valid_html(
        self, context: BrowserContext, dummy_html: str
    ):
        scraper = MangadexScraper(context)
        test_uuid = "a96676e5-8ae2-425e-b549-7f15dd34a6d8"
        target_url = f"http://mock.local/title/{test_uuid}/komi-san"

        async def handle_network(route: Route):
            if route.request.resource_type == "document":
                await route.fulfill(status=200, content_type="text/html", body=dummy_html)
            else:
                await route.fulfill(status=200, content_type="application/javascript", body="")

        await context.route("**/*", handle_network)

        manga = await scraper.fetch_metadata(target_url)

        assert manga.uuid == UUID(test_uuid)
        assert manga.sources[0].target_url == target_url
        assert manga.name != "", "Scraper couldn't extract manga name"

    async def test_scraper_extracts_chapters_from_valid_html(
        self, context: BrowserContext, dummy_html: str
    ):
        scraper = MangadexScraper(context)
        test_uuid = "a96676e5-8ae2-425e-b549-7f15dd34a6d8"
        target_url = f"http://mock.local/title/{test_uuid}/komi-san"

        async def handle_network(route: Route):
            if route.request.resource_type == "document":
                await route.fulfill(status=200, content_type="text/html", body=dummy_html)
            else:
                await route.fulfill(status=200, content_type="application/javascript", body="")

        await context.route("**/*", handle_network)

        raw_chapters = await scraper.fetch_chapters(target_url)

        assert len(raw_chapters) > 0, "Scraper couldn't extract manga chapters"

    async def test_chapter_load_timeout_returns_zero_chapters(
        self, context: BrowserContext, monkeypatch: pytest.MonkeyPatch
    ):
        scraper = MangadexScraper(context)
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

        await context.route("https://mangadex.org/title/*", handle_route)

        monkeypatch.setattr(md_module, "CHAPTER_LOAD_TIMEOUT_MS", 2000)

        raw_chapters = await scraper.fetch_chapters(target_url)

        assert len(raw_chapters) == 0

    async def test_relative_thumbnail_url_is_resolved(self, context: BrowserContext):
        scraper = MangadexScraper(context)
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

        await context.route("https://mangadex.org/title/*", handle_route)

        manga = await scraper.fetch_metadata(target_url)

        assert manga.thumbnail == "https://mangadex.org/cover.jpg"
