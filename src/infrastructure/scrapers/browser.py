from collections.abc import Generator
from contextlib import contextmanager

from playwright.sync_api import BrowserContext, sync_playwright


@contextmanager
def get_browser_context(
    executable_path: str | None = None,
) -> Generator[BrowserContext, None, None]:
    """
    Context manager to manage a headless Chromium browser context lifecycle
    """

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, executable_path=executable_path)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/118.0.5993.117 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            color_scheme="light",
        )

        try:
            yield context
        finally:
            context.close()
            browser.close()
