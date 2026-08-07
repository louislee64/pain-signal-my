from datetime import datetime
from typing import Any

from sqlalchemy import insert, update
from sqlalchemy.engine import Connection

from intelligence.db import ingestion_runs_table


def start_run(conn: Connection, source_id: int, started_at: datetime) -> int:
    result = conn.execute(
        insert(ingestion_runs_table).values(
            source_id=source_id,
            started_at=started_at,
            status="running",
            records_received=0,
            records_inserted=0,
            records_updated=0,
            records_rejected=0,
            error_count=0,
        )
    )
    return result.inserted_primary_key[0]


def finish_run(
    conn: Connection,
    run_id: int,
    *,
    finished_at: datetime,
    status: str,
    records_received: int,
    records_inserted: int,
    records_updated: int,
    records_rejected: int,
    error_count: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    conn.execute(
        update(ingestion_runs_table)
        .where(ingestion_runs_table.c.id == run_id)
        .values(
            finished_at=finished_at,
            status=status,
            records_received=records_received,
            records_inserted=records_inserted,
            records_updated=records_updated,
            records_rejected=records_rejected,
            error_count=error_count,
            metadata_json=metadata or {},
        )
    )
