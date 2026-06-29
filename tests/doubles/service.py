from collections.abc import Iterator
from uuid import UUID

from src.domain.models import RunContext


class FakeSyncService:
    """
    Simulate the service's answers without executing its real logic
    """

    execution_results: Iterator[bool]
    calls_made: int

    def __init__(self, execution_results: list[bool]) -> None:
        self.execution_results = iter(execution_results)
        self.calls_made = 0
        self.succeeded_calls = 0
        self.failed_calls = 0

    async def execute(self, manga_id: UUID, run_context: RunContext) -> bool:
        del manga_id
        del run_context
        self.calls_made += 1

        current_result = next(self.execution_results)
        if current_result:
            self.succeeded_calls += 1
        else:
            self.failed_calls += 1

        return current_result
