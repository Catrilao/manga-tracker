from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum, StrEnum, auto
from types import MappingProxyType
from typing import Any
from uuid import UUID

EMPTY_CONTEXT: Mapping[str, Any] = MappingProxyType({})


class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class Severity(Enum):
    WARNING = 0xE67E22
    ERROR = 0xE74C3C
    CRITICAL = 0xC0392B


class AuditStatus(StrEnum):
    STARTED = "started"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"


class ControlSignal(Enum):
    ABORT = auto()
    CONTINUE = auto()


@dataclass(frozen=True)
class RawChapter:
    info_text: str
    header_text: str
    href: str
    language_title: str


@dataclass(frozen=True)
class Manga:
    uuid: UUID
    name: str
    thumbnail: str
    url: str


@dataclass(frozen=True)
class Chapter:
    manga_id: UUID
    number: Decimal
    name: str
    link: str
    language: str


@dataclass
class ScrapeAuditRecord:
    manga_id: UUID
    manga_name: str = "Unknown"
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    duration_ms: int = 0
    chapters_found: int = 0
    chapters_new: int = 0
    chapters_skipped: int = 0
    null_chapter_pct: float | None = None
    status: str = AuditStatus.STARTED.value
    http_status_code: int | None = None
    error_class: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    notified_at: datetime | None = None

    def mark_finished(self, status: AuditStatus, max_skipped_details: int = 50) -> None:
        self.status = status.value
        self.finished_at = datetime.now(UTC)
        self.duration_ms = int((self.finished_at - self.started_at).total_seconds() * 1000)

        if self.status == AuditStatus.SUCCESS and self.chapters_found > 0:
            self.null_chapter_pct = round((self.chapters_skipped / self.chapters_found) * 100, 2)

        if "skipped_details" in self.metadata:
            details = self.metadata["skipped_details"]
            total_skipped = len(details)

            if total_skipped > max_skipped_details:
                self.metadata["skipped_details"] = details[:max_skipped_details]
                self.metadata["skipped_details_truncated"] = True
                self.metadata["skipped_details_total_count"] = total_skipped

    def mark_notified(self) -> None:
        self.notified_at = datetime.now(UTC)


@dataclass(frozen=True)
class RunContext:
    run_id: UUID
    gh_run_id: str
    git_commit: str


@dataclass(frozen=True)
class ChapterIdentifier:
    manga_id: UUID
    number: Decimal
    language: str


@dataclass(frozen=True)
class DBMetadata:
    manga_id: UUID
    is_cold_start: bool
    chapter_count: int
    max_chapter_number: Decimal | None
    existing_chapter_identifiers: frozenset[ChapterIdentifier]


@dataclass(frozen=True)
class LogEvent:
    level: LogLevel
    event_name: str
    context: Mapping[str, Any] = field(default=EMPTY_CONTEXT)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class SyncPlan:
    chapters_to_insert: tuple[Chapter, ...]
    chapters_to_notify: tuple[Chapter, ...]
    log_events: tuple[LogEvent, ...]


class TrackerBaseException(Exception):
    """Base exception for all Manga Tracker domain and infrastructure errors."""

    severity: Severity = Severity.ERROR
    audit_status: AuditStatus = AuditStatus.FAILED

    def __init__(self, message: str) -> None:
        super().__init__(message)

    @property
    def color_code(self) -> int:
        return self.severity.value


class ConfigurationError(TrackerBaseException):
    severity: Severity = Severity.CRITICAL
    audit_status: AuditStatus = AuditStatus.FAILED

    def __init__(
        self,
        message: str = "Initial configuration error",
    ) -> None:
        super().__init__(message)


class DatabaseError(TrackerBaseException):
    severity: Severity = Severity.CRITICAL
    audit_status: AuditStatus = AuditStatus.FAILED

    def __init__(
        self,
        message: str = "Database fetch/logic error",
    ) -> None:
        super().__init__(message)


class ScraperBaseException(TrackerBaseException):
    """Base category for all errors that occur during the extraction phase."""

    severity: Severity = Severity.ERROR
    audit_status: AuditStatus = AuditStatus.FAILED

    def __init__(self, message: str) -> None:
        super().__init__(message)


class DOMChangeError(ScraperBaseException):
    def __init__(self, message: str = "Possible DOM change") -> None:
        super().__init__(message)


class ParseError(ScraperBaseException):
    def __init__(self, message: str = "Data parsing error") -> None:
        super().__init__(message)


class NetworkError(ScraperBaseException):
    audit_status = AuditStatus.TIMEOUT

    def __init__(self, message: str = "Network error") -> None:
        super().__init__(message)
