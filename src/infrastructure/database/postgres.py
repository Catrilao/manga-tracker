import json
from dataclasses import asdict
from uuid import UUID

import psycopg
from psycopg import Connection
from psycopg.rows import class_row

from src.domain.models import (
    Chapter,
    ChapterIdentifier,
    DatabaseError,
    DBMetadata,
    Manga,
    RunContext,
    ScrapeAuditRecord,
    SyncPlan,
)


class PostgresRepository:
    def __init__(self, connection: Connection) -> None:
        self.conn = connection

    def get_metadata(self, manga_id: UUID) -> DBMetadata:
        """
        Fulfills the `GetDBMetadataPort`
        Fetches the current state of the manga to inform the Use Case
        """
        try:
            with self.conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*), MAX(number) FROM chapters WHERE manga_id = %s;
                    """,
                    (manga_id,),
                )
                count, max_number = cursor.fetchone() or (0, None)

            with self.conn.cursor(row_factory=class_row(ChapterIdentifier)) as cursor:
                cursor.execute(
                    """
                    SELECT manga_id, number, language FROM chapters WHERE manga_id = %s
                    """,
                    (manga_id,),
                )
                existing_identifiers = frozenset(cursor)
        except psycopg.Error as e:
            raise DatabaseError(f"Failed to fetch metadata: {str(e)}")

        return DBMetadata(
            manga_id=manga_id,
            is_cold_start=(count == 0),
            chapter_count=count,
            max_chapter_number=max_number,
            existing_chapter_identifiers=existing_identifiers,
        )

    def store_chapters(self, manga: Manga, plan: SyncPlan) -> None:
        """
        Executes the DB writes required by the SyncPlan
        """
        try:
            with self.conn.transaction(), self.conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO mangas
                    (id, name, thumbnail, url)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT(id) DO UPDATE
                    SET name = EXCLUDED.name,
                        thumbnail = EXCLUDED.thumbnail,
                        url = EXCLUDED.url;
                    """,
                    (manga.uuid, manga.name, manga.thumbnail, manga.url),
                )

                if plan.chapters_to_insert:
                    cursor.executemany(
                        """
                        INSERT INTO chapters
                        (manga_id, number, name, language, link)
                        VALUES (%(manga_id)s, %(number)s, %(name)s, %(language)s, %(link)s)
                        ON CONFLICT(manga_id, number, language) DO NOTHING;
                        """,
                        (asdict(c) for c in plan.chapters_to_insert),
                    )
        except psycopg.Error as e:
            raise DatabaseError(f"Failed to execute sync plan writes: {str(e)}")

    def mark_as_notified(self, chapters: tuple[Chapter, ...]) -> None:
        """Updates the notified flag after successful notifications"""
        if not chapters:
            return

        try:
            with self.conn.transaction(), self.conn.cursor() as cursor:
                cursor.executemany(
                    """
                    UPDATE chapters
                    SET notified = TRUE
                    WHERE manga_id = %(manga_id)s
                    AND number = %(number)s
                    AND language = %(language)s;
                    """,
                    (asdict(c) for c in chapters),
                )
        except psycopg.Error as e:
            raise DatabaseError(f"Failed to mark chapters as notified: {str(e)}")

    def get_tracked_urls(self) -> tuple[str, ...]:
        """Retrieves the active manga URLs from the database"""
        with self.conn.cursor() as cursor:
            cursor.execute("SELECT url FROM tracked_mangas WHERE is_active")
            return tuple(row[0] for row in cursor.fetchall())

    def save_audit_record(self, run_context: RunContext, record: ScrapeAuditRecord) -> None:
        query = """
           INSERT INTO scrape_runs (
                run_id, gh_run_id, git_commit,
                finished_at, duration_ms,
                manga_id, manga_name,
                chapters_found, chapters_new, chapters_skipped, null_chapter_pct,
                status, http_status_code, error_class, error_message,
                metadata, notified_at
            ) VALUES (
                %s, %s, %s,
                %s, %s,
                %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s
            ) ON CONFLICT (run_id, manga_id) DO UPDATE SET
                finished_at = EXCLUDED.finished_at,
                duration_ms = EXCLUDED.duration_ms,
                chapters_found = EXCLUDED.chapters_found,
                chapters_new = EXCLUDED.chapters_new,
                chapters_skipped = EXCLUDED.chapters_skipped,
                null_chapter_pct = EXCLUDED.null_chapter_pct,
                status = EXCLUDED.status,
                http_status_code = EXCLUDED.http_status_code,
                error_class = EXCLUDED.error_class,
                error_message = EXCLUDED.error_message,
                metadata = EXCLUDED.metadata,
                notified_at = EXCLUDED.notified_at;
        """

        with self.conn.cursor() as cursor:
            cursor.execute(
                query,
                (
                    run_context.run_id,
                    run_context.gh_run_id,
                    run_context.git_commit,
                    record.finished_at,
                    record.duration_ms,
                    record.manga_id,
                    record.manga_name,
                    record.chapters_found,
                    record.chapters_new,
                    record.chapters_skipped,
                    record.null_chapter_pct,
                    record.status,
                    record.http_status_code,
                    record.error_class,
                    record.error_message,
                    json.dumps(record.metadata),
                    record.notified_at,
                ),
            )

        self.conn.commit()
