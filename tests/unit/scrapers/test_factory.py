import pytest

from src.infrastructure.scrapers.factory import _PLUGIN_REGISTRY, ScraperFactory, register_scraper
from tests.doubles.scraper import ConfigurableScraperStub


@pytest.fixture(autouse=True)
def clean_registry():
    _PLUGIN_REGISTRY.clear()
    yield
    _PLUGIN_REGISTRY.clear()


def test_factory_raises_value_error_for_unknown_provider():
    factory = ScraperFactory(context=None)

    with pytest.raises(ValueError, match="There's no registered plugin for the provider: "):
        factory.get_scraper("mentira")


def test_register_scraper_raises_value_error_on_duplicate():
    provider_name = "test_duplicate_scraper"

    class DummyScraper(ConfigurableScraperStub):
        pass

    register_scraper(provider_name)(DummyScraper)

    with pytest.raises(
        ValueError, match=f"There's already a plugin register to provider: '{provider_name}'"
    ):
        register_scraper(provider_name)(DummyScraper)
