from collections.abc import Callable
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from src.domain.models import Chapter, DBMetadata, Manga, RawChapter, RunContext, Source
from tests.doubles.notifier import MockNotifier
from tests.scenarios.plan_scenario import SyncPlanScenario
from tests.scenarios.sync_scenario import MangaSyncScenario

pytest_plugins = ["pytest_playwright"]


@pytest.fixture
def mock_notifier() -> MockNotifier:
    return MockNotifier()


@pytest.fixture
def run_context() -> RunContext:
    return RunContext(run_id=uuid4(), gh_run_id="test-gh-id", git_commit="test-commit")


@pytest.fixture
def make_manga() -> Callable[..., Manga]:
    """
    Factory to create new valid mangas
    """

    def _make(**kwargs) -> Manga:
        defaults = {
            "uuid": uuid4(),
            "name": "Test Manga Default",
            "thumbnail": "https://img.manga/default",
            "sources": (
                Source(
                    provider_name="mangadex", target_url="https://mangadex.org/", is_active=True
                ),
            ),
        }
        defaults.update(kwargs)
        return Manga(**defaults)

    return _make


@pytest.fixture
def make_chapter() -> Callable[..., Chapter]:
    """
    Fatory to create new valid chapters
    """

    def _make(**kwargs) -> Chapter:
        defaults = {
            "manga_id": uuid4(),
            "number": Decimal("1.0"),
            "name": "Default",
            "link": "https://link.default",
            "language": "es",
        }
        defaults.update(kwargs)
        return Chapter(**defaults)

    return _make


@pytest.fixture
def make_raw_chapter() -> Callable[..., RawChapter]:
    """
    Fatory to create new valid chapters
    """

    def _make(**kwargs) -> RawChapter:
        defaults = {
            "info_text": "Eye Care",
            "header_text": "Chapter 57",
            "href": "/chapter/ba5ec0e2-70bc-4359-9584-9913c2b99470",
            "language_title": "English",
        }
        defaults.update(kwargs)
        return RawChapter(**defaults)

    return _make


@pytest.fixture
def make_db_metadata() -> Callable[..., DBMetadata]:
    """
    Factory for the database state
    """

    def _make(**kwargs) -> DBMetadata:
        defaults = {
            "manga_id": UUID("00000000-0000-0000-0000-000000000000"),
            "is_cold_start": True,
            "chapter_count": 0,
            "max_chapter_number": None,
            "existing_chapter_identifiers": frozenset(),
        }
        defaults.update(kwargs)
        return DBMetadata(**defaults)

    return _make


@pytest.fixture
def sync_scenario(
    run_context, mock_notifier, make_manga, make_raw_chapter, make_chapter, make_db_metadata
):
    return MangaSyncScenario(
        run_context, mock_notifier, make_manga, make_raw_chapter, make_chapter, make_db_metadata
    )


@pytest.fixture
def plan_scenario(make_chapter, make_db_metadata):
    return SyncPlanScenario(make_chapter, make_db_metadata)
