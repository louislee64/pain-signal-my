import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import delete, insert, select

from intelligence.aggregate import aggregate_all_topic_daily_metrics
from intelligence.classify import CLASSIFICATION_METHOD
from intelligence.collectors.base import CollectedDocument, Collector
from intelligence.db import (
    document_topics_table,
    normalized_documents_table,
    problem_signals_table,
    raw_documents_table,
    sources_table,
    topic_daily_metrics_table,
    topics_table,
)
from intelligence.ingest import run_ingestion
from intelligence.normalize import normalize_pending_documents
from intelligence.process import classify_and_extract_signals
from intelligence.repositories.sources import get_enabled_source_by_slug

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "multilingual_documents.json").read_text())
TEST_SOURCE_SLUG = "test_source_pipeline"
TEST_TOPIC_SLUGS = ["accounting_sync", "invoice_delivery", "reconciliation", "stock_accuracy"]


class FixtureCollector(Collector):
    def collect(self, since):
        for fixture in FIXTURES:
            yield CollectedDocument(
                external_id=fixture["id"],
                payload={"title": fixture["title"], "body": fixture["body"]},
                title=fixture["title"],
                body=fixture["body"],
                region_raw="Selangor",
            )


def _collector_factory(collector_name, config):
    return FixtureCollector(config)


@pytest.fixture()
def engine():
    from intelligence.db import get_engine

    get_engine.cache_clear()
    engine = get_engine()

    _cleanup(engine)

    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            insert(sources_table).values(
                name="Test Source",
                slug=TEST_SOURCE_SLUG,
                source_type="official_dataset",
                collector="fixture",
                config={},
                terms_status="reviewed",
                personal_data_risk="none",
                enabled=True,
                created_at=now,
                updated_at=now,
            )
        )
        # TEST_TOPIC_SLUGS intentionally match real config/topics.yaml slugs
        # (for realistic classification), so this must never delete them —
        # only create-if-missing, so a real `topics:sync` run (in dev or CI)
        # is left completely alone.
        for slug in TEST_TOPIC_SLUGS:
            exists = conn.execute(select(topics_table.c.id).where(topics_table.c.slug == slug)).first()
            if exists is None:
                conn.execute(
                    insert(topics_table).values(
                        slug=slug,
                        name=slug,
                        enabled=True,
                        created_at=now,
                        updated_at=now,
                    )
                )

    yield engine

    _cleanup(engine)


def _cleanup(engine):
    with engine.begin() as conn:
        source = conn.execute(
            select(sources_table.c.id).where(sources_table.c.slug == TEST_SOURCE_SLUG)
        ).first()
        if source is not None:
            raw_ids = select(raw_documents_table.c.id).where(raw_documents_table.c.source_id == source.id)
            normalized_ids = select(normalized_documents_table.c.id).where(
                normalized_documents_table.c.raw_document_id.in_(raw_ids)
            )
            conn.execute(
                delete(problem_signals_table).where(problem_signals_table.c.document_id.in_(normalized_ids))
            )
            conn.execute(
                delete(document_topics_table).where(document_topics_table.c.document_id.in_(normalized_ids))
            )
            conn.execute(
                delete(normalized_documents_table).where(normalized_documents_table.c.raw_document_id.in_(raw_ids))
            )
            conn.execute(delete(raw_documents_table).where(raw_documents_table.c.source_id == source.id))
            conn.execute(delete(sources_table).where(sources_table.c.id == source.id))

        # Deliberately do not delete TEST_TOPIC_SLUGS here — see the comment
        # in the `engine` fixture above. They are real taxonomy entries; at
        # most this leaves a CI-only DB with a few topics pre-created.


def test_full_pipeline_ingests_normalizes_classifies_and_aggregates(engine):
    ingest_result = run_ingestion(TEST_SOURCE_SLUG, engine=engine, collector_factory=_collector_factory)
    assert ingest_result["inserted"] == len(FIXTURES)

    normalize_result = normalize_pending_documents(engine, source_slug=TEST_SOURCE_SLUG)
    assert normalize_result["processed"] == len(FIXTURES)

    classify_result = classify_and_extract_signals(engine, source_slug=TEST_SOURCE_SLUG)
    assert classify_result["documents"] == len(FIXTURES)
    assert classify_result["topic_matches"] > 0

    with engine.begin() as conn:
        source = get_enabled_source_by_slug(conn, TEST_SOURCE_SLUG)

        languages = conn.execute(
            select(normalized_documents_table.c.language)
            .select_from(normalized_documents_table)
            .join(raw_documents_table, raw_documents_table.c.id == normalized_documents_table.c.raw_document_id)
            .where(raw_documents_table.c.source_id == source.id)
        ).scalars().all()

    assert set(languages) == {f["expected_language"] for f in FIXTURES}

    aggregate_result = aggregate_all_topic_daily_metrics(engine)
    assert aggregate_result["rows"] > 0

    with engine.begin() as conn:
        metrics = conn.execute(
            select(topic_daily_metrics_table).join(
                topics_table, topics_table.c.id == topic_daily_metrics_table.c.topic_id
            ).where(topics_table.c.slug == "reconciliation")
        ).all()

    assert len(metrics) == 1
    assert metrics[0].mention_count == 2  # zh + mixed fixtures both hit reconciliation
    assert metrics[0].region == "Selangor"


def test_pipeline_is_idempotent_on_rerun(engine):
    run_ingestion(TEST_SOURCE_SLUG, engine=engine, collector_factory=_collector_factory)
    normalize_pending_documents(engine, source_slug=TEST_SOURCE_SLUG)
    classify_and_extract_signals(engine, source_slug=TEST_SOURCE_SLUG)

    # Re-running everything must not create duplicate rows.
    run_ingestion(TEST_SOURCE_SLUG, engine=engine, collector_factory=_collector_factory)
    normalize_pending_documents(engine, source_slug=TEST_SOURCE_SLUG)
    second_classify = classify_and_extract_signals(engine, source_slug=TEST_SOURCE_SLUG)

    assert second_classify["documents"] == 0  # already classified, nothing pending

    with engine.begin() as conn:
        source = get_enabled_source_by_slug(conn, TEST_SOURCE_SLUG)
        raw_count = conn.execute(
            select(raw_documents_table.c.id).where(raw_documents_table.c.source_id == source.id)
        ).all()

    assert len(raw_count) == len(FIXTURES)


def test_duplicate_content_is_flagged_not_duplicated(engine):
    class DuplicateCollector(Collector):
        def collect(self, since):
            yield CollectedDocument(external_id="a", payload={"body": "same text"}, body="same text")
            yield CollectedDocument(external_id="b", payload={"body": "same text"}, body="same text")

    run_ingestion(TEST_SOURCE_SLUG, engine=engine, collector_factory=lambda name, cfg: DuplicateCollector(cfg))
    normalize_pending_documents(engine, source_slug=TEST_SOURCE_SLUG)

    with engine.begin() as conn:
        source = get_enabled_source_by_slug(conn, TEST_SOURCE_SLUG)
        rows = conn.execute(
            select(normalized_documents_table.c.duplicate_of_normalized_document_id)
            .select_from(normalized_documents_table)
            .join(raw_documents_table, raw_documents_table.c.id == normalized_documents_table.c.raw_document_id)
            .where(raw_documents_table.c.source_id == source.id)
            .order_by(normalized_documents_table.c.id)
        ).all()

    assert len(rows) == 2
    assert rows[0][0] is None
    assert rows[1][0] is not None
