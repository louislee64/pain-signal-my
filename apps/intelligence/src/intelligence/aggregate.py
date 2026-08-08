from datetime import date

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from intelligence.db import problem_signals_table
from intelligence.observability import get_logger, log_event
from intelligence.repositories import topic_daily_metrics

logger = get_logger("intelligence.aggregate")


def distinct_signal_dates(engine: Engine) -> list[date]:
    with engine.connect() as conn:
        rows = conn.execute(select(func.distinct(problem_signals_table.c.signal_date))).all()
    return sorted(row[0] for row in rows)


def aggregate_topic_daily_metrics(engine: Engine, target_date: date) -> int:
    with engine.begin() as conn:
        aggregates = topic_daily_metrics.compute_daily_aggregates(conn, target_date)
        for aggregate in aggregates:
            topic_daily_metrics.upsert(conn, aggregate)

    return len(aggregates)


def aggregate_all_topic_daily_metrics(engine: Engine) -> dict[str, int]:
    """Recompute topic_daily_metrics for every date that has problem_signals.
    Simple full recompute rather than tracking which dates are "dirty" —
    fine at today's data volume; revisit if this becomes slow."""

    dates = distinct_signal_dates(engine)
    total_rows = sum(aggregate_topic_daily_metrics(engine, d) for d in dates)

    log_event(logger, "aggregate.finished", dates=len(dates), rows=total_rows)
    return {"dates": len(dates), "rows": total_rows}
