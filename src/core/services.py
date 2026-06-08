from uuid import UUID

from src.core.ports import ChapterParserPort, DatabasePort, FetchMangaPort, NotifierPort
from src.core.use_cases import calculate_sync_plan
from src.domain.models import AuditStatus, RunContext, ScrapeAuditRecord, TrackerBaseException
from src.logger import execute_log_event, get_logger, manga_log_context

log = get_logger()


class MangaSyncService:
    """
    Application service that orchestrates the synchronization of a Manga
    """

    def __init__(
        self,
        db_repo: DatabasePort,
        scraper: FetchMangaPort,
        parser: ChapterParserPort,
        notifier: NotifierPort,
    ) -> None:
        self.db_repo = db_repo
        self.scraper = scraper
        self.parser = parser
        self.notifier = notifier

    def execute(self, url: str, run_context: RunContext) -> bool:
        """
        Coordinates the side-effects and passes the result
        into the functional core
        """
        audit = ScrapeAuditRecord(manga_id=UUID(int=0))

        try:
            manga, raw_chapters = self.scraper(url)
            audit = ScrapeAuditRecord(manga_id=manga.uuid, manga_name=manga.name)
            audit.chapters_found = len(raw_chapters)

            with manga_log_context(manga.uuid, manga.name, manga.url):
                parsed_chapters = self.parser(manga.uuid, raw_chapters)

                db_metadata = self.db_repo.get_metadata(manga.uuid)

                plan = calculate_sync_plan(parsed_chapters, db_metadata)

                for event in plan.log_events:
                    execute_log_event(event)

                audit.chapters_new = len(plan.chapters_to_insert)
                audit.chapters_skipped = len(parsed_chapters) - audit.chapters_new

                if plan.chapters_to_insert:
                    self.db_repo.store_chapters(manga, plan)

                audit.mark_finished(AuditStatus.SUCCESS)

                notified_chapters = []
                for chapter in plan.chapters_to_notify:
                    success = self.notifier.send_notification(manga.name, manga.thumbnail, chapter)
                    if success:
                        notified_chapters.append(chapter)

                if notified_chapters:
                    self.db_repo.mark_as_notified(tuple(notified_chapters))
                    audit.mark_notified()

                log.info("manga_sync_completed", new_chapters=len(plan.chapters_to_insert))

                return True
        except TrackerBaseException as e:
            log.error("manga_sync_failed", error=str(e), error_class=type(e).__name__)

            audit.error_class = type(e).__name__
            audit.error_message = str(e)
            audit.mark_finished(e.audit_status)

            self.notifier.send_error_notification(str(e), e.color_code, run_context)
            audit.mark_notified()

            return False
        except Exception as e:
            log.critical("manga_sync_crashed", error=str(e), error_class=type(e).__name__)

            audit.error_class = type(e).__name__
            audit.error_message = str(e)
            audit.mark_finished(AuditStatus.FAILED)

            self.notifier.send_error_notification(
                f"Critical crash: {str(e)}", 0xC0392B, run_context
            )
            audit.mark_notified()

            return False
        finally:
            try:
                self.db_repo.save_audit_record(run_context, audit)
            except Exception as e:
                log.error("save_audit_failed", error=str(e))
