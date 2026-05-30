from dataclasses import dataclass

import pytest

from src.domain.models import (
    DatabaseError,
    DOMChangeError,
    NetworkError,
    ParseError,
    Severity,
)


def test_sync_service_skips_notifications_on_cold_start(sync_scenario):
    (
        sync_scenario.scraper_returns_chapters("1", "2")
        .execute()
        .assert_success()
        .assert_no_notifications()
        .assert_plans_stored(1)
        .assert_logging("manga_sync_completed", "info", new_chapters=2)
    )


def test_sync_service_send_notifications_when_not_cold_start(sync_scenario):
    (
        sync_scenario.existing_series_with_chapters("1", "2")
        .scraper_returns_chapters("3", "4")
        .execute()
        .assert_success()
        .assert_plans_stored(1)
        .assert_notified_about("3", "4")
        .assert_marked_as_notified("3", "4")
        .assert_logging("manga_sync_completed", "info", new_chapters=2)
    )


def test_sync_service_does_not_notify_if_no_new_chapters(sync_scenario):
    (
        sync_scenario.existing_series_with_chapters("1", "2")
        .scraper_returns_chapters("1", "2")
        .execute()
        .assert_success()
        .assert_plans_stored(0)
        .assert_no_notifications()
        .assert_logging("manga_sync_completed", "info", new_chapters=0)
    )


def test_sync_service_handles_partial_notifications_failure(sync_scenario):
    (
        sync_scenario.existing_series_with_chapters("1", "2")
        .scraper_returns_chapters("3", "4")
        .notification_fails_for("3")
        .execute()
        .assert_success()
        .assert_plans_stored(1)
        .assert_notified_about("4")
        .assert_marked_as_notified("4")
        .assert_not_marked_as_notified("3")
        .assert_logging("manga_sync_completed", "info", new_chapters=2)
    )


def test_sync_service_notifies_database_error(sync_scenario):
    (
        sync_scenario.database_fails_with(DatabaseError())
        .execute()
        .assert_success(False)
        .assert_error_notified("Database fetch/logic error", Severity.CRITICAL.value)
        .assert_logging("manga_sync_failed", "error", error_class="DatabaseError")
    )


@dataclass(frozen=True)
class SyncErrorCase:
    simulated_error: Exception
    expected_message: str
    expected_color: int
    expected_event: str
    expected_level: str


FAILURE_SCRAPER_SYNC_SCENARIOS = [
    pytest.param(
        SyncErrorCase(
            simulated_error=DOMChangeError("CSS selector '.chapter' missing"),
            expected_message="CSS selector '.chapter' missing",
            expected_color=Severity.ERROR.value,
            expected_event="manga_sync_failed",
            expected_level="error",
        ),
        id="dom_change_error",
    ),
    pytest.param(
        SyncErrorCase(
            simulated_error=NetworkError("Timeout from Playwright"),
            expected_message="Timeout from Playwright",
            expected_color=Severity.ERROR.value,
            expected_event="manga_sync_failed",
            expected_level="error",
        ),
        id="network_timeout",
    ),
    pytest.param(
        SyncErrorCase(
            simulated_error=Exception("Postgres Out Of Memory"),
            expected_message="Critical crash: Postgres Out Of Memory",
            expected_color=Severity.CRITICAL.value,
            expected_event="manga_sync_crashed",
            expected_level="critical",
        ),
        id="database_error",
    ),
]


@pytest.mark.parametrize(
    "case",
    FAILURE_SCRAPER_SYNC_SCENARIOS,
)
def test_sync_service_captures_and_notifies_scraper_errors(case: SyncErrorCase, sync_scenario):
    (
        sync_scenario.scraper_fails_with(case.simulated_error)
        .execute()
        .assert_success(False)
        .assert_error_notified(case.expected_message, case.expected_color)
        .assert_no_side_effects()
        .assert_logging(
            case.expected_event,
            case.expected_level,
            error_class=case.simulated_error.__class__.__name__,
        )
    )


PARSER_FAILURE_SYNC_SCENARIOS = [
    pytest.param(
        SyncErrorCase(
            simulated_error=ParseError("Missing 'language' attribute in RawChapter"),
            expected_message="Missing 'language' attribute in RawChapter",
            expected_color=Severity.ERROR.value,
            expected_event="manga_sync_failed",
            expected_level="error",
        ),
        id="parse_error",
    ),
    pytest.param(
        SyncErrorCase(
            simulated_error=ValueError("Invalid decimal format for chapter number"),
            expected_message="Critical crash: Invalid decimal format for chapter number",
            expected_color=Severity.CRITICAL.value,
            expected_event="manga_sync_crashed",
            expected_level="critical",
        ),
        id="value_error",
    ),
]


@pytest.mark.parametrize(
    "case",
    PARSER_FAILURE_SYNC_SCENARIOS,
)
def test_sync_service_captures_parser_errors(case: SyncErrorCase, sync_scenario):
    (
        sync_scenario.parser_fails_with(case.simulated_error)
        .execute()
        .assert_success(False)
        .assert_error_notified(case.expected_message, case.expected_color)
        .assert_no_side_effects()
        .assert_logging(
            case.expected_event,
            case.expected_level,
            error_class=case.simulated_error.__class__.__name__,
        )
    )
