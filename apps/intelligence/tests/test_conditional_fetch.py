"""§38's conditional fetching.

> "Do not download unchanged official datasets unnecessarily. Store:
>  last_modified, etag, dataset_version, last_successful_sync where available."

This matters from Milestone 7 onward because ingestion now runs on a schedule.
Fetching a dataset by hand occasionally is harmless; re-downloading it every
night when the upstream file has not changed wastes a public service's bandwidth
that we are using under its terms (§11).

The distinction these tests are really about is between three outcomes that all
look like "nothing new" from the outside:

  - the source said 304, so nothing was downloaded  → succeeded, no data
  - the source sent data we already had             → succeeded, data
  - the collector is broken and returned nothing    → not covered here; the
                                                      source-health page's
                                                      succeeded-but-empty check
                                                      is what catches that

Conflating the first two would make a source that has been unchanged for a month
indistinguishable from one delivering fresh data daily.
"""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from sqlalchemy import delete, insert, select

from intelligence.collectors.base import (
    CollectedDocument,
    Collector,
    FetchState,
    SourceUnchanged,
)
from intelligence.collectors.data_gov_my import DataGovMyDatasetCollector
from intelligence.db import (
    ingestion_runs_table,
    normalized_documents_table,
    raw_documents_table,
    sources_table,
)
from intelligence.ingest import run_ingestion
from intelligence.repositories import sources

SOURCE_SLUG = "pytest_cond_source"


# --------------------------------------------------------------------- fixtures


def _cleanup(engine) -> None:
    with engine.begin() as conn:
        source_id = conn.execute(
            select(sources_table.c.id).where(sources_table.c.slug == SOURCE_SLUG)
        ).scalar()
        if source_id is None:
            return

        raw_ids = [
            r.id
            for r in conn.execute(
                select(raw_documents_table.c.id).where(
                    raw_documents_table.c.source_id == source_id
                )
            )
        ]
        if raw_ids:
            conn.execute(
                delete(normalized_documents_table).where(
                    normalized_documents_table.c.raw_document_id.in_(raw_ids)
                )
            )
            conn.execute(delete(raw_documents_table).where(raw_documents_table.c.id.in_(raw_ids)))
        conn.execute(
            delete(ingestion_runs_table).where(ingestion_runs_table.c.source_id == source_id)
        )
        conn.execute(delete(sources_table).where(sources_table.c.id == source_id))


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
                name=SOURCE_SLUG,
                slug=SOURCE_SLUG,
                source_type="test",
                collector="test",
                config={},
                terms_status="reviewed",
                personal_data_risk="none",
                enabled=True,
                created_at=now,
                updated_at=now,
            )
        )

    yield engine
    _cleanup(engine)


class RecordingCollector(Collector):
    """Records what fetch_state it was handed, and can report a new one back."""

    def __init__(self, config, documents=None, unchanged=False, new_state=None):
        super().__init__(config)
        self.documents = documents or []
        self.unchanged = unchanged
        self.new_state = new_state or FetchState()
        self.received_state: FetchState | None = None
        self.received_since: datetime | None = None

    def collect(self, since, fetch_state=None):
        self.received_state = fetch_state
        self.received_since = since
        if self.unchanged:
            raise SourceUnchanged("nothing new")
        return iter(self.documents)

    def fetch_state(self) -> FetchState:
        return self.new_state


def _document(index: int = 0) -> CollectedDocument:
    return CollectedDocument(
        external_id=f"pytest_cond_{index}",
        payload={"value": index},
        title=f"doc {index}",
        body=f"body {index}",
    )


def _factory(collector: Collector):
    return lambda collector_name, config: collector


def _source(engine):
    with engine.begin() as conn:
        return sources.get_enabled_source_by_slug(conn, SOURCE_SLUG)


# ------------------------------------------------------------------ the wiring


def test_stored_validators_are_handed_to_the_collector(engine):
    with engine.begin() as conn:
        sources.mark_synced(
            conn,
            _source(engine).id,
            datetime.now(timezone.utc),
            etag='W/"abc123"',
            last_modified="Wed, 05 Aug 2026 00:00:00 GMT",
        )

    collector = RecordingCollector({}, documents=[_document()])
    run_ingestion(SOURCE_SLUG, engine=engine, collector_factory=_factory(collector))

    assert collector.received_state.etag == 'W/"abc123"'
    assert collector.received_state.last_modified == "Wed, 05 Aug 2026 00:00:00 GMT"


def test_validators_returned_by_the_collector_are_stored(engine):
    collector = RecordingCollector(
        {},
        documents=[_document()],
        new_state=FetchState(etag='"v2"', last_modified="Thu, 06 Aug 2026 00:00:00 GMT", dataset_version="7"),
    )

    run_ingestion(SOURCE_SLUG, engine=engine, collector_factory=_factory(collector))
    source = _source(engine)

    assert source.etag == '"v2"'
    assert source.last_modified == "Thu, 06 Aug 2026 00:00:00 GMT"
    assert source.dataset_version == "7"


def test_an_unchanged_source_is_a_success_not_a_failure(engine):
    collector = RecordingCollector({}, unchanged=True)

    result = run_ingestion(SOURCE_SLUG, engine=engine, collector_factory=_factory(collector))

    # §38's happy path: one conditional request, no download, nothing wrong.
    assert result["status"] == "succeeded"
    assert result["source_unchanged"] is True
    assert result["received"] == 0
    assert result["errors"] == 0


def test_an_unchanged_source_does_not_advance_last_successful_sync(engine):
    # The distinction that makes source health meaningful: talking to a source is
    # not the same as receiving data from it.
    collector = RecordingCollector({}, documents=[_document()])
    run_ingestion(SOURCE_SLUG, engine=engine, collector_factory=_factory(collector))
    after_data = _source(engine).last_successful_sync
    assert after_data is not None

    unchanged = RecordingCollector({}, unchanged=True)
    run_ingestion(SOURCE_SLUG, engine=engine, collector_factory=_factory(unchanged))
    source = _source(engine)

    # The invariant, stated without depending on clock resolution: we talked to
    # the source again (so last_synced_at is at least as recent), but received
    # nothing, so last_successful_sync must be exactly where it was.
    assert source.last_successful_sync == after_data
    assert source.last_synced_at >= source.last_successful_sync


def test_an_unchanged_run_is_recorded_on_the_run_metadata(engine):
    collector = RecordingCollector({}, unchanged=True)
    result = run_ingestion(SOURCE_SLUG, engine=engine, collector_factory=_factory(collector))

    with engine.begin() as conn:
        row = conn.execute(
            select(ingestion_runs_table.c.metadata_json).where(
                ingestion_runs_table.c.id == result["run_id"]
            )
        ).scalar_one()

    # So the source-health page can tell "succeeded with zero records because
    # nothing changed" from "succeeded with zero records because the collector is
    # broken" — the quiet failure that page exists for.
    assert row["source_unchanged"] is True


def test_since_uses_last_successful_sync_not_last_attempt(engine):
    # After a 304 or a failure, resuming from "when we last tried" would skip
    # anything published in between.
    first = RecordingCollector({}, documents=[_document()])
    run_ingestion(SOURCE_SLUG, engine=engine, collector_factory=_factory(first))
    successful = _source(engine).last_successful_sync

    unchanged = RecordingCollector({}, unchanged=True)
    run_ingestion(SOURCE_SLUG, engine=engine, collector_factory=_factory(unchanged))

    third = RecordingCollector({}, documents=[_document(1)])
    run_ingestion(SOURCE_SLUG, engine=engine, collector_factory=_factory(third))

    assert third.received_since == successful


def test_a_collector_that_reports_no_validators_does_not_erase_stored_ones(engine):
    # A server that stops sending ETags must not cause us to forget the last good
    # validator and silently drop back to unconditional requests.
    with engine.begin() as conn:
        sources.mark_synced(
            conn, _source(engine).id, datetime.now(timezone.utc), etag='"keep-me"'
        )

    silent = RecordingCollector({}, documents=[_document()], new_state=FetchState())
    run_ingestion(SOURCE_SLUG, engine=engine, collector_factory=_factory(silent))

    assert _source(engine).etag == '"keep-me"'


def test_a_failed_run_does_not_store_validators_or_advance_sync(engine):
    class Broken(Collector):
        def collect(self, since, fetch_state=None):
            raise RuntimeError("upstream exploded")

    result = run_ingestion(SOURCE_SLUG, engine=engine, collector_factory=_factory(Broken({})))
    source = _source(engine)

    assert result["status"] == "failed"
    assert source.last_successful_sync is None
    assert source.etag is None


# ------------------------------------------------------ the real collector


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://example.test/")


def test_data_gov_collector_sends_conditional_headers():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["if_none_match"] = request.headers.get("If-None-Match")
        seen["if_modified_since"] = request.headers.get("If-Modified-Since")
        return httpx.Response(200, json=[{"date": "2026-08-01", "value": 1}])

    collector = DataGovMyDatasetCollector(
        {"dataset_id": "fuelprice", "date_column": "date"}, client=_client(handler)
    )

    list(collector.collect(since=None, fetch_state=FetchState(etag='"e1"', last_modified="Mon, 03 Aug 2026 00:00:00 GMT")))

    assert seen["if_none_match"] == '"e1"'
    assert seen["if_modified_since"] == "Mon, 03 Aug 2026 00:00:00 GMT"


def test_data_gov_collector_raises_source_unchanged_on_304():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(304, headers={"ETag": '"e2"'})

    collector = DataGovMyDatasetCollector(
        {"dataset_id": "fuelprice", "date_column": "date"}, client=_client(handler)
    )

    with pytest.raises(SourceUnchanged):
        list(collector.collect(since=None, fetch_state=FetchState(etag='"e1"')))

    # Recorded even on 304: a server may rotate a weak validator without the body
    # changing, and storing the newest keeps the next request conditional.
    assert collector.fetch_state().etag == '"e2"'


def test_data_gov_collector_captures_validators_from_a_200():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[{"date": "2026-08-01", "value": 1}],
            headers={"ETag": '"fresh"', "Last-Modified": "Fri, 07 Aug 2026 00:00:00 GMT"},
        )

    collector = DataGovMyDatasetCollector(
        {"dataset_id": "fuelprice", "date_column": "date"}, client=_client(handler)
    )

    documents = list(collector.collect(since=None))

    assert len(documents) == 1
    assert collector.fetch_state().etag == '"fresh"'
    assert collector.fetch_state().last_modified == "Fri, 07 Aug 2026 00:00:00 GMT"


def test_data_gov_collector_still_raises_on_a_real_error():
    # A 304 must be the only status that bypasses raise_for_status(); letting a
    # 500 through as "unchanged" would turn an outage into a silent no-op.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="no such dataset")

    collector = DataGovMyDatasetCollector(
        {"dataset_id": "nope", "date_column": "date"}, client=_client(handler)
    )

    with pytest.raises(httpx.HTTPStatusError):
        list(collector.collect(since=None))


def test_a_collector_with_no_conditional_support_still_works(engine):
    # Most sources expose none of this. The default FetchState() is empty and
    # ingestion must be entirely happy with that.
    class Simple(Collector):
        def collect(self, since, fetch_state=None):
            return iter([_document()])

    result = run_ingestion(SOURCE_SLUG, engine=engine, collector_factory=_factory(Simple({})))

    assert result["status"] == "succeeded"
    assert result["source_unchanged"] is False
    assert result["inserted"] == 1
    assert _source(engine).etag is None
