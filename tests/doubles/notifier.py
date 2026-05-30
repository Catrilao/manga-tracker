from decimal import Decimal
from typing import Any

from src.domain.models import Chapter, RunContext


class MockNotifier:
    def __init__(self) -> None:
        self.notifications_sent: list[dict[str, Any]] = []
        self.errors_sent: list[dict[str, Any]] = []
        self.chapters_to_fail: set[Decimal] = set()

    def send_notification(self, manga_name: str, thumbnail: str, chapter: Chapter) -> bool:
        if chapter.number in self.chapters_to_fail:
            return False

        self.notifications_sent.append(
            {
                "name": manga_name,
                "thumbnail": thumbnail,
                "chapter": chapter.name,
                "number": chapter.number,
            }
        )
        return True

    def send_error_notification(
        self, error_message: str, color: int, run_context: RunContext
    ) -> None:
        self.errors_sent.append(
            {
                "message": error_message,
                "color": color,
                "run_id": run_context.run_id,
            }
        )
