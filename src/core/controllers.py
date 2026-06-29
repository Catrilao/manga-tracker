from src.core.ports import DatabasePort, SyncServicePort
from src.domain.models import RunContext
from src.logger import get_logger

log = get_logger(__name__)


class MangaBatchController:
    """
    Controls the batch execution of the manga synchronization process,
    evaluates the global state, and returns exit codes.
    """

    def __init__(self, db_repo: DatabasePort, sync_service: SyncServicePort) -> None:
        self.db_repo = db_repo
        self.sync_service = sync_service

    async def run_all(self, run_context: RunContext) -> int:
        target_ids = self.db_repo.get_active_manga_ids()
        if not target_ids:
            log.warning("no_active_mangas_found_in_database")
            return 0

        mangas_attempted = 0
        mangas_succeeded = 0
        for id in target_ids:
            mangas_attempted += 1
            is_success = await self.sync_service.execute(id, run_context)
            if is_success:
                mangas_succeeded += 1

        if mangas_succeeded == 0 and mangas_attempted > 0:
            log.critical("run_failed_completely", attempted=mangas_attempted)
            return 1
        elif mangas_succeeded < mangas_attempted:
            log.warning(
                "run_completed_with_failures",
                attempted=mangas_attempted,
                succeeded=mangas_succeeded,
            )
            return 1
        else:
            log.info("run_completed_successfully")
            return 0
