from src.domain.models import Manga, RawChapter
from src.infrastructure.scrapers.factory import ScraperFactory


class ConfigurableScraperStub:
    def __init__(self, raw_chapters_to_return: list[RawChapter] | None = None):
        self.raw_chapters = [] if raw_chapters_to_return is None else raw_chapters_to_return

    @property
    def provider_name(self) -> str:
        return "test_provider"

    async def fetch_metadata(self, target_url: str) -> Manga:
        del target_url
        raise NotImplementedError("Orchestrator shouldn't call this")

    async def fetch_chapters(self, target_url: str) -> list[RawChapter]:
        del target_url
        return self.raw_chapters


class FailingScraperStub:
    def __init__(self, exception_to_throw: Exception):
        self.error = exception_to_throw

    @property
    def provider_name(self) -> str:
        return "test_provider"

    async def fetch_metadata(self, target_url: str) -> Manga:
        del target_url
        raise self.error

    async def fetch_chapters(self, target_url: str) -> list[RawChapter]:
        del target_url
        raise self.error


class FakeScraperFactory(ScraperFactory):
    def __init__(self, stub_to_return) -> None:
        self.stub = stub_to_return

    def get_scraper(self, provider_name: str):
        del provider_name
        return self.stub
