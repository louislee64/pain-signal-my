from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.engine import Engine

from intelligence.collectors.base import CollectedDocument, Collector
from intelligence.collectors.registry import get_collector_class
from intelligence.db import get_engine
from intelligence.hashing import compute_content_hash
from intelligence.observability import get_logger, log_event
from intelligence.repositories import ingestion_runs, raw_documents, sources

logger = get_logger("intelligence.ingest")

CollectorFactory = Callable[[str, dict[str, Any]], Collector]


class UnknownSourceError(RuntimeError):
    pass


def _default_collector_factory(collector_name: str, config: dict[str, Any]) -> Collector:
    return get_collector_class(collector_name)(config)


def run_ingestion(
    source_slug: str,
    *,
    engine: Engine | None = None,
    collector_factory: CollectorFactory = _default_collector_factory,
) -> dict[str, Any]:
    engine = engine or get_engine()

    with engine.begin() as conn:
        source = sources.get_enabled_source_by_slug(conn, source_slug)
        if source is None:
            raise UnknownSourceError(f"No enabled source with slug '{source_slug}'")

        run_id = ingestion_runs.start_run(conn, source.id, datetime.now(timezone.utc))

    log_event(logger, "ingest.started", source=source_slug, run_id=run_id)

    counts = {"received": 0, "inserted": 0, "updated": 0, "unchanged": 0, "rejected": 0, "errors": 0}
    status = "succeeded"
    error_message: str | None = None

    try:
        collector = collector_factory(source.collector, source.config)

        for document in collector.collect(since=source.last_synced_at):
            counts["received"] += 1
            try:
                outcome = _store_document(engine, source.id, document)
                counts[outcome] += 1
            except Exception as exc:  # noqa: BLE001 - one bad row must not abort the run
                counts["rejected"] += 1
                counts["errors"] += 1
                log_event(
                    logger,
                    "ingest.document_rejected",
                    source=source_slug,
                    external_id=document.external_id,
                    error=str(exc),
                )
    except Exception as exc:
        status = "failed"
        error_message = str(exc)
        counts["errors"] += 1
        log_event(logger, "ingest.failed", source=source_slug, run_id=run_id, error=error_message)

    finished_at = datetime.now(timezone.utc)

    with engine.begin() as conn:
        ingestion_runs.finish_run(
            conn,
            run_id,
            finished_at=finished_at,
            status=status,
            records_received=counts["received"],
            records_inserted=counts["inserted"],
            records_updated=counts["updated"],
            records_rejected=counts["rejected"],
            error_count=counts["errors"],
            metadata={"error": error_message} if error_message else None,
        )
        if status == "succeeded":
            sources.mark_synced(conn, source.id, finished_at)

    log_event(logger, "ingest.finished", source=source_slug, run_id=run_id, status=status, **counts)

    return {"run_id": run_id, "status": status, **counts}


def _store_document(engine: Engine, source_id: int, document: CollectedDocument) -> str:
    content_hash = compute_content_hash(document.payload)

    with engine.begin() as conn:
        return raw_documents.upsert(
            conn,
            raw_documents.RawDocumentInput(
                source_id=source_id,
                external_id=document.external_id,
                content_hash=content_hash,
                collected_at=datetime.now(timezone.utc),
                url=document.url,
                title=document.title,
                body=document.body,
                published_at=document.published_at,
                language_raw=document.language_raw,
                region_raw=document.region_raw,
                metadata=document.payload,
            ),
        )
