from uuid import UUID

from src.domain.models import Chapter, RawChapter


class ConfigurableParserStub:
    def __init__(self, chapters_to_return: tuple[Chapter, ...] = ()):
        self.chapters = chapters_to_return

    def __call__(self, manga_id: UUID, raw_chapters: tuple[RawChapter, ...]) -> tuple[Chapter, ...]:
        _ = manga_id
        _ = raw_chapters
        return self.chapters


class FailingParserStub:
    def __init__(self, exception_to_throw: Exception):
        self.error = exception_to_throw

    def __call__(self, manga_id: UUID, raw_chapters: tuple[RawChapter, ...]):
        del manga_id
        del raw_chapters
        raise self.error
