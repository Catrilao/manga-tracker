from uuid import UUID

from src.domain.models import Chapter, DBMetadata, Manga, RunContext, ScrapeAuditRecord, SyncPlan


class FakeDatabase:
    def __init__(
        self,
        stub_metadata: DBMetadata,
        tracked_urls: tuple[str, ...] = ("https://mangadex.org/title/fake-uuid",),
    ) -> None:
        self.stub_metadata = stub_metadata
        self.stored_plans: list[SyncPlan] = []
        self.notified_chapters: list[tuple[Chapter, ...]] = []
        self._tracked_urls = tracked_urls
        self.audit_records: list[ScrapeAuditRecord] = []

    def get_metadata(self, manga_id: UUID) -> DBMetadata:
        del manga_id
        return self.stub_metadata

    def store_chapters(self, manga: Manga, plan: SyncPlan) -> None:
        del manga
        self.stored_plans.append(plan)

    def mark_as_notified(self, chapters: tuple[Chapter, ...]) -> None:
        self.notified_chapters.append(chapters)

    def get_tracked_urls(self) -> tuple[str, ...]:
        return self._tracked_urls

    def save_audit_record(self, run_context: RunContext, record: ScrapeAuditRecord) -> None:
        del run_context
        self.audit_records.append(record)


class FailingDatabaseStub:
    def __init__(self, exception_to_throw: Exception):
        self.error = exception_to_throw

    def get_metadata(self, manga_id: UUID) -> DBMetadata:
        del manga_id
        raise self.error

    def store_chapters(self, manga: Manga, plan: SyncPlan) -> None:
        del manga
        del plan
        raise self.error

    def mark_as_notified(self, chapters: tuple[Chapter, ...]) -> None:
        del chapters
        raise self.error

    def get_tracked_urls(self) -> tuple[str, ...]:
        raise self.error

    def save_audit_record(self, run_context: RunContext, record: ScrapeAuditRecord) -> None:
        del run_context
        del record
        pass
