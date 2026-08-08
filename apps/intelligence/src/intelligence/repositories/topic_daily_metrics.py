from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, insert, select, update
from sqlalchemy.engine import Connection

from intelligence.db import (
    normalized_documents_table,
    problem_signals_table,
    raw_documents_table,
    topic_daily_metrics_table,
)


@dataclass(frozen=True)
class DailyAggregate:
    signal_date: date
    topic_id: int
    region: str
    mention_count: int
    source_count: int
    avg_severity: Decimal | None
    avg_urgency: Decimal | None


def compute_daily_aggregates(conn: Connection, target_date: date) -> list[DailyAggregate]:
    region = func.coalesce(problem_signals_table.c.region, "")

    query = (
        select(
            problem_signals_table.c.signal_date,
            problem_signals_table.c.topic_id,
            region.label("region"),
            func.count(problem_signals_table.c.id).label("mention_count"),
            func.count(func.distinct(raw_documents_table.c.source_id)).label("source_count"),
            func.avg(problem_signals_table.c.severity_score).label("avg_severity"),
            func.avg(problem_signals_table.c.urgency_score).label("avg_urgency"),
        )
        .select_from(problem_signals_table)
        .join(
            normalized_documents_table,
            normalized_documents_table.c.id == problem_signals_table.c.document_id,
        )
        .join(
            raw_documents_table,
            raw_documents_table.c.id == normalized_documents_table.c.raw_document_id,
        )
        .where(problem_signals_table.c.signal_date == target_date)
        .group_by(problem_signals_table.c.signal_date, problem_signals_table.c.topic_id, region)
    )

    return [
        DailyAggregate(
            signal_date=row.signal_date,
            topic_id=row.topic_id,
            region=row.region,
            mention_count=row.mention_count,
            source_count=row.source_count,
            avg_severity=row.avg_severity,
            avg_urgency=row.avg_urgency,
        )
        for row in conn.execute(query).all()
    ]


def upsert(conn: Connection, aggregate: DailyAggregate) -> None:
    existing = conn.execute(
        select(topic_daily_metrics_table.c.id)
        .where(topic_daily_metrics_table.c.date == aggregate.signal_date)
        .where(topic_daily_metrics_table.c.topic_id == aggregate.topic_id)
        .where(topic_daily_metrics_table.c.region == aggregate.region)
    ).first()

    now = datetime.now(timezone.utc)
    values = {
        "mention_count": aggregate.mention_count,
        "source_count": aggregate.source_count,
        "avg_severity": aggregate.avg_severity,
        "avg_urgency": aggregate.avg_urgency,
        "updated_at": now,
    }

    if existing is not None:
        conn.execute(
            update(topic_daily_metrics_table)
            .where(topic_daily_metrics_table.c.id == existing.id)
            .values(**values)
        )
        return

    conn.execute(
        insert(topic_daily_metrics_table).values(
            date=aggregate.signal_date,
            topic_id=aggregate.topic_id,
            region=aggregate.region,
            created_at=now,
            **values,
        )
    )
