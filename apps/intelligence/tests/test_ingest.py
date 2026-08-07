from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, insert, select, text

from intelligence.collectors.base import CollectedDocument, Collector
from intelligence.config import Settings
from intelligence.db import raw_documents_table, sources_table
from intelligence.ingest import UnknownSourceError, run_ingestion
from intelligence.repositories.sources import get_enabled_source_by_slug

TEST_SLUG = "test_source_ingest"


class FakeCollector(Collector):
    def __init__(self, config, documents):
        super().__init__(config)
        self._documents = documents

    def collect(self, since):
        return iter(self._documents)


def _factory(documents):
    return lambda collector_name, config: FakeCollector(config, documents)


@pytest.fixture()
def engine():
    from intelligence.db import get_engine

    get_engine.cache_clear()
    engine = get_engine()

    with engine.begin() as conn:
        conn.execute(delete(sources_table).where(sources_table.c.slug == TEST_SLUG))

    with engine.begin() as conn:
        now = datetime.now(timezone.utc)
        conn.execute(
            insert(sources_table).values(
                name="Test Source",
                slug=TEST_SLUG,
                source_type="official_dataset",
                collector="fake",
                config={},
                terms_status="reviewed",
                personal_data_risk="none",
                enabled=True,
                created_at=now,
                updated_at=now,
            )
        )

    yield engine

    with engine.begin() as conn:
        conn.execute(delete(sources_table).where(sources_table.c.slug == TEST_SLUG))


def _raw_document_count(engine, source_id: int) -> int:
    with engine.connect() as conn:
        return conn.execute(
            select(text("count(*)")).select_from(raw_documents_table).where(
                raw_documents_table.c.source_id == source_id
            )
        ).scalar()


def test_run_ingestion_is_idempotent(engine):
    documents = [
        CollectedDocument(external_id="a", payload={"value": 1}),
        CollectedDocument(external_id="b", payload={"value": 2}),
    ]

    first = run_ingestion(TEST_SLUG, engine=engine, collector_factory=_factory(documents))
    assert first["status"] == "succeeded"
    assert first["received"] == 2
    assert first["inserted"] == 2
    assert first["updated"] == 0

    second = run_ingestion(TEST_SLUG, engine=engine, collector_factory=_factory(documents))
    assert second["received"] == 2
    assert second["inserted"] == 0
    assert second["unchanged"] == 2

    with engine.begin() as conn:
        source = get_enabled_source_by_slug(conn, TEST_SLUG)

    assert _raw_document_count(engine, source.id) == 2


def test_run_ingestion_updates_row_when_source_content_changes(engine):
    run_ingestion(
        TEST_SLUG,
        engine=engine,
        collector_factory=_factory([CollectedDocument(external_id="a", payload={"value": 1})]),
    )

    result = run_ingestion(
        TEST_SLUG,
        engine=engine,
        collector_factory=_factory([CollectedDocument(external_id="a", payload={"value": 2})]),
    )

    assert result["inserted"] == 0
    assert result["updated"] == 1

    with engine.begin() as conn:
        source = get_enabled_source_by_slug(conn, TEST_SLUG)

    assert _raw_document_count(engine, source.id) == 1


def test_run_ingestion_raises_for_unknown_source(engine):
    with pytest.raises(UnknownSourceError):
        run_ingestion("does_not_exist_at_all", engine=engine)


def test_run_ingestion_one_bad_document_does_not_abort_the_run(engine):
    good = CollectedDocument(external_id="good", payload={"value": 1})
    bad = CollectedDocument(external_id=None, payload={"value": 2})  # violates NOT NULL external_id

    result = run_ingestion(TEST_SLUG, engine=engine, collector_factory=_factory([good, bad]))

    assert result["status"] == "succeeded"
    assert result["received"] == 2
    assert result["inserted"] == 1
    assert result["rejected"] == 1
    assert result["errors"] == 1
