from collections.abc import Generator
from contextlib import contextmanager

import psycopg

from src.domain.models import DatabaseError
from src.logger import get_logger

log = get_logger(__name__)


@contextmanager
def get_db_connection(database_url: str) -> Generator[psycopg.Connection, None, None]:
    """
    Manages the database connection lifecycle
    """

    log.debug("postgres_connection_attempting")
    connection = None
    try:
        connection = psycopg.connect(database_url)
        connection.autocommit = True
    except psycopg.Error as e:
        log.critical("database_connection_failed", error=str(e))
        raise DatabaseError(f"Could not connect to the database {e}") from e

    try:
        log.info("postgres_connection_established")
        yield connection
    finally:
        if connection and not connection.closed:
            try:
                connection.close()
                log.debug("postgres_connection_closed")
            except psycopg.Error as e:
                log.warning("postgres_connection_close_failed", error=str(e))
