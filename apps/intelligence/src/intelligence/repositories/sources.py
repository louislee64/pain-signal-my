from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.engine import Connection

from intelligence.db import sources_table


def _as_utc(value: datetime | None) -> datetime | None:
    """Label a timestamp read from Postgres as UTC.

    The schema is owned by Laravel migrations, which create `timestamp(0)`
    columns — `timestamp WITHOUT time zone`. SQLAlchemy declares them
    `DateTime(timezone=True)` but cannot invent an offset the database does not
    store, so every timestamp arrives naive while everything this codebase writes
    is `datetime.now(timezone.utc)`. The values are UTC; only the label is
    missing.

    Restoring it here rather than at each call site is the difference between one
    correct conversion and a trap. `since` is handed straight to collectors, and
    a collector that compares it against a parsed feed date raised
    "can't compare offset-naive and offset-aware datetimes" — but only on the
    SECOND run, because the first has no last_successful_sync to compare with.
    A first run that always works is the worst possible place to hide this.
    """
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class SourceRecord:
    id: int
    slug: str
    collector: str
    config: dict[str, Any]
    enabled: bool
    last_synced_at: datetime | None

    # §38's conditional-fetch validators, as the source last reported them.
    etag: str | None = None
    last_modified: str | None = None
    dataset_version: str | None = None
    last_successful_sync: datetime | None = None


def get_enabled_source_by_slug(conn: Connection, slug: str) -> SourceRecord | None:
    row = conn.execute(
        select(
            sources_table.c.id,
            sources_table.c.slug,
            sources_table.c.collector,
            sources_table.c.config,
            sources_table.c.enabled,
            sources_table.c.last_synced_at,
            sources_table.c.etag,
            sources_table.c.last_modified,
            sources_table.c.dataset_version,
            sources_table.c.last_successful_sync,
        ).where(sources_table.c.slug == slug)
    ).first()

    if row is None or not row.enabled:
        return None

    return SourceRecord(
        id=row.id,
        slug=row.slug,
        collector=row.collector,
        config=row.config or {},
        enabled=row.enabled,
        last_synced_at=_as_utc(row.last_synced_at),
        etag=row.etag,
        last_modified=row.last_modified,
        dataset_version=row.dataset_version,
        last_successful_sync=_as_utc(row.last_successful_sync),
    )


def mark_synced(
    conn: Connection,
    source_id: int,
    synced_at: datetime,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
    dataset_version: str | None = None,
    received_data: bool = True,
) -> None:
    """Record that we talked to this source (§38).

    `last_synced_at` always moves — it answers "when did we last try". Only
    `last_successful_sync` is gated on `received_data`, so a source that has been
    answering 304 for a month does not look like one that has been delivering
    fresh data for a month.

    Validators are only overwritten when the source supplied one. A server that
    stops sending ETags should not cause us to forget the last good validator and
    silently drop back to unconditional requests.
    """

    values: dict[str, Any] = {"last_synced_at": synced_at, "updated_at": synced_at}

    if etag is not None:
        values["etag"] = etag
    if last_modified is not None:
        values["last_modified"] = last_modified
    if dataset_version is not None:
        values["dataset_version"] = dataset_version
    if received_data:
        values["last_successful_sync"] = synced_at

    conn.execute(update(sources_table).where(sources_table.c.id == source_id).values(**values))
