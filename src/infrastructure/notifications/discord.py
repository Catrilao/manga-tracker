import os
import random
import time
from typing import Any

import requests
from structlog import get_logger

from src.domain.models import Chapter, RunContext


class DiscordNotifier:
    """
    Adapter for Discord Webhooks.
    Fulfills the NotifierPort contract.

    CONTRACT: This adapter handles its own HTTP errors gracefully.
    It returns True on success and False on failure, preventing
    network blips to Discord from crashing the main sync pipeline.
    """

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url

    def post_with_retry(
        self,
        payload: dict[str, Any],
        max_retries: int = 3,
    ) -> requests.Response | None:
        log = get_logger(__name__)

        base_delay = 1.0
        last_response = None
        for attempt in range(max_retries):
            response = None
            try:
                response = requests.post(self.webhook_url, json=payload, timeout=10)
                last_response = response

                # Success
                if response.ok:
                    return response

                # Rate limit
                if response.status_code == 429:
                    try:
                        retry_after = float(response.json().get("retry_after", 2.0))
                    except Exception:
                        retry_after = float(response.headers.get("X-RateLimit-Reset-After", 2.0))
                    log.warning(
                        "discord_rate_limit_hit",
                        attempt=attempt + 1,
                        sleep_seconds=retry_after,
                    )
                    if attempt < max_retries - 1:
                        time.sleep(retry_after)
                    continue

                # Server errors
                if response.status_code in {500, 502, 503, 504}:
                    delay = min(base_delay + (2**attempt) + random.uniform(0, 1), 30)
                    log.warning(
                        "discord_server_error",
                        attempt=attempt + 1,
                        http_status=response.status_code,
                        sleep_seconds=round(delay, 2),
                    )
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                    continue

                # Client errors
                # No point in retrying, either the URL or payload is invalid
                return response

            # Network/connection failure
            except requests.RequestException as e:
                delay = min(base_delay + (2**attempt) + random.uniform(0, 1), 30)
                log.warning(
                    "discord_network_error",
                    attempt=attempt + 1,
                    error=str(e),
                    sleep_seconds=round(delay, 2),
                )
                if attempt < max_retries - 1:
                    time.sleep(delay)

        log.error("discord_max_retries_exceeded", max_retries=max_retries)
        return last_response

    def build_chapter_payload(
        self,
        chapter: Chapter,
        manga_name: str,
        thumbnail: str,
    ) -> dict[str, Any]:
        embed = {
            "title": f"{manga_name} - Chapter {str(chapter.number.normalize())} - {chapter.name}",
            "url": chapter.link,
            "color": 0xAC5F29,
            "fields": [
                {"name": "Language", "value": chapter.language, "inline": True},
            ],
            "footer": {"text": "MangaDex Notifier"},
            "thumbnail": {"url": thumbnail},
        }
        return {"embeds": [embed]}

    def build_error_payload(
        self,
        error_message: str,
        color: int,
        run_context: RunContext | None = None,
    ) -> dict[str, Any]:
        text_footer = "MangaDex Notifier"
        if run_context and run_context.gh_run_id != "local":
            repo = os.getenv("GITHUB_REPOSITORY", "catrilao/manga-tracker")
            action_url = f"https://github.com/{repo}/actions/runs/{run_context.gh_run_id}"

            error_message += f"\n\n**[View GitHub Actions Logs]({action_url})**"
            text_footer += f" | Commit {run_context.git_commit[:7]}"

        embed = {
            "title": "Health Check: Error in the Tracker",
            "description": error_message,
            "color": color,
            "footer": {"text": text_footer},
        }
        return {"embeds": [embed]}

    def send_notification(
        self,
        manga_name: str,
        thumbnail: str,
        chapter: Chapter,
    ) -> bool:
        log = get_logger(__name__)

        payload = self.build_chapter_payload(chapter, manga_name, thumbnail)
        response = self.post_with_retry(payload)

        if response is not None and response.ok:
            log.info(
                "discord_notification_sent",
                manga_name=manga_name,
                chapter_number=str(chapter.number.normalize()),
                chapter_language=chapter.language,
            )
            return True

        status = response.status_code if response is not None else "Network Error / Timeout"
        body = response.text[:176] if response is not None else ""
        log.warning(
            "discord_notification_failed",
            manga_name=manga_name,
            chapter_number=str(chapter.number.normalize()),
            http_status=status,
            response_body=body,
        )
        return False

    def send_error_notification(
        self,
        error_message: str,
        color: int,
        run_context: RunContext,
    ) -> None:
        log = get_logger(__name__)

        payload = self.build_error_payload(error_message, color, run_context)
        response = self.post_with_retry(payload)

        if response and response.ok:
            log.info(
                "discord_error_notification_sent",
                error_message=error_message[:176],
            )
            return

        status = response.status_code if response is not None else "Network Error / Timeout"
        body = response.text[:176] if response is not None else ""
        log.warning(
            "discord_error_notification_failed",
            http_status=status,
            response_body=body,
        )
