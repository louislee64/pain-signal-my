"""End-to-end scoring against a real Postgres.

Everything this creates is prefixed "pytest scoring " / `pytest_scoring_` so it
can never collide with, or be cleaned up alongside, the real config-synced rows
that share this database — the lesson from the Milestone 2 test-isolation bug.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, insert, select
from ulid import ULID

from intelligence.db import (
    document_topics_table,
    normalized_documents_table,
    opportunities_table,
    problem_signals_table,
    raw_documents_table,
    sources_table,
    topics_table,
)
from intelligence.scoring.config import load_scoring_config
from intelligence.scoring.engine import score_all_topics
from intelligence.scoring.measurements import gather_measurements

SOURCE_SLUG = "pytest_scoring_source"
SECOND_SOURCE_SLUG = "pytest_scoring_source_two"
TOPIC_SLUG = "pytest_scoring_topic"
TODAY = date(2026, 8, 8)
from conftest import SCORING_CONFIG_PATH as CONFIG_PATH


@pytest.fixture()
def config():
    return load_scoring_config(CONFIG_PATH)


@pytest.fixture()
def engine():
    from intelligence.db import get_engine

    get_engine.cache_clear()
    engine = get_engine()
    _cleanup(engine)

    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        for slug in (SOURCE_SLUG, SECOND_SOURCE_SLUG):
            conn.execute(
                insert(sources_table).values(
                    name=slug, slug=slug, source_type="test", collector="test", config={},
                    terms_status="reviewed", personal_data_risk="none", enabled=True,
                    created_at=now, updated_at=now,
                )
            )
        conn.execute(
            insert(topics_table).values(
                slug=TOPIC_SLUG, name="Pytest Scoring Topic", enabled=True,
                created_at=now, updated_at=now,
            )
        )

    yield engine

    _cleanup(engine)


def _cleanup(engine):
    with engine.begin() as conn:
        topic_ids = select(topics_table.c.id).where(topics_table.c.slug == TOPIC_SLUG)
        source_ids = select(sources_table.c.id).where(
            sources_table.c.slug.in_([SOURCE_SLUG, SECOND_SOURCE_SLUG])
        )
        raw_ids = select(raw_documents_table.c.id).where(raw_documents_table.c.source_id.in_(source_ids))
        norm_ids = select(normalized_documents_table.c.id).where(
            normalized_documents_table.c.raw_document_id.in_(raw_ids)
        )

        conn.execute(delete(opportunities_table).where(opportunities_table.c.topic_id.in_(topic_ids)))
        conn.execute(delete(problem_signals_table).where(problem_signals_table.c.document_id.in_(norm_ids)))
        conn.execute(delete(document_topics_table).where(document_topics_table.c.document_id.in_(norm_ids)))
        conn.execute(
            delete(normalized_documents_table).where(
                normalized_documents_table.c.raw_document_id.in_(raw_ids)
            )
        )
        conn.execute(delete(raw_documents_table).where(raw_documents_table.c.source_id.in_(source_ids)))
        conn.execute(delete(topics_table).where(topics_table.c.slug == TOPIC_SLUG))
        conn.execute(
            delete(sources_table).where(sources_table.c.slug.in_([SOURCE_SLUG, SECOND_SOURCE_SLUG]))
        )


def seed_signal(
    engine,
    *,
    signal_date: date,
    source_slug: str = SOURCE_SLUG,
    severity: int | None = 70,
    urgency: int | None = 60,
    economic_impact: int | None = 65,
    payer_type: str | None = "business_owner",
    frequency_hint: str | None = "daily",
    region: str = "Selangor",
    confidence: int = 75,
) -> None:
    now = datetime.now(timezone.utc)
    raw_id = str(ULID())

    with engine.begin() as conn:
        source_id = conn.execute(
            select(sources_table.c.id).where(sources_table.c.slug == source_slug)
        ).scalar_one()
        topic_id = conn.execute(
            select(topics_table.c.id).where(topics_table.c.slug == TOPIC_SLUG)
        ).scalar_one()

        conn.execute(
            insert(raw_documents_table).values(
                id=raw_id, source_id=source_id, external_id=raw_id, body="seeded",
                collected_at=now, content_hash=raw_id, created_at=now,
            )
        )
        document_id = conn.execute(
            insert(normalized_documents_table)
            .values(raw_document_id=raw_id, cleaned_text="seeded", language="en",
                    country="MY", state=region, processed_at=now)
            .returning(normalized_documents_table.c.id)
        ).scalar_one()

        conn.execute(
            insert(document_topics_table).values(
                document_id=document_id, topic_id=topic_id, confidence=confidence,
                classification_method="pytest", created_at=now, updated_at=now,
            )
        )
        conn.execute(
            insert(problem_signals_table).values(
                document_id=document_id, topic_id=topic_id, signal_date=signal_date,
                region=region, severity_score=severity, urgency_score=urgency,
                economic_impact_score=economic_impact, frequency_hint=frequency_hint,
                payer_type=payer_type, evidence_json={}, classification_method="pytest",
                created_at=now, updated_at=now,
            )
        )


def _opportunity(engine):
    with engine.begin() as conn:
        return conn.execute(
            select(opportunities_table)
            .join(topics_table, topics_table.c.id == opportunities_table.c.topic_id)
            .where(topics_table.c.slug == TOPIC_SLUG)
        ).first()


def _measurements(engine, config):
    with engine.begin() as conn:
        topic_id = conn.execute(
            select(topics_table.c.id).where(topics_table.c.slug == TOPIC_SLUG)
        ).scalar_one()
        return gather_measurements(conn, config, TODAY)[topic_id]


def test_gathers_measurements_from_real_signals(engine, config):
    for i in range(5):
        seed_signal(engine, signal_date=TODAY - timedelta(days=i))

    m = _measurements(engine, config)

    assert m.topic_slug == TOPIC_SLUG
    assert m.mention_count == 5
    assert m.avg_severity == pytest.approx(70)
    assert m.avg_urgency == pytest.approx(60)
    assert m.avg_economic_impact == pytest.approx(65)
    assert m.signals_with_payer == 5
    assert m.dominant_frequency_hint == "daily"
    assert m.latest_signal_date == TODAY


def test_distinct_sources_counts_sources_not_documents(engine, config):
    """§31 ranks multiple independent sources far above multiple posts, so one
    chatty source must not impersonate corroboration."""
    for i in range(4):
        seed_signal(engine, signal_date=TODAY - timedelta(days=i), source_slug=SOURCE_SLUG)

    assert _measurements(engine, config).distinct_sources == 1

    seed_signal(engine, signal_date=TODAY, source_slug=SECOND_SOURCE_SLUG)

    assert _measurements(engine, config).distinct_sources == 2


def test_growth_compares_against_the_preceding_window(engine, config):
    window = config.window_days()

    # 2 signals in the previous window, 6 in the current one.
    for i in range(2):
        seed_signal(engine, signal_date=TODAY - timedelta(days=window + i))
    for i in range(6):
        seed_signal(engine, signal_date=TODAY - timedelta(days=i))

    m = _measurements(engine, config)

    assert m.mention_count == 6
    assert m.previous_mention_count == 2


def test_signals_outside_the_window_are_excluded(engine, config):
    window = config.window_days()
    seed_signal(engine, signal_date=TODAY - timedelta(days=window * 5))
    seed_signal(engine, signal_date=TODAY)

    assert _measurements(engine, config).mention_count == 1


def test_dominant_frequency_hint_is_modal_not_averaged(engine, config):
    # "daily" and "monthly" have no meaningful midpoint; the most commonly
    # observed cadence is the only honest summary.
    for _ in range(3):
        seed_signal(engine, signal_date=TODAY, frequency_hint="weekly")
    seed_signal(engine, signal_date=TODAY, frequency_hint="monthly")

    assert _measurements(engine, config).dominant_frequency_hint == "weekly"


def test_score_creates_an_opportunity_with_stored_explanation(engine):
    for i in range(5):
        seed_signal(engine, signal_date=TODAY - timedelta(days=i))

    result = score_all_topics(engine, as_of=TODAY)
    assert result["created"] >= 1

    row = _opportunity(engine)
    assert row is not None
    assert row.pain_score is not None
    assert row.commercial_score is not None
    assert row.opportunity_score is not None
    assert row.confidence_score is not None
    assert row.recommendation is not None
    assert row.scoring_config_version is not None

    # Milestone 4's acceptance criterion, checked against what is actually
    # persisted rather than what was computed in memory.
    components = row.score_components
    for key in ("pain_score", "commercial_score", "confidence_score", "opportunity_score"):
        assert components[key]["dimensions"], f"{key} must persist its dimensions"

    recomputed = sum(d["contribution"] for d in components["pain_score"]["dimensions"].values())
    assert float(row.pain_score) == pytest.approx(recomputed, abs=0.05)


def test_rescoring_updates_in_place_rather_than_duplicating(engine):
    seed_signal(engine, signal_date=TODAY)

    first = score_all_topics(engine, as_of=TODAY)
    second = score_all_topics(engine, as_of=TODAY)

    assert first["created"] >= 1
    assert second["created"] == 0
    assert second["updated"] >= 1

    with engine.begin() as conn:
        topic_id = conn.execute(
            select(topics_table.c.id).where(topics_table.c.slug == TOPIC_SLUG)
        ).scalar_one()
        rows = conn.execute(
            select(opportunities_table.c.id).where(opportunities_table.c.topic_id == topic_id)
        ).all()

    assert len(rows) == 1


def test_rescoring_never_overwrites_human_owned_fields(engine):
    """§52: AI suggests, a human approves. A nightly rescore must not undo a
    person's funnel decision or their written analysis."""
    seed_signal(engine, signal_date=TODAY)
    score_all_topics(engine, as_of=TODAY)

    with engine.begin() as conn:
        conn.execute(
            opportunities_table.update()
            .where(opportunities_table.c.id == _opportunity(engine).id)
            .values(
                status="problem_validated",
                problem_statement="A human wrote this after interviewing three operators.",
                monetization_model="setup fee + subscription",
            )
        )

    seed_signal(engine, signal_date=TODAY)
    score_all_topics(engine, as_of=TODAY)

    row = _opportunity(engine)
    assert row.status == "problem_validated"
    assert row.problem_statement.startswith("A human wrote this")
    assert row.monetization_model == "setup fee + subscription"


def test_more_evidence_raises_the_score(engine):
    seed_signal(engine, signal_date=TODAY)
    score_all_topics(engine, as_of=TODAY)
    thin = float(_opportunity(engine).opportunity_score)

    for i in range(1, 20):
        seed_signal(engine, signal_date=TODAY - timedelta(days=i % 5), source_slug=SECOND_SOURCE_SLUG)
    score_all_topics(engine, as_of=TODAY)
    thick = float(_opportunity(engine).opportunity_score)

    assert thick > thin


def test_topics_with_no_signals_produce_no_opportunity(engine):
    # The real fuelprice dataset behaves exactly like this: numeric price data
    # matches no topic keywords, so it yields no signals and therefore no
    # opportunity. Silence is the correct output, not a zero-scored row.
    result = score_all_topics(engine, as_of=TODAY)

    assert result["scored"] == 0
    assert _opportunity(engine) is None
