import os
from collections.abc import Generator
from pathlib import Path

import psycopg
import pytest
from testcontainers.postgres import PostgresContainer

from src.infrastructure.database.connection import get_db_connection


@pytest.fixture(scope="module")
def postgres_container() -> Generator[PostgresContainer, None, None]:
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres


@pytest.fixture(scope="module")
def init_database(postgres_container: PostgresContainer) -> None:
    raw_url = postgres_container.get_connection_url()
    db_url = raw_url.replace("+psycopg2", "")

    schema_path = (
        Path(__file__).parent.parent.parent / "src" / "infrastructure" / "database" / "schema.sql"
    )

    with open(schema_path, encoding="utf-8") as f:
        schema_sql = f.read()

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(schema_sql)  # type: ignore[arg-type]
        conn.commit()


@pytest.fixture(scope="function")
def db_connection(
    postgres_container: PostgresContainer, init_database: None
) -> Generator[psycopg.Connection, None, None]:
    del init_database
    raw_url = postgres_container.get_connection_url()
    db_url = raw_url.replace("+psycopg2", "")

    with get_db_connection(db_url) as conn:
        yield conn

        with conn.cursor() as cursor:
            cursor.execute(
                "TRUNCATE TABLE chapters, mangas, tracked_mangas RESTART IDENTITY CASCADE;"
            )


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    args = {**browser_type_launch_args}

    chromium_path = os.environ.get("CHROMIUM_EXECUTABLE_PATH")
    if chromium_path:
        args["executable_path"] = chromium_path

    return args
