import os
import sys
from unittest.mock import AsyncMock, patch
from uuid import UUID

import psycopg
import pytest
import pytest_asyncio
from playwright.async_api import async_playwright

from src.main import main


@pytest.fixture(autouse=True)
def clear_module_cache(monkeypatch):
    monkeypatch.delitem(sys.modules, "src.config", raising=False)
    monkeypatch.setattr("src.main.configure_logging", lambda: None)


@pytest_asyncio.fixture
async def async_browser_context():
    async with async_playwright() as p:
        chromium_path = os.environ.get("CHROMIUM_EXECUTABLE_PATH")
        browser = await p.chromium.launch(executable_path=chromium_path)
        context = await browser.new_context()

        yield context

        await context.close()
        await browser.close()


class TestMainCompositionRootSmoke:
    def test_main_happy_path_with_empty_database(
        self,
        postgres_container,
        init_database,
        monkeypatch,
        capsys,
    ):
        del init_database

        db_url = postgres_container.get_connection_url().replace("+psycopg2", "")

        with psycopg.connect(db_url, autocommit=True) as conn:
            conn.execute("TRUNCATE TABLE manga_sources CASCADE;")

        monkeypatch.setenv("DATABASE_URL", db_url)
        monkeypatch.setenv("DISCORD_WEBHOOK", "http://127.0.0.1:54321/mock-webhook")
        monkeypatch.setenv("CHROMIUM_EXECUTABLE_PATH", "mock")
        monkeypatch.setenv("TRACKER_ENV", "test")

        with patch("src.main.async_playwright"):
            mock_context_manager = AsyncMock()
            mock_p = AsyncMock()
            mock_context_manager.__aenter__.return_value = mock_p

            mock_browser = AsyncMock()
            mock_p.chromium.launch.return_value = mock_browser
            mock_browser.new_context.return_value = AsyncMock()

            with pytest.raises(SystemExit) as exec_info:
                main()

        captured = capsys.readouterr()
        output = captured.out + captured.err

        assert exec_info.value.code == 0, (
            f"Expected exit code 0 on successful run, got {exec_info.value.code}. Output:\n{output}"
        )

        assert "tracker_booting" in output
        assert "postgres_connection_established" in output
        assert "no_active_mangas_found_in_database" in output

    def test_main_exits_with_error_on_configuration_failure(self, monkeypatch, capsys):
        monkeypatch.setenv("DATABASE_URL", "")
        monkeypatch.setenv("DISCORD_WEBHOOK", "")
        monkeypatch.setenv("CHROMIUM_EXECUTABLE_PATH", "")
        monkeypatch.setenv("TRACKER_ENV", "invalid_path")

        with pytest.raises(SystemExit) as exec_info:
            main()

        captured = capsys.readouterr()
        output = captured.out + captured.err

        assert exec_info.value.code == 1, (
            f"Expected return code to be 1, got: {exec_info.value.code}"
        )

        output = captured.out + captured.err
        assert "configuration_failed" in output
        assert "tracker_booting" in output

    def test_main_exits_with_error_on_infrastructure_initialization_failure(
        self, monkeypatch, capsys
    ):

        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql://usuario_fantasma:password_falso@localhost:9999/db_inexistente",
        )
        monkeypatch.setenv("DISCORD_WEBHOOK", "http://127.0.0.1:54321/mock-webhook")
        monkeypatch.setenv("CHROMIUM_EXECUTABLE_PATH", "/dev/null/non-existent-path")
        monkeypatch.setenv("TRACKER_ENV", "test")

        with pytest.raises(SystemExit) as exec_info:
            main()

        captured = capsys.readouterr()
        output = captured.out + captured.err

        assert exec_info.value.code == 1, (
            f"Expected return code to be 1, got: {exec_info.value.code}"
        )

        assert "infrastructure_initialization_failed" in output
        assert "discord_error_notification" in output


class TestMainCompositionRootOperationalEdgeCases:
    def test_main_handles_database_loss_during_active_batch_execution(
        self, postgres_container, init_database, monkeypatch, capsys
    ):
        del init_database

        db_url = postgres_container.get_connection_url().replace("+psycopg2", "")
        dummy_id = UUID(int=9)

        import psycopg

        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO mangas (id, name, thumbnail, is_active)
                    VALUES(%s, 'Bad Manga', 'https://thumnail.fake/image.png', TRUE)
                    ON CONFLICT DO NOTHING;
                    """,
                    (dummy_id,),
                )
            conn.commit()

        monkeypatch.setenv("DATABASE_URL", db_url)
        monkeypatch.setenv("DISCORD_WEBHOOK", "http://127.0.0.1:54321/mock-webhook")
        monkeypatch.setenv("CHROMIUM_EXECUTABLE_PATH", "mock")
        monkeypatch.setenv("TRACKER_ENV", "test")

        with pytest.raises(SystemExit) as exec_info:
            main()

        captured = capsys.readouterr()
        output = captured.out + captured.err

        assert "postgres_connection_established" in output
        assert exec_info.value.code == 1, (
            f"Expected runtime errors to yield exit code 1, got {exec_info.value.code}"
        )
