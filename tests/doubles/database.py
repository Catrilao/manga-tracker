from uuid import UUID

from src.domain.models import (
    Chapter,
    DBMetadata,
    Manga,
    RunContext,
    ScrapeAuditRecord,
    Source,
    SyncPlan,
)

DEFAULT_FAKE_MANGA = Manga(
    uuid=UUID("12345678-1234-1234-1234-123456789123"),
    name="Manga Falso",
    thumbnail="https://thumbnail.fake/image.png",
    sources=[
        Source(provider_name="mangadex", target_url="https://mangadex.org/fake", is_active=True)
    ],
)


class FakeDatabase:
    def __init__(
        self,
        stub_metadata: DBMetadata,
        stub_mangas: list[Manga] | None = None,
    ) -> None:
        self.stub_metadata = stub_metadata
        self.stored_plans: list[SyncPlan] = []
        self.notified_chapters: list[tuple[Chapter, ...]] = []
        self.audit_records: list[ScrapeAuditRecord] = []

        mangas_to_load = stub_mangas if stub_mangas is not None else [DEFAULT_FAKE_MANGA]
        self.mangas: dict[UUID, Manga] = {m.uuid: m for m in mangas_to_load}

    def get_metadata(self, manga_id: UUID) -> DBMetadata:
        del manga_id
        return self.stub_metadata

    def store_chapters(self, manga: Manga, plan: SyncPlan) -> None:
        del manga
        self.stored_plans.append(plan)

    def mark_as_notified(self, chapters: tuple[Chapter, ...]) -> None:
        self.notified_chapters.append(chapters)

    def get_active_manga_ids(self) -> tuple[UUID, ...]:
        return tuple(self.mangas.keys())

    def get_manga(self, manga_id: UUID) -> Manga:
        if manga_id not in self.mangas:
            raise ValueError(f"DatabaseError mock: Manga {manga_id} not found")
        return self.mangas[manga_id]

    def save_audit_record(self, run_context: RunContext, record: ScrapeAuditRecord) -> None:
        del run_context
        self.audit_records.append(record)


class FailingDatabaseStub:
    def __init__(self, exception_to_throw: Exception):
        self.error = exception_to_throw
        self.audit_records: list[ScrapeAuditRecord] = []

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

    def get_active_manga_ids(self) -> tuple[UUID, ...]:
        raise self.error

    def get_manga(self, manga_id: UUID) -> Manga:
        del manga_id
        raise self.error

    def save_audit_record(self, run_context: RunContext, record: ScrapeAuditRecord) -> None:
        del run_context
        self.audit_records.append(record)
        pass
