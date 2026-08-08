"""Trend pipeline integration tests.

These run against the shared dev/CI Postgres, which also holds real keywords
synced from config/keywords.yaml. Every keyword used here is therefore
deliberately prefixed "pytest trend " so it can never collide with — or be
cleaned up alongside — a real config keyword. The fixture CSV uses the same
prefixed names for the same reason; tests/fixtures/google_trends_interest_over_time.csv
keeps the realistic keyword names for the parser tests, which touch no database.
"""

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import delete, insert, select

from intelligence.db import keywords_table, trend_metrics_table
from intelligence.trends.base import DiscoveredTerm, TrendObservation, TrendProvider
from intelligence.trends.pipeline import collect_trends, compute_trend_metrics, discover_trend_terms

FIXTURE = Path(__file__).parent.parent / "fixtures" / "google_trends_pipeline_test.csv"

TRACKED_KEYWORDS = ["pytest trend alpha", "pytest trend beta"]
DISCOVERED_KEYWORD = "pytest trend discovered"
ALL_TEST_KEYWORDS = [*TRACKED_KEYWORDS, DISCOVERED_KEYWORD]
TEST_GROUP = "pytest_trends"


class StubDiscoveryProvider(TrendProvider):
    name = "stub_discovery"

    def __init__(self, terms):
        super().__init__({})
        self._terms = terms

    def check_available(self) -> None:
        return None

    def discover_terms(self):
        return iter(self._terms)


@pytest.fixture()
def engine():
    from intelligence.db import get_engine

    get_engine.cache_clear()
    engine = get_engine()

    _cleanup(engine)

    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        for keyword in TRACKED_KEYWORDS:
            conn.execute(
                insert(keywords_table).values(
                    keyword=keyword,
                    keyword_group=TEST_GROUP,
                    language="en",
                    geo="MY",
                    source="config",
                    enabled=True,
                    created_at=now,
                    updated_at=now,
                )
            )

    yield engine

    _cleanup(engine)


def _cleanup(engine):
    """Delete strictly by this test's own keyword names — never by group or by
    source, either of which could sweep up real rows."""

    with engine.begin() as conn:
        keyword_ids = select(keywords_table.c.id).where(keywords_table.c.keyword.in_(ALL_TEST_KEYWORDS))
        conn.execute(delete(trend_metrics_table).where(trend_metrics_table.c.keyword_id.in_(keyword_ids)))
        conn.execute(delete(keywords_table).where(keywords_table.c.keyword.in_(ALL_TEST_KEYWORDS)))


def _stored(engine, keyword: str):
    with engine.begin() as conn:
        return conn.execute(
            select(trend_metrics_table)
            .select_from(trend_metrics_table)
            .join(keywords_table, keywords_table.c.id == trend_metrics_table.c.keyword_id)
            .where(keywords_table.c.keyword == keyword)
            .order_by(trend_metrics_table.c.date)
        ).all()


def test_collect_stores_observations_for_tracked_keywords(engine):
    result = collect_trends(engine, "google_trends_csv", config={"path": str(FIXTURE), "geo": "MY"})

    assert result["received"] == 20
    assert result["inserted"] == 20
    assert result["unknown_keyword"] == 0
    assert len(_stored(engine, "pytest trend alpha")) == 10


def test_every_row_from_one_run_shares_a_collection_batch(engine):
    # Trends values are only comparable within a single collection (§16), so the
    # batch marker has to be reliable, not decorative.
    result = collect_trends(engine, "google_trends_csv", config={"path": str(FIXTURE)})

    batches = {row.collection_batch for row in _stored(engine, "pytest trend alpha")}
    assert batches == {result["batch"]}


def test_recollecting_updates_in_place_rather_than_duplicating(engine):
    collect_trends(engine, "google_trends_csv", config={"path": str(FIXTURE)})
    second = collect_trends(engine, "google_trends_csv", config={"path": str(FIXTURE)})

    assert second["inserted"] == 0
    assert second["updated"] == 20
    assert len(_stored(engine, "pytest trend alpha")) == 10


def test_untracked_keywords_are_skipped_not_auto_created(engine):
    """Monitoring is a curated list (§15B) — a keyword nobody registered must be
    skipped, not silently enrolled.

    Exercised with a stub rather than the CSV provider, because that provider
    already filters to the requested keywords before returning (covered in
    test_google_trends_csv.py). This guard exists for providers that return
    whatever they like — which any future API-backed one may well do.
    """

    class OverreachingProvider(TrendProvider):
        name = "stub_overreaching"

        def check_available(self) -> None:
            return None

        def collect_observations(self, keywords):
            return [
                TrendObservation("pytest trend alpha", date(2026, 5, 10), 50),
                TrendObservation("never registered anywhere", date(2026, 5, 10), 99),
            ]

    result = collect_trends(engine, "stub", provider=OverreachingProvider())

    assert result["received"] == 2
    assert result["inserted"] == 1
    assert result["unknown_keyword"] == 1

    with engine.begin() as conn:
        enrolled = conn.execute(
            select(keywords_table.c.id).where(keywords_table.c.keyword == "never registered anywhere")
        ).first()

    assert enrolled is None


def test_compute_fills_derived_metrics_for_stored_series(engine):
    collect_trends(engine, "google_trends_csv", config={"path": str(FIXTURE)})

    compute_trend_metrics(engine)

    rows = _stored(engine, "pytest trend alpha")
    # The fixture climbs 40 -> 100 over ten weeks, so the final point should be
    # running hotter than its own baseline.
    assert rows[-1].rolling_7d is not None
    assert rows[-1].baseline_90d is not None
    assert float(rows[-1].growth_score) > 1.0
    assert float(rows[-1].growth_30d) > 0


def test_compute_is_idempotent(engine):
    collect_trends(engine, "google_trends_csv", config={"path": str(FIXTURE)})

    compute_trend_metrics(engine)
    first = [(r.date, r.growth_score, r.z_score) for r in _stored(engine, "pytest trend alpha")]

    compute_trend_metrics(engine)
    second = [(r.date, r.growth_score, r.z_score) for r in _stored(engine, "pytest trend alpha")]

    assert first == second
    assert len(_stored(engine, "pytest trend alpha")) == 10


def test_earliest_point_has_no_growth_but_still_stores_a_rolling_average(engine):
    collect_trends(engine, "google_trends_csv", config={"path": str(FIXTURE)})
    compute_trend_metrics(engine)

    first_row = _stored(engine, "pytest trend alpha")[0]

    assert first_row.rolling_7d is not None
    assert first_row.growth_7d is None  # nothing before it to compare against


def test_discovery_registers_unknown_terms_as_discovered_keywords(engine):
    provider = StubDiscoveryProvider(
        [
            DiscoveredTerm(term=DISCOVERED_KEYWORD, observed_on=date(2026, 5, 3), rank=1, score=100),
            DiscoveredTerm(term="pytest trend alpha", observed_on=date(2026, 5, 3), rank=2, score=90),
        ]
    )

    result = discover_trend_terms(engine, "stub", provider=provider)

    assert result["received"] == 2
    assert result["new_keywords"] == 1
    assert result["already_known"] == 1

    with engine.begin() as conn:
        row = conn.execute(
            select(keywords_table.c.source, keywords_table.c.enabled).where(
                keywords_table.c.keyword == DISCOVERED_KEYWORD
            )
        ).first()

    assert row.source == "discovered"
    assert row.enabled is True


def test_provider_can_be_injected_for_monitoring_too(engine):
    class StubMonitoringProvider(TrendProvider):
        name = "stub_monitoring"

        def check_available(self) -> None:
            return None

        def collect_observations(self, keywords):
            return [
                TrendObservation(
                    keyword="pytest trend alpha",
                    observed_on=date(2026, 5, 10) + timedelta(days=i),
                    interest=50 + i,
                )
                for i in range(3)
            ]

    result = collect_trends(engine, "stub", provider=StubMonitoringProvider())

    assert result["inserted"] == 3
    assert result["provider"] == "stub_monitoring"
