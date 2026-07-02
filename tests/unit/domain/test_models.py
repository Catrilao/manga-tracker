from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from src.domain.models import AuditStatus, ScrapeAuditRecord


def test_audit_record_calculates_failures_on_finish():
    record = ScrapeAuditRecord(manga_id=UUID(int=1))

    record.started_at = datetime.now(UTC) - timedelta(seconds=2)
    record.chapters_found = 10
    record.chapters_skipped = 2

    record.mark_finished(AuditStatus.SUCCESS)
    record.mark_notified()

    assert record.status == "success"
    assert record.duration_ms == pytest.approx(2000, abs=50)
    assert record.null_chapter_pct == 20.0
    assert record.notified_at is not None


def test_audit_record_truncates_massive_skipped_details():
    record = ScrapeAuditRecord(UUID(int=1))

    record.metadata["skipped_details"] = ["Error"] * 100
    record.mark_finished(AuditStatus.STARTED, max_skipped_details=50)

    assert len(record.metadata["skipped_details"]) == 50
    assert record.metadata["skipped_details_truncated"] is True
    assert record.metadata["skipped_details_total_count"] == 100


def test_audit_record_register_skipped_details():
    record = ScrapeAuditRecord(UUID(int=1))

    record.metadata["skipped_details"] = ["Error"]
    record.mark_finished(AuditStatus.SUCCESS)

    assert len(record.metadata["skipped_details"]) == 1
    assert "skipped_details_truncated" not in record.metadata
    assert "skipped_details_total_count" not in record.metadata


def test_audit_record_post_init_preserves_existing_metadata():
    existing_meta = {
        "source_errors": {"mock_provider": "error"},
        "log_events": [{"event": "mock"}],
    }

    record = ScrapeAuditRecord(manga_id=UUID(int=1), metadata=existing_meta)

    assert record.metadata["source_errors"] == {"mock_provider": "error"}
    assert record.metadata["log_events"] == [{"event": "mock"}]


def test_audit_record_scraper_failure_preserves_existing_error_class():
    record = ScrapeAuditRecord(manga_id=UUID(int=1), error_class="CriticalCrash")

    record.record_scraper_failure("mangadex", "timeout", 408)

    assert record.metadata["source_errors"]["mangadex"]["error"] == "timeout"
    assert record.metadata["source_errors"]["mangadex"]["status_code"] == 408
    assert record.error_class == "CriticalCrash"


def test_audit_record_mark_finished_partial_failure():
    record = ScrapeAuditRecord(UUID(int=1))

    record.record_scraper_failure("mangadex", "timeout")
    record.mark_finished(AuditStatus.SUCCESS)

    assert record.error_class == "PartialFailure"
