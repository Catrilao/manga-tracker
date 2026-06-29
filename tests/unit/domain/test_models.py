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
