from collections.abc import Callable
from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest

from src.domain.models import (
    AuditStatus,
    Chapter,
    ChapterIdentifier,
    DatabaseError,
    DBMetadata,
    Manga,
    RunContext,
    ScrapeAuditRecord,
    SyncPlan,
)
from src.infrastructure.database.postgres import PostgresRepository


def test_repository_lifecycle_integration(
    db_connection: psycopg.Connection,
    make_manga,
    make_chapter,
) -> None:
    repository = PostgresRepository(db_connection)

    target_manga: Manga = make_manga(name="One Piece")
    chapter_1: Chapter = make_chapter(
        manga_id=target_manga.uuid, number=Decimal("627"), name="Casa"
    )
    chapter_2: Chapter = make_chapter(
        manga_id=target_manga.uuid, number=Decimal("628"), name="Jurel"
    )

    initial_metadata: DBMetadata = repository.get_metadata(target_manga.uuid)
    assert initial_metadata.is_cold_start is True
    assert initial_metadata.chapter_count == 0
    assert initial_metadata.max_chapter_number is None
    assert len(initial_metadata.existing_chapter_identifiers) == 0

    plan = SyncPlan(
        chapters_to_insert=((chapter_1, chapter_2)),
        chapters_to_notify=((chapter_1, chapter_2)),
        log_events=(),
    )

    repository.store_chapters(target_manga, plan)

    updated_metadata: DBMetadata = repository.get_metadata(target_manga.uuid)
    assert updated_metadata.is_cold_start is False
    assert updated_metadata.chapter_count == 2
    assert updated_metadata.max_chapter_number == Decimal("628")

    expected_identifiers = {
        ChapterIdentifier(target_manga.uuid, chapter_1.number, chapter_1.language),
        ChapterIdentifier(target_manga.uuid, chapter_2.number, chapter_2.language),
    }
    assert updated_metadata.existing_chapter_identifiers == frozenset(expected_identifiers)

    repository.store_chapters(target_manga, plan)

    metadata_after_retry = repository.get_metadata(target_manga.uuid)
    assert metadata_after_retry.chapter_count == 2


def test_mark_as_notified(db_connection: psycopg.Connection, make_manga, make_chapter) -> None:
    """
    Validates that the flag 'notified' is updated on the physical DB
    """

    repository = PostgresRepository(db_connection)

    target_manga: Manga = make_manga()
    chapter: Chapter = make_chapter(manga_id=target_manga.uuid, number=Decimal("232"))

    plan = SyncPlan(chapters_to_insert=(chapter,), chapters_to_notify=(chapter,), log_events=())
    repository.store_chapters(target_manga, plan)

    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT notified FROM chapters WHERE manga_id = %s AND number = %s",
            (target_manga.uuid, Decimal("232")),
        )
        row = cursor.fetchone()
        assert row is not None, "Chapter wasn't inserted"

        notified_status = row[0]
        assert notified_status is False

    repository.mark_as_notified((chapter,))

    with db_connection.cursor() as cursor:
        cursor.execute(
            "SELECT notified FROM chapters WHERE manga_id = %s AND number = %s",
            (target_manga.uuid, Decimal("232")),
        )
        row = cursor.fetchone()
        assert row is not None, "Chapter wasn't inserted"

        notified_status = row[0]
        assert notified_status is True


def test_repository_handles_transaction_rollback(
    db_connection, make_manga, make_chapter, monkeypatch: pytest.MonkeyPatch
):
    def mock_execute(*args, **kwargs):
        del args
        del kwargs
        raise psycopg.OperationalError("Database died, смерть")

    target_manga: Manga = make_manga()
    chapter: Chapter = make_chapter(manga_id=target_manga.uuid, number=Decimal("232"))

    plan = SyncPlan(chapters_to_insert=(chapter,), chapters_to_notify=(chapter,), log_events=())
    respository = PostgresRepository(db_connection)

    monkeypatch.setattr(psycopg.Cursor, "execute", mock_execute)

    with pytest.raises(DatabaseError):
        respository.store_chapters(target_manga, plan)


def test_repository_saves_and_updates_audit_record(db_connection, make_manga):
    repository = PostgresRepository(db_connection)
    target_manga: Manga = make_manga()

    run_context = RunContext(run_id=target_manga.uuid, gh_run_id="local", git_commit="abc123")

    audit = ScrapeAuditRecord(
        manga_id=target_manga.uuid,
        manga_name=target_manga.name,
        chapters_found=10,
    )

    audit.mark_finished(AuditStatus.FAILED)
    repository.save_audit_record(run_context, audit)

    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT status, chapters_found FROM scrape_runs WHERE run_id = %s AND manga_id = %s
            """,
            (run_context.run_id, target_manga.uuid),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "failed"
        assert row[1] == 10

    audit.status = AuditStatus.SUCCESS.value
    audit.chapters_found = 15
    audit.mark_notified()

    repository.save_audit_record(run_context, audit)

    with db_connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT status, chapters_found FROM scrape_runs WHERE run_id = %s AND manga_id = %s
            """,
            (run_context.run_id, target_manga.uuid),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "success"
        assert row[1] == 15


def test_get_manga_updates_sources_correctly(db_connection, make_manga):
    repository = PostgresRepository(db_connection)
    target_manga = make_manga(name="Varias Fuentes")

    with db_connection.transaction(), db_connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO mangas (id, name, thumbnail) VALUES (%s, %s, %s);",
            (target_manga.uuid, target_manga.name, target_manga.thumbnail),
        )
        cursor.execute(
            """
            INSERT INTO manga_sources (manga_id, provider_name, target_url, is_active)
            VALUES
                (%s, 'mangadex', 'https://mangadex.org/', TRUE),
                (%s, 'tmo', 'https://tmo.com/', TRUE);
            """,
            (target_manga.uuid, target_manga.uuid),
        )

    fetched_manga = repository.get_manga(target_manga.uuid)

    assert fetched_manga.uuid == target_manga.uuid
    assert fetched_manga.name == "Varias Fuentes"
    assert len(fetched_manga.sources) == 2

    tmo_source = fetched_manga.sources[0]
    assert tmo_source.provider_name == "mangadex"
    assert tmo_source.target_url == "https://mangadex.org/"
    assert tmo_source.is_active is True

    tmo_source = fetched_manga.sources[1]
    assert tmo_source.provider_name == "tmo"
    assert tmo_source.target_url == "https://tmo.com/"
    assert tmo_source.is_active is True


def test_get_manga_raises_database_error_if_not_found(db_connection):
    repository = PostgresRepository(db_connection)

    with pytest.raises(DatabaseError, match="not found"):
        repository.get_manga(uuid4())


def test_repository_early_returns_and_empty_plans(db_connection, make_manga):
    repository = PostgresRepository(db_connection)
    target_manga = make_manga()

    empty_plan = SyncPlan(chapters_to_insert=(), chapters_to_notify=(), log_events=())
    repository.store_chapters(manga=target_manga, plan=empty_plan)

    repository.mark_as_notified(())


@pytest.mark.parametrize(
    "method_name, get_args, expected_match",
    [
        ("get_metadata", lambda manga, chapter: (manga.uuid,), "Failed to fetch metadata"),
        ("get_manga", lambda manga, chapter: (manga.uuid,), "Failed to fetch manga"),
        (
            "mark_as_notified",
            lambda manga, chapter: ((chapter,),),
            "Failed to mark chapters as notified",
        ),
        ("get_active_manga_ids", lambda manga, chapter: (), "Failed to fetch active manga IDs"),
    ],
    ids=[
        "get_metadata",
        "get_manga",
        "mark_as_notified",
        "get_active_manga_ids",
    ],
)
def test_repository_translates_psycopg_errors_to_domain_errors(
    method_name: str,
    get_args: Callable,
    expected_match: str,
    db_connection,
    make_manga,
    make_chapter,
    monkeypatch: pytest.MonkeyPatch,
):
    repository = PostgresRepository(db_connection)
    target_manga = make_manga()
    chapter = make_chapter()

    def mock_execute(*args, **kwargs):
        raise psycopg.OperationalError("Simulated DB explotion")

    monkeypatch.setattr(psycopg.Cursor, "execute", mock_execute)
    monkeypatch.setattr(psycopg.Cursor, "executemany", mock_execute)

    method_to_call = getattr(repository, method_name)
    args = get_args(target_manga, chapter)

    with pytest.raises(DatabaseError, match=expected_match):
        method_to_call(*args)
