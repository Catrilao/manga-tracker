from dataclasses import asdict
from uuid import UUID

from psycopg import Connection

from src.domain.models import Chapter, DatabaseError, DBMetadata, Manga, SyncPlan


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

                cursor.execute(
                    """
                    SELECT manga_id, number, language FROM chapters WHERE manga_id = %s
                    """,
                    (manga_id,),
                )
                existing_identifiers = frozenset(cursor.fetchall())
        except Exception as e:
            raise DatabaseError(f"Failed to fetch metadata: {str(e)}")

        return DBMetadata(
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
        except Exception as e:
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
        except Exception as e:
            raise DatabaseError(f"Failed to mark chapters as notified: {str(e)}")
