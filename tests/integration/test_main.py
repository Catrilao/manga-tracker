import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def main_path():
    return Path(__file__).parent.parent.parent / "src" / "main.py"


class TestMainCompositionRootSmoke:
    def test_main_happy_path_with_empty_database(
        self, main_path, postgres_container, init_database
    ):
        del init_database

        env_simulated = os.environ.copy()

        env_simulated["DATABASE_URL"] = postgres_container.get_connection_url().replace(
            "+psycopg2", ""
        )
        env_simulated["DISCORD_WEBHOOK_URL"] = "http://127.0.0.1:54321/mock-webhook"
        env_simulated["CHROMIUM_EXECUTABLE_PATH"] = "mock"
        env_simulated["TRACKER_ENV"] = "test"

        result = subprocess.run(
            [sys.executable, str(main_path)],
            env=env_simulated,
            capture_output=True,
            text=True,
        )

        output = result.stdout + result.stderr

        assert result.returncode == 0, (
            f"Expected exit code 0 on successful run, got {result.returncode}. Output:\n{output}"
        )

        assert "tracker_booting" in output
        assert "postgres_connection_established" in output
        assert "no_urls_found_in_database" in output

    def test_main_exits_with_error_on_configuration_failure(self, main_path):
        env_simulated = os.environ.copy()

        env_simulated["DATABASE_URL"] = ""
        env_simulated["DISCORD_WEBHOOK_URL"] = ""
        env_simulated["CHROMIUM_EXECUTABLE_PATH"] = ""
        env_simulated["TRACKER_ENV"] = "invalid_path"

        result = subprocess.run(
            [sys.executable, str(main_path)],
            env=env_simulated,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1, f"Expected return code to be 1, got: {result.returncode}"

        output = result.stdout + result.stderr
        assert "configuration_failed" in output
        assert "tracker_booting" in output

    def test_main_exits_with_error_on_infrastructure_initialization_failure(self, main_path):
        env_simulated = os.environ.copy()

        env_simulated["DATABASE_URL"] = (
            "postgresql://usuario_fantasma:password_falso@localhost:9999/db_inexistente"
        )
        env_simulated["DISCORD_WEBHOOK_URL"] = "http://127.0.0.1:54321/mock-webhook"
        env_simulated["CHROMIUM_EXECUTABLE_PATH"] = "/dev/null/non-existent-path"
        env_simulated["TRACKER_ENV"] = "test"

        result = subprocess.run(
            [sys.executable, str(main_path)],
            env=env_simulated,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1, f"Expected return code to be 1, got: {result.returncode}"

        output = result.stdout + result.stderr
        assert "infrastructure_initialization_failed" in output
        assert "discord_error_notification" in output


class TestMainCompositionRootOperationalEdgeCases:
    def test_main_handles_database_loss_during_active_batch_execution(
        self, main_path, postgres_container, init_database
    ):
        del init_database

        env_simulated = os.environ.copy()
        db_url = postgres_container.get_connection_url().replace("+psycopg2", "")

        import psycopg

        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO tracked_mangas (url)
                    VALUES('https://mangadex.org/title/corrupted-url-format')
                    ON CONFLICT DO NOTHING;
                    """
                )
            conn.commit()

        env_simulated["DATABASE_URL"] = db_url
        env_simulated["DISCORD_WEBHOOK_URL"] = "http://127.0.0.1:54321/mock-webhook"
        env_simulated["CHROMIUM_EXECUTABLE_PATH"] = "mock"
        env_simulated["TRACKER_ENV"] = "test"

        result = subprocess.run(
            [sys.executable, str(main_path)],
            env=env_simulated,
            capture_output=True,
            text=True,
        )

        output = result.stdout + result.stderr

        assert "postgres_connection_established" in output
        assert result.returncode == 1, (
            f"Expected runtime errors to yield exit code 1, got {result.returncode}"
        )
