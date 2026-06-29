from unittest.mock import MagicMock

import psycopg

from src.infrastructure.database.connection import get_db_connection


def test_get_db_connection_handles_close_error(monkeypatch):
    mock_conn = MagicMock()
    mock_conn.closed = False
    mock_conn.close.side_effect = psycopg.Error("malo")

    monkeypatch.setattr("psycopg.connect", lambda *args, **kwargs: mock_conn)

    with get_db_connection("dummy_url") as conn:
        assert conn is not None

    mock_conn.close.assert_called_once()


def test_get_db_connection_does_not_close_already_closed_connection(monkeypatch):
    mock_conn = MagicMock()
    mock_conn.closed = True
    mock_conn.close.side_effect = psycopg.Error("malo")

    monkeypatch.setattr("psycopg.connect", lambda *args, **kwargs: mock_conn)

    with get_db_connection("dummy_url") as conn:
        assert conn is not None

    mock_conn.close.assert_not_called()
