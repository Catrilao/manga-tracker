import logging
import logging.config
import os
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import structlog

from src.domain.models import LogEvent, LogLevel, RunContext

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "scrape.log"


SHARED_PROCESSORS: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
]


def _ensure_log_dir() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def configure_logging() -> None:
    """
    Call once at program startup, after load_dotenv().
    Sets up:
      - structlog with JSON output to logs/scrape.log (Layer 2: Artifact)
      - structlog with console output to stdout       (Layer 1: GH Actions live log)
    """
    _ensure_log_dir()

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processors": [
                        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                        structlog.processors.JSONRenderer(),
                    ],
                    "foreign_pre_chain": SHARED_PROCESSORS,
                },
                "console": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processors": [
                        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                        structlog.dev.ConsoleRenderer(colors=False),
                    ],
                    "foreign_pre_chain": SHARED_PROCESSORS,
                },
            },
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                    "formatter": "console",
                },
                "file": {
                    "class": "logging.FileHandler",
                    "filename": str(LOG_FILE),
                    "mode": "a",
                    "encoding": "utf-8",
                    "formatter": "json",
                },
            },
            "root": {
                "handlers": ["stdout", "file"],
                "level": log_level,
            },
        }
    )

    structlog.configure(
        processors=SHARED_PROCESSORS + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def bind_run_context() -> RunContext:
    """
    Generate and bind run-level context that will appear on every
    subsequent log line automatically. Call once at the start of main().

    Returns the run_id so it can be passed to the DB audit layer later.
    """
    run_id = uuid4()
    gh_run_id = os.getenv("GITHUB_RUN_ID", "local")
    git_commit = os.getenv("GIT_COMMIT", "unknown")

    structlog.contextvars.bind_contextvars(
        run_id=run_id,
        gh_run_id=gh_run_id,
        git_commit=git_commit,
    )

    return RunContext(
        run_id=run_id,
        gh_run_id=gh_run_id,
        git_commit=git_commit,
    )


def manga_log_context(
    manga_id: UUID, manga_name: str, manga_url: str
) -> AbstractContextManager[None]:
    """
    A context manager to safely bind and unbind manga-level logs.

    Usage in main.py:
        with manga_log_context(manga.id, manga.name, manga.url):
            fetch_info_chapter(...)
            store_chapter_data(...)
    """
    return cast(
        AbstractContextManager[None],
        structlog.contextvars.bound_contextvars(
            manga_id=str(manga_id),
            manga_name=manga_name,
            manga_url=manga_url,
        ),
    )


def get_logger(name: str = __name__) -> structlog.stdlib.BoundLogger:
    """
    Import and call this in every module that needs logging.

    Usage:
        from logger import get_logger
        log = get_logger(__name__)
        log.info("chapters_found", count=38)
    """
    return cast(structlog.stdlib.BoundLogger, structlog.get_logger(name))


def execute_log_event(event: LogEvent) -> None:
    log = structlog.get_logger("src.core.use_cases")

    log_kwargs = dict(event.context)
    log_kwargs["occurred_at"] = event.occurred_at.isoformat()

    if event.level == LogLevel.DEBUG:
        log.debug(event.event_name, **log_kwargs)
    elif event.level == LogLevel.INFO:
        log.info(event.event_name, **log_kwargs)
    elif event.level == LogLevel.WARNING:
        log.warning(event.event_name, **log_kwargs)
    elif event.level == LogLevel.ERROR:
        log.error(event.event_name, **log_kwargs)
    elif event.level == LogLevel.CRITICAL:
        log.critical(event.event_name, **log_kwargs)
    else:
        log.warning("unknown_log_level", unknown_event_name=event.event_name, **log_kwargs)


if __name__ == "__main__":
    configure_logging()
    run_id = bind_run_context()
    log = get_logger(__name__)

    log.info("logger_test", status="ok")

    with manga_log_context(UUID(int=1236), "TesT", "http://url.org"):
        log.warning("test_warning", selector=".chapter.relative.read", chapter_found=0)
        log.error("test_error", error_class="DOMChangeError")

    print("\nlogs/scrape.log for JSON output")
