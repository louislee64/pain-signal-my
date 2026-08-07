from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.engine import Connection

from intelligence.db import sources_table


@dataclass(frozen=True)
class SourceRecord:
    id: int
    slug: str
    collector: str
    config: dict[str, Any]
    enabled: bool
    last_synced_at: datetime | None


def get_enabled_source_by_slug(conn: Connection, slug: str) -> SourceRecord | None:
    row = conn.execute(
        select(
            sources_table.c.id,
            sources_table.c.slug,
            sources_table.c.collector,
            sources_table.c.config,
            sources_table.c.enabled,
            sources_table.c.last_synced_at,
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
        last_synced_at=row.last_synced_at,
    )


def mark_synced(conn: Connection, source_id: int, synced_at: datetime) -> None:
    conn.execute(
        update(sources_table)
        .where(sources_table.c.id == source_id)
        .values(last_synced_at=synced_at, updated_at=synced_at)
    )
