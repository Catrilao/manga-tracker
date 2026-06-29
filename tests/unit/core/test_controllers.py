from dataclasses import dataclass
from typing import Any
from unittest.mock import sentinel
from uuid import UUID

import pytest
from structlog.testing import capture_logs

from src.core.controllers import MangaBatchController
from src.domain.models import Manga
from tests.doubles.database import FakeDatabase
from tests.doubles.service import FakeSyncService

MANGA_1 = Manga(uuid=UUID(int=1), name="Manga 1", thumbnail="", sources=[])
MANGA_2 = Manga(uuid=UUID(int=2), name="Manga 2", thumbnail="", sources=[])


@dataclass(frozen=True)
class BatchExecutionCase:
    stub_mangas: list[Manga]
    service_results: list[bool]
    expected_exit: int
    expected_success: int
    expected_failure: int
    expected_log_msg: str
    expected_log_level: str
    expected_log_kwargs: dict[str, Any]


SCENARIOS = [
    pytest.param(
        BatchExecutionCase(
            stub_mangas=[],
            service_results=[],
            expected_exit=0,
            expected_success=0,
            expected_failure=0,
            expected_log_msg="no_active_mangas_found_in_database",
            expected_log_level="warning",
            expected_log_kwargs={},
        ),
        id="no_urls_found",
    ),
    pytest.param(
        BatchExecutionCase(
            stub_mangas=[MANGA_1, MANGA_2],
            service_results=[True, True],
            expected_exit=0,
            expected_success=2,
            expected_failure=0,
            expected_log_msg="run_completed_successfully",
            expected_log_level="info",
            expected_log_kwargs={},
        ),
        id="complete_success",
    ),
    pytest.param(
        BatchExecutionCase(
            stub_mangas=[MANGA_1, MANGA_2],
            service_results=[False, True],
            expected_exit=1,
            expected_success=1,
            expected_failure=1,
            expected_log_msg="run_completed_with_failures",
            expected_log_level="warning",
            expected_log_kwargs={"attempted": 2, "succeeded": 1},
        ),
        id="partial_failure",
    ),
    pytest.param(
        BatchExecutionCase(
            stub_mangas=[MANGA_1, MANGA_2],
            service_results=[False, False],
            expected_exit=1,
            expected_success=0,
            expected_failure=2,
            expected_log_msg="run_failed_completely",
            expected_log_level="critical",
            expected_log_kwargs={"attempted": 2},
        ),
        id="complete_failure",
    ),
]


@pytest.mark.parametrize("case", SCENARIOS)
async def test_manga_batch_controller_scenarios(
    case: BatchExecutionCase,
    run_context,
):
    db_stub = FakeDatabase(stub_metadata=sentinel.METADATA, stub_mangas=case.stub_mangas)
    service_stub = FakeSyncService(case.service_results)
    controller = MangaBatchController(db_repo=db_stub, sync_service=service_stub)

    with capture_logs() as cap_logs:
        exit_code = await controller.run_all(run_context)

    assert exit_code == case.expected_exit
    assert service_stub.calls_made == len(case.stub_mangas)
    assert service_stub.succeeded_calls == case.expected_success
    assert service_stub.failed_calls == case.expected_failure

    assert len(cap_logs) == 1, f"Expected exactly 1 log, got: {len(cap_logs)}"

    target_log = cap_logs[0]
    assert target_log["event"] == case.expected_log_msg
    assert target_log["log_level"] == case.expected_log_level
    assert case.expected_log_kwargs.items() <= target_log.items(), (
        "Missed or mismatched kwargs. "
        f"Expected subset: {case.expected_log_kwargs} ."
        f"Actual log: {target_log}"
    )
