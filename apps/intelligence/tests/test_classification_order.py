"""Regression test for classification starvation.

A document that matches no keyword produces no `document_topics` row, so it stays
in the "unclassified" set permanently and is re-scanned on every run. That is a
deliberate trade (rule-based matching is cheap), but combined with `LIMIT` and no
`ORDER BY` it had a failure mode nobody would notice: Postgres was free to return
the same arbitrary batch of never-matching documents forever, so once the
unmatched backlog grew past `batch_size`, newly ingested documents were never
classified at all.

It stayed invisible while the only source was data.gov.my fuel prices — 945
documents that match nothing by design, and no newer documents to starve. Adding
a news source made it reachable and immediate: classification reported "500
documents, 0 matches" on every pass while the freshly ingested articles sat
untouched.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, insert, select

from intelligence.classify import CLASSIFICATION_METHOD
from intelligence.db import (
    document_topics_table,
    normalized_documents_table,
    problem_signals_table,
    raw_documents_table,
    sources_table,
)
from intelligence.repositories import normalized_documents, raw_documents
from intelligence.repositories.normalized_documents import (
    NormalizedDocumentInput,
    get_unclassified_documents,
)

SOURCE_SLUG = "pytest_order_source"
BATCH = 3
TOTAL = 10


@pytest.fixture()
def source_id():
    from intelligence.db import get_engine

    get_engine.cache_clear()
    engine = get_engine()

    _cleanup(engine)

    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            insert(sources_table).values(
                name="Ordering test source",
                slug=SOURCE_SLUG,
                source_type="news_feed",
                collector="fixture",
                config={},
                terms_status="reviewed",
                personal_data_risk="none",
                enabled=True,
                created_at=now,
                updated_at=now,
            )
        )
        sid = conn.execute(
            select(sources_table.c.id).where(sources_table.c.slug == SOURCE_SLUG)
        ).scalar_one()

        # TOTAL documents, one per day, oldest first. None of them contain a
        # taxonomy keyword — they stand in for the never-matching backlog.
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for i in range(TOTAL):
            published = base + timedelta(days=i)
            raw_documents.upsert(
                conn,
                raw_documents.RawDocumentInput(
                    source_id=sid,
                    external_id=f"{SOURCE_SLUG}_{i:02d}",
                    content_hash=f"{'0' * 60}{i:04d}"[:64],
                    collected_at=now,
                    title=f"Filler document {i}",
                    body="Nothing in this text matches any configured topic keyword.",
                    published_at=published,
                ),
            )

        raw_rows = conn.execute(
            select(raw_documents_table.c.id, raw_documents_table.c.published_at)
            .where(raw_documents_table.c.source_id == sid)
            .order_by(raw_documents_table.c.published_at)
        ).all()

        for row in raw_rows:
            normalized_documents.upsert(
                conn,
                NormalizedDocumentInput(
                    raw_document_id=row.id,
                    cleaned_text="Nothing in this text matches any configured topic keyword.",
                    language="en",
                    country="MY",
                    state=None,
                    city=None,
                    normalized_content_hash=None,
                    processed_at=now,
                    duplicate_of_normalized_document_id=None,
                ),
            )

    yield sid

    _cleanup(engine)


def _cleanup(engine):
    with engine.begin() as conn:
        existing = conn.execute(
            select(sources_table.c.id).where(sources_table.c.slug == SOURCE_SLUG)
        ).first()
        if existing is None:
            return

        raw_ids = select(raw_documents_table.c.id).where(
            raw_documents_table.c.source_id == existing.id
        )
        normalized_ids = select(normalized_documents_table.c.id).where(
            normalized_documents_table.c.raw_document_id.in_(raw_ids)
        )
        conn.execute(
            delete(problem_signals_table).where(
                problem_signals_table.c.document_id.in_(normalized_ids)
            )
        )
        conn.execute(
            delete(document_topics_table).where(
                document_topics_table.c.document_id.in_(normalized_ids)
            )
        )
        conn.execute(
            delete(normalized_documents_table).where(
                normalized_documents_table.c.raw_document_id.in_(raw_ids)
            )
        )
        conn.execute(delete(raw_documents_table).where(raw_documents_table.c.source_id == existing.id))
        conn.execute(delete(sources_table).where(sources_table.c.id == existing.id))


def test_a_limited_batch_returns_the_newest_documents(source_id):
    """The whole point: a newly published document must be reachable even when
    the unmatched backlog is larger than the batch."""
    from intelligence.db import get_engine

    with get_engine().begin() as conn:
        batch = get_unclassified_documents(
            conn, CLASSIFICATION_METHOD, limit=BATCH, source_id=source_id
        )

    assert len(batch) == BATCH
    dates = [d.signal_date for d in batch]
    assert dates == sorted(dates, reverse=True), "batch must be newest-first"
    # Day 10 is the newest of the ten inserted; it must be in the first batch of
    # three, which is exactly what an unordered LIMIT could not guarantee.
    assert dates[0] == datetime(2026, 1, 10, tzinfo=timezone.utc).date()


def test_the_order_is_stable_across_calls(source_id):
    """Two identical calls must agree.

    signal_date alone is not a total order — a whole feed can share one date — so
    without the id tiebreak the tail of each batch could shuffle between runs and
    reintroduce the starvation the ordering exists to prevent.
    """
    from intelligence.db import get_engine

    with get_engine().begin() as conn:
        first = get_unclassified_documents(
            conn, CLASSIFICATION_METHOD, limit=BATCH, source_id=source_id
        )
        second = get_unclassified_documents(
            conn, CLASSIFICATION_METHOD, limit=BATCH, source_id=source_id
        )

    assert [d.id for d in first] == [d.id for d in second]
