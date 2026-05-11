from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
import requests

from src.domain.models import Chapter, RunContext
from src.infrastructure.notifications.discord import DiscordNotifier


class DummyResponse:
    def __init__(
        self,
        *,
        ok: bool,
        status_code: int,
        text: str = "",
        json_data: dict | None = None,
        headers: dict | None = None,
    ) -> None:
        self.ok = ok
        self.status_code = status_code
        self.text = text
        self._json_data = json_data or {}
        self.headers = headers or {}

    def json(self) -> dict:
        return self._json_data


@pytest.fixture
def notifier() -> DiscordNotifier:
    return DiscordNotifier("https://discord.test/webhook")


@pytest.fixture
def chapter() -> Chapter:
    return Chapter(
        manga_id=uuid4(),
        number=Decimal("12.0"),
        name="A New Dawn",
        link="https://mangadex.org/chapter/abc",
        language="English",
    )


def test_build_chapter_payload(notifier: DiscordNotifier, chapter: Chapter) -> None:
    payload = notifier.build_chapter_payload(chapter, "Dai Dark", "https://img.test/cover.jpg")

    embed = payload["embeds"][0]
    assert embed["title"] == "Dai Dark - Chapter 12 - A New Dawn"
    assert embed["url"] == chapter.link
    assert embed["thumbnail"]["url"] == "https://img.test/cover.jpg"
    assert embed["fields"][0]["value"] == "English"


def test_build_error_payload_local_run() -> None:
    notifier = DiscordNotifier("https://discord.test/webhook")
    payload = notifier.build_error_payload("boom", 0xFF0000, None)

    embed = payload["embeds"][0]
    assert "View GitHub Actions Logs" not in embed["description"]
    assert embed["footer"]["text"] == "MangaDex Notifier"


def test_build_error_payload_github_run(
    monkeypatch: pytest.MonkeyPatch, notifier: DiscordNotifier
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "Catrilao/manga-tracker")
    run_context = cast(RunContext, SimpleNamespace(gh_run_id="123456", git_commit="abcdef123456"))

    payload = notifier.build_error_payload("boom", 0xFF0000, run_context)
    embed = payload["embeds"][0]

    assert "View GitHub Actions Logs" in embed["description"]
    assert "actions/runs/123456" in embed["description"]
    assert "Commit abcdef1" in embed["footer"]["text"]


def test_post_with_retry_success_first_try(
    monkeypatch: pytest.MonkeyPatch, notifier: DiscordNotifier
) -> None:
    resp = DummyResponse(ok=True, status_code=204)
    monkeypatch.setattr(
        "src.infrastructure.notifications.discord.requests.post", lambda *a, **k: resp
    )

    result = notifier.post_with_retry({"x": 1})
    assert result is resp


def test_post_with_retry_rate_limit_then_success(
    monkeypatch: pytest.MonkeyPatch, notifier: DiscordNotifier
) -> None:
    responses = [
        DummyResponse(ok=False, status_code=429, json_data={"retry_after": 0}),
        DummyResponse(ok=True, status_code=204),
    ]

    def fake_post(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr("src.infrastructure.notifications.discord.requests.post", fake_post)
    monkeypatch.setattr("src.infrastructure.notifications.discord.time.sleep", lambda *_: None)

    result = notifier.post_with_retry({"x": 1}, max_retries=3)
    assert result is not None
    assert result.ok is True


def test_post_with_retry_server_error_returns_last_response(
    monkeypatch: pytest.MonkeyPatch, notifier: DiscordNotifier
) -> None:
    resp_500 = DummyResponse(ok=False, status_code=500, text="err")
    calls = {"n": 0}

    def fake_post(*args, **kwargs):
        calls["n"] += 1
        return resp_500

    monkeypatch.setattr("src.infrastructure.notifications.discord.requests.post", fake_post)
    monkeypatch.setattr("src.infrastructure.notifications.discord.time.sleep", lambda *_: None)
    monkeypatch.setattr("src.infrastructure.notifications.discord.random.uniform", lambda *_: 0)

    result = notifier.post_with_retry({"x": 1}, max_retries=3)
    assert calls["n"] == 3
    assert result is resp_500


def test_post_with_retry_client_error_no_retry(
    monkeypatch: pytest.MonkeyPatch, notifier: DiscordNotifier
) -> None:
    resp_400 = DummyResponse(ok=False, status_code=400, text="bad request")
    calls = {"n": 0}

    def fake_post(*args, **kwargs):
        calls["n"] += 1
        return resp_400

    monkeypatch.setattr("src.infrastructure.notifications.discord.requests.post", fake_post)

    result = notifier.post_with_retry({"x": 1}, max_retries=3)
    assert calls["n"] == 1
    assert result is resp_400


def test_post_with_retry_network_error_then_none(
    monkeypatch: pytest.MonkeyPatch, notifier: DiscordNotifier
) -> None:
    calls = {"n": 0}

    def fake_post(*args, **kwargs):
        calls["n"] += 1
        raise requests.RequestException("network down")

    monkeypatch.setattr("src.infrastructure.notifications.discord.requests.post", fake_post)
    monkeypatch.setattr("src.infrastructure.notifications.discord.time.sleep", lambda *_: None)
    monkeypatch.setattr("src.infrastructure.notifications.discord.random.uniform", lambda *_: 0)

    result = notifier.post_with_retry({"x": 1}, max_retries=2)
    assert calls["n"] == 2
    assert result is None


def test_send_notification_success(
    monkeypatch: pytest.MonkeyPatch, notifier: DiscordNotifier, chapter: Chapter
) -> None:
    monkeypatch.setattr(
        notifier,
        "post_with_retry",
        lambda payload: DummyResponse(ok=True, status_code=204),
    )

    assert notifier.send_notification("Dai Dark", "https://img.test/cover.jpg", chapter) is True


def test_send_notification_failure(
    monkeypatch: pytest.MonkeyPatch, notifier: DiscordNotifier, chapter: Chapter
) -> None:
    monkeypatch.setattr(
        notifier,
        "post_with_retry",
        lambda payload: DummyResponse(ok=False, status_code=500, text="oops"),
    )

    assert notifier.send_notification("Dai Dark", "https://img.test/cover.jpg", chapter) is False
