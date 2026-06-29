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
    db_url = postgres_container.get_connection_url().replace("+psycopg2", "")

    migrations_dir = Path(__file__).parent.parent.parent / "supabase" / "migrations"
    migrations_files = sorted(migrations_dir.glob("*.sql"))

    if not migrations_files:
        raise FileNotFoundError(f"No files founded in {migrations_dir}")

    for migration_path in migrations_files:
        with open(migration_path, encoding="utf-8") as f:
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


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    args = {**browser_type_launch_args}

    chromium_path = os.environ.get("CHROMIUM_EXECUTABLE_PATH")
    if chromium_path:
        args["executable_path"] = chromium_path

    return args
