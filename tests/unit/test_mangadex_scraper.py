from unittest.mock import MagicMock
from urllib.parse import urljoin
from uuid import UUID

import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from src.domain.models import DOMChangeError, NetworkError, ParseError
from src.infrastructure.scrapers.mangadex import MangadexScraper


@pytest.fixture
def mock_page():
    page = MagicMock()
    page.__enter__.return_value = page
    page.__exit__.return_value = None
    return page


@pytest.fixture
def mock_context(mock_page):
    context = MagicMock()
    context.new_page.return_value = mock_page
    return context


@pytest.fixture
def scraper(mock_context):
    return MangadexScraper(mock_context)


class TestMangadexScraper:
    VALID_URL = "https://mangadex.org/title/84703c86-eb83-45ec-8fc5-f34a25115893"
    VALID_UUID = UUID("84703c86-eb83-45ec-8fc5-f34a25115893")

    def test_successful_extraction(self, scraper, mock_page):
        """Should return a Manga and a tuple of RawChapters on success."""
        mock_page.evaluate.side_effect = [
            {
                "name": "Dai Dark",
                "thumbnail": "https://example.com/thumb.jpg",
            },  # First evaluate (manga)
            [
                {
                    "info_text": "Ch. 1 - Bone 1",
                    "header_text": "1",
                    "href": "/chapter/abc",
                    "language_title": "English",
                }
            ],  # Second evaluate (chapters)
        ]

        manga, chapters = scraper(self.VALID_URL)

        assert manga.uuid == self.VALID_UUID
        assert manga.name == "Dai Dark"
        assert len(chapters) == 1
        assert chapters[0].href == "/chapter/abc"

        mock_page.goto.assert_called_once_with(self.VALID_URL)

    def test_relative_thumbnail_url_is_resolved(self, scraper, mock_page):
        """Should correctly join relative thumbnail URLs with the base target URL."""
        mock_page.evaluate.side_effect = [
            {"name": "Dai Dark", "thumbnail": "/covers/daidark.jpg"},
            [],
        ]

        manga, _ = scraper(self.VALID_URL)

        expected_url = urljoin(self.VALID_URL, "/covers/daidark.jpg")
        assert manga.thumbnail == expected_url

    def test_invalid_url_raises_parse_error(self, scraper):
        """Should fail immediately without opening a browser if URL lacks a UUID."""
        with pytest.raises(ParseError, match="Could not extract Manga UUID"):
            scraper("https://mangadex.org/title/invalid-url-format")

    def test_page_load_timeout_raises_network_error(self, scraper, mock_page):
        """Should translate PlaywrightTimeoutError on initial load to NetworkError."""
        mock_page.wait_for_selector.side_effect = PlaywrightTimeoutError("Timeout")

        with pytest.raises(NetworkError, match="Page timeout loading"):
            scraper(self.VALID_URL)

    def test_playwright_error_raises_dom_change_error(self, scraper, mock_page):
        """Should translate generic Playwright navigation errors to DOMChangeError."""
        mock_page.goto.side_effect = PlaywrightError("Navigation failed")

        with pytest.raises(DOMChangeError, match="Playwright navigation failed"):
            scraper(self.VALID_URL)

    def test_missing_manga_data_raises_parse_error(self, scraper, mock_page):
        """Should raise ParseError if JS extraction returns empty strings for manga info."""
        mock_page.evaluate.return_value = {"name": "", "thumbnail": ""}

        with pytest.raises(ParseError, match="Could not get manga data"):
            scraper(self.VALID_URL)

    def test_chapter_load_timeout_returns_zero_chapters(self, scraper, mock_page):
        """
        If the manga page loads but the chapters timeout, it should NOT crash.
        It should return the Manga info and an empty tuple for chapters.
        """

        mock_page.evaluate.return_value = {
            "name": "Dai Dark",
            "thumbnail": "https://example.com/thumb.jpg",
        }

        # First wait succeeds (None), second wait raises the timeout
        mock_page.wait_for_selector.side_effect = [None, PlaywrightTimeoutError("Timeout")]

        manga, chapters = scraper(self.VALID_URL)

        assert manga.name == "Dai Dark"
        assert len(chapters) == 0
