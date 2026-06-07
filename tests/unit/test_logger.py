from datetime import UTC, datetime

import pytest
import structlog

from src.domain.models import LogEvent, LogLevel
from src.logger import execute_log_event


@pytest.mark.parametrize(
    "level, expected_method_name",
    [
        (LogLevel.DEBUG, "debug"),
        (LogLevel.INFO, "info"),
        (LogLevel.WARNING, "warning"),
        (LogLevel.ERROR, "error"),
        (LogLevel.CRITICAL, "critical"),
    ],
)
def test_execute_log_event_routes_to_correct_log_level(level, expected_method_name):
    test_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    event = LogEvent(
        level=level,
        event_name="test_event",
        context={"manga_id": "123", "status": "ok"},
        occurred_at=test_time,
    )

    with structlog.testing.capture_logs() as captured_logs:
        execute_log_event(event)

    assert len(captured_logs) == 1

    log_entry = captured_logs[0]
    assert log_entry["log_level"] == expected_method_name
    assert log_entry["event"] == "test_event"
    assert log_entry["manga_id"] == "123"
    assert log_entry["status"] == "ok"
    assert log_entry["occurred_at"] == "2026-01-01T12:00:00+00:00"


def test_execute_log_event_handles_unknown_level():
    test_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    event = LogEvent(
        level="no_importa",  # type: ignore
        event_name="INVALID_LEVEL",
        context={},
        occurred_at=test_time,
    )

    with structlog.testing.capture_logs() as captured_logs:
        execute_log_event(event)

    assert len(captured_logs) == 1
    assert captured_logs[0]["log_level"] == "warning"
    assert captured_logs[0]["event"] == "unknown_log_level"
    assert captured_logs[0]["unknown_event_name"] == "INVALID_LEVEL"
