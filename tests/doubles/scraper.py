from src.domain.models import Manga, RawChapter


class ConfigurableScraperStub:
    def __init__(self, manga_to_return: Manga, raw_chapters_to_return: tuple[RawChapter, ...] = ()):
        self.manga = manga_to_return
        self.raw_chapters = raw_chapters_to_return

    def __call__(self, target_url: str) -> tuple[Manga, tuple[RawChapter, ...]]:
        del target_url
        return self.manga, self.raw_chapters


class FailingScraperStub:
    def __init__(self, exception_to_throw: Exception):
        self.error = exception_to_throw

    def __call__(self, target_url: str):
        del target_url
        raise self.error
