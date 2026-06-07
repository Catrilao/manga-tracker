from decimal import Decimal

import psycopg
import pytest

from src.domain.models import Chapter, ChapterIdentifier, DatabaseError, DBMetadata, Manga, SyncPlan
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
