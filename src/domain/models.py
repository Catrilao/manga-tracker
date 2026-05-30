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
    SUCCESS = "success"
    ERROR = "error"
    CRITICAL = "critical"


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
    status: str = "started"
    error_class: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def mark_finished(self, status: AuditStatus, max_skipped_details: int = 50) -> None:
        self.status = status.value
        self.finished_at = datetime.now(UTC)
        self.duration_ms = int((self.finished_at - self.started_at).total_seconds() * 1000)

        if self.status == AuditStatus.SUCCESS and self.chapters_found > 0:
            self.metadata["null_chapter_pct"] = round(
                (self.chapters_skipped / self.chapters_found) * 100, 2
            )
        else:
            self.metadata["null_chapter_pct"] = None

        if "skipped_details" in self.metadata:
            details = self.metadata["skipped_details"]
            total_skipped = len(details)

            if total_skipped > max_skipped_details:
                self.metadata["skipped_details"] = details[:max_skipped_details]
                self.metadata["skipped_details_truncated"] = True
                self.metadata["skipped_details_total_count"] = total_skipped


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

    def __init__(self, message: str, severity: Severity) -> None:
        super().__init__(message)
        self.severity = severity

    @property
    def color_code(self) -> int:
        return self.severity.value


class ConfigurationError(TrackerBaseException):
    def __init__(
        self,
        message: str = "Initial configuration error",
        severity: Severity = Severity.CRITICAL,
    ) -> None:
        super().__init__(message, severity)


class DatabaseError(TrackerBaseException):
    def __init__(
        self,
        message: str = "Database fetch/logic error",
        severity: Severity = Severity.CRITICAL,
    ) -> None:
        super().__init__(message, severity)


class ScraperBaseException(TrackerBaseException):
    """Base category for all errors that occur during the extraction phase."""

    def __init__(
        self,
        message: str,
        severity: Severity = Severity.ERROR,
    ) -> None:
        super().__init__(message, severity)


class DOMChangeError(ScraperBaseException):
    def __init__(self, message: str = "Possible DOM change") -> None:
        super().__init__(message, Severity.ERROR)


class ParseError(ScraperBaseException):
    def __init__(self, message: str = "Data parsing error") -> None:
        super().__init__(message, Severity.ERROR)


class NetworkError(ScraperBaseException):
    def __init__(self, message: str = "Network error") -> None:
        super().__init__(message, Severity.ERROR)
