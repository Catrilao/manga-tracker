from src.domain.models import DatabaseError, DOMChangeError, ParseError
from tests.scenarios.plan_scenario import SyncPlanScenario


class TestsSyncPlanGuards:
    def test_massive_chapter_drop_raises_dom_change_error(self, plan_scenario):
        (
            plan_scenario.with_active_series(chapter_count=100, max_chapter_number="100")
            .scraper_finds_chapters(*[str(i) for i in range(49)])
            .calculate()
            .assert_error_raised(DOMChangeError, "less than 50% of chapters")
        )

    def test_high_null_ratio_raises_parse_error(self, plan_scenario):
        (
            plan_scenario.scraper_finds_chapters("1", "2", "3", "4", "5", "6", "7")
            .scraper_finds_invalid_chapter(link="")
            .scraper_finds_invalid_chapter(language="")
            .scraper_finds_invalid_chapter(number="-1.0")
            .calculate()
            .assert_error_raised(ParseError, "High volume")
        )

    def test_scraper_max_is_lower_than_db_raises_parse_error(self, plan_scenario):
        (
            plan_scenario.with_active_series(chapter_count=2, max_chapter_number="100")
            .scraper_finds_chapters("99")
            .calculate()
            .assert_error_raised(ParseError, "Max chapter in DB is bigger")
        )


class TestSyncPlanBusinessRules:
    def test_filters_invalid_chapters_and_generates_warnings(self, plan_scenario):
        (
            plan_scenario.scraper_finds_chapters("1", "2", "3", "4", "5", "6", "7", "8")
            .scraper_finds_invalid_chapter(link="")
            .scraper_finds_invalid_chapter(language="")
            .scraper_finds_invalid_chapter(number="-1.0")
            .calculate()
            .assert_inserts("1", "2", "3", "4", "5", "6", "7", "8")
            .assert_warnings_logged(
                "null_chapter_link", "null_chapter_language", "null_chapter_number"
            )
        )

    def test_deduplicates_chapters_with_same_identifier(self, plan_scenario):
        (
            plan_scenario.scraper_finds_chapters("5", name="Scanlation A")
            .scraper_finds_chapters("5", name="Scanlation B")
            .calculate()
            .assert_inserts("5")  # Should only be inserted once
        )

    def test_skips_notifications_for_backfilled_chapters(self, plan_scenario):
        (
            plan_scenario.with_active_series(chapter_count=2, max_chapter_number="100")
            .scraper_finds_chapters("101", "94")
            .calculate()
            .assert_inserts("101", "94")
            .assert_notifies("101")
        )

    def test_prevents_notification_spam(self, plan_scenario):
        (
            plan_scenario.with_active_series(chapter_count=2, max_chapter_number="100")
            .with_existing_chapters(("100", "en"))
            .scraper_finds_chapters("101", "102", "103", "104", "105", "106")
            .calculate()
            .assert_inserts("101", "102", "103", "104", "105", "106")
            .assert_notifies("106", "105", "104", "103", "102")  # Top 5
            .assert_warnings_logged("notification_spam_prevented")
        )

    def test_plan_raises_db_error_if_max_number_is_missing(self, make_chapter, make_db_metadata):
        scenario = SyncPlanScenario(make_chapter, make_db_metadata)

        scenario.db_kwargs.update({"is_cold_start": False, "max_chapter_number": None})

        scenario.calculate().assert_error_raised(
            DatabaseError, "'max_number_db' is None but not cold start"
        )

    def test_plan_raises_dom_change_error_if_empty_scraper(self, make_chapter, make_db_metadata):
        scenario = SyncPlanScenario(make_chapter, make_db_metadata)

        scenario.calculate().assert_error_raised(
            DOMChangeError, "Scraper returned zero chapters. Possible DOM change"
        )
