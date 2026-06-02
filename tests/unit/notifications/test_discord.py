from dataclasses import dataclass
from decimal import Decimal

import pytest
import requests
import responses
from structlog.testing import capture_logs

from src.domain.models import Severity
from src.infrastructure.notifications.discord import DiscordNotifier


@pytest.fixture
def notifier():
    return DiscordNotifier(webhook_url="https://discord.test/api/active-webhook-token")


@pytest.fixture(autouse=True)
def speed_up_retries(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _: None)
    monkeypatch.setattr("random.uniform", lambda *_: 0.0)


@dataclass(frozen=True)
class HttpScenarioCase:
    response_setup: list[dict]
    expected_result: bool
    expected_calls: int
    expected_log: str


HTTP_MATRIX_SCENARIOS = [
    pytest.param(
        HttpScenarioCase(
            response_setup=[{"status": 204, "body": ""}],
            expected_result=True,
            expected_calls=1,
            expected_log="discord_notification_sent",
        ),
        id="happy_path_success",
    ),
    pytest.param(
        HttpScenarioCase(
            response_setup=[{"status": 400, "json": {"message": "Bad Request"}}],
            expected_result=False,
            expected_calls=1,
            expected_log="discord_notification_failed",
        ),
        id="client_error_no_retry",
    ),
    pytest.param(
        HttpScenarioCase(
            response_setup=[
                {"status": 503, "body": ""},
                {"status": 502, "body": ""},
                {"status": 204, "body": ""},
            ],
            expected_result=True,
            expected_calls=3,
            expected_log="discord_notification_sent",
        ),
        id="server_error_recovery_on_retry",
    ),
    pytest.param(
        HttpScenarioCase(
            response_setup=[
                {"status": 500, "body": ""},
                {"status": 500, "body": ""},
                {"status": 500, "body": ""},
            ],
            expected_result=False,
            expected_calls=3,
            expected_log="discord_notification_failed",
        ),
        id="server_error_max_retries_exceeded",
    ),
]


class TestDiscordNotifierHttpCore:
    @responses.activate
    @pytest.mark.parametrize("case", HTTP_MATRIX_SCENARIOS)
    def test_http_behavior_matrix(self, notifier, make_chapter, case: HttpScenarioCase):
        for r_config in case.response_setup:
            extra_kwargs = {}
            if "json" in r_config:
                extra_kwargs["json"] = r_config["json"]
            else:
                extra_kwargs["body"] = r_config["body"]

            responses.add(
                method=responses.POST,
                url=notifier.webhook_url,
                status=r_config["status"],
                headers=r_config.get("headers", {}),
                **extra_kwargs,
            )

        chapter = make_chapter()

        with capture_logs() as captured:
            result = notifier.send_notification(
                manga_name="Noruega",
                thumbnail="https://manga.com/cover.png",
                chapter=chapter,
            )

        assert result is case.expected_result
        assert len(responses.calls) == case.expected_calls

        logged_events = [log["event"] for log in captured]
        assert case.expected_log in logged_events, (
            f"Expected the event '{case.expected_log}' "
            f"but the following were recorded: {logged_events}"
        )

    @responses.activate
    def test_handles_pure_network_exceptions_and_retries(self, notifier, make_chapter):
        for _ in range(3):
            responses.add(
                method=responses.POST,
                url=notifier.webhook_url,
                body=requests.RequestException("Connection refused by peer"),
            )

        chapter = make_chapter()

        with capture_logs() as captured:
            result = notifier.send_notification("Manga", "https://url.net", chapter)

        assert result is False
        assert len(responses.calls) == 3

        logged_events = [log["event"] for log in captured]
        assert "discord_network_error" in logged_events
        assert "discord_max_retries_exceeded" in logged_events

    @responses.activate
    def test_handles_rate_limit_429_with_retry_after(self, notifier, make_chapter):
        responses.add(
            method=responses.POST,
            url=notifier.webhook_url,
            status=429,
            json={"retry_after": 0.5},
        )
        responses.add(
            method=responses.POST,
            url=notifier.webhook_url,
            status=204,
        )

        chapter = make_chapter()

        with capture_logs() as captured:
            result = notifier.send_notification("Manga", "https://texto.net", chapter)

        assert result is True
        assert len(responses.calls) == 2

        logged_events = [log["event"] for log in captured]
        assert "discord_rate_limit_hit" in logged_events, (
            f"Expected the event 'discord_rate_limit_hit' "
            f"but the following were recorded: {logged_events}"
        )

    @responses.activate
    def test_handles_rate_limit_429_fallback_to_http_headers(self, notifier, make_chapter):
        responses.add(
            method=responses.POST,
            url=notifier.webhook_url,
            status=429,
            body="Bad Rate Limit Payload, no JSON",
            headers={"X-RateLimit-Reset-After": "1.5"},
        )
        responses.add(method=responses.POST, url=notifier.webhook_url, status=204)

        chapter = make_chapter()

        with capture_logs() as captured:
            result = notifier.send_notification("Manga", "https://texto.net", chapter)

        assert result is True
        assert len(responses.calls) == 2

        logs = [log for log in captured if log["event"] == "discord_rate_limit_hit"]
        assert logs[0]["sleep_seconds"] == 1.5


@dataclass(frozen=True)
class ErrorNotificationCase:
    status: int
    expected_log: str


ERROR_MATRIX_SCENARIOS = [
    pytest.param(
        ErrorNotificationCase(status=204, expected_log="discord_error_notification_sent"),
        id="error_alert_success",
    ),
    pytest.param(
        ErrorNotificationCase(status=500, expected_log="discord_error_notification_failed"),
        id="error_alert_failed",
    ),
]


class TestDiscordErrorNotifications:
    @responses.activate
    @pytest.mark.parametrize("case", ERROR_MATRIX_SCENARIOS)
    def test_send_error_notification_http_matrix(
        self, notifier, run_context, case: ErrorNotificationCase
    ):
        responses.add(method=responses.POST, url=notifier.webhook_url, status=case.status)

        with capture_logs() as captured:
            notifier.send_error_notification(
                error_message="Server Imploded", color=0xFF0000, run_context=run_context
            )

        assert len(responses.calls) == (1 if case.status == 204 else 3)

        logged_events = [log["event"] for log in captured]
        assert case.expected_log in logged_events


class TestDiscordNotifierPayloadBuilder:
    def test_buils_chapter_embed_payload(self, notifier, make_chapter):
        chapter = make_chapter(number=Decimal("28.0"), name="Milhouse", language="es")

        payload = notifier.build_chapter_payload(
            chapter=chapter,
            manga_name="Dai Dark",
            thumbnail="https://thumbnail.com",
        )

        assert "embeds" in payload
        embed = payload["embeds"][0]
        assert embed["title"] == "Dai Dark - Chapter 28 - Milhouse"
        assert embed["url"] == chapter.link
        assert embed["thumbnail"]["url"] == "https://thumbnail.com"
        assert embed["fields"][0]["value"] == "es"

    def test_builds_error_embed_payload_local_run(self, notifier, run_context):
        object.__setattr__(run_context, "gh_run_id", "local")

        payload = notifier.build_error_payload(
            error_message="Local PC in flames",
            color=0x111111,
            run_context=run_context,
        )

        embed = payload["embeds"][0]
        assert "Local PC in flames" in embed["description"]
        assert "View GitHub Actions Logs" not in embed["description"]
        assert embed["footer"]["text"] == "MangaDex Notifier"

    def test_builds_error_embed_payload_with_github_actions_context(
        self, notifier, run_context, monkeypatch
    ):
        monkeypatch.setenv("GITHUB_REPOSITORY", "catrilao/manga-tracker")

        context = run_context
        object.__setattr__(context, "gh_run_id", "328746828")
        object.__setattr__(context, "git_commit", "b3h36765456")

        payload = notifier.build_error_payload(
            error_message="Database Connection Refused",
            color=Severity.CRITICAL.value,
            run_context=run_context,
        )

        embed = payload["embeds"][0]
        assert "Database Connection Refused" in embed["description"]
        assert (
            "https://github.com/catrilao/manga-tracker/actions/runs/328746828"
            in embed["description"]
        )
        assert "Commit b3h3676" in embed["footer"]["text"]
