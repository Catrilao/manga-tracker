from collections.abc import Callable
from typing import Any, TypeVar

from src.core.ports import FetchMangaPort

_PLUGIN_REGISTRY: dict[str, type[FetchMangaPort]] = {}

T = TypeVar("T", bound=type[FetchMangaPort])


def register_scraper(provider_name: str) -> Callable[[T], T]:
    def decorator(cls: T) -> T:
        if provider_name in _PLUGIN_REGISTRY:
            raise ValueError(f"There's already a plugin register to provider: '{provider_name}'")

        _PLUGIN_REGISTRY[provider_name] = cls
        return cls

    return decorator


class ScraperFactory:
    def __init__(self, **dependencies: Any) -> None:
        self._registry: dict[str, type[FetchMangaPort]] = _PLUGIN_REGISTRY.copy()
        self._dependencies = dependencies

    def get_scraper(self, provider_name: str) -> FetchMangaPort:
        scraper_class = self._registry.get(provider_name)
        if not scraper_class:
            raise ValueError(f"There's no registered plugin for the provider: '{provider_name}'")

        return scraper_class(**self._dependencies)  # Line 32
