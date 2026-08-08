from dataclasses import dataclass
from datetime import date, datetime, timezone

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection

from intelligence.db import trend_metrics_table
from intelligence.trends.metrics import Observation, TrendMetrics


@dataclass(frozen=True)
class TrendObservationInput:
    keyword_id: int
    observed_on: date
    interest: int
    country: str
    region: str
    collection_method: str
    collection_batch: str


def upsert_observation(conn: Connection, observation: TrendObservationInput) -> str:
    """Store one raw interest reading. Returns 'inserted' or 'updated'.

    Keyed on (keyword_id, date, region) so re-importing an overlapping CSV
    export refreshes those dates in place instead of duplicating the series.
    Derived metric columns are left untouched here — `compute` fills them in a
    second pass, because a rolling window can only be calculated once the whole
    series is present.
    """

    existing = conn.execute(
        select(trend_metrics_table.c.id)
        .where(trend_metrics_table.c.keyword_id == observation.keyword_id)
        .where(trend_metrics_table.c.date == observation.observed_on)
        .where(trend_metrics_table.c.region == observation.region)
    ).first()

    now = datetime.now(timezone.utc)

    if existing is not None:
        conn.execute(
            update(trend_metrics_table)
            .where(trend_metrics_table.c.id == existing.id)
            .values(
                interest=observation.interest,
                country=observation.country,
                collection_method=observation.collection_method,
                collection_batch=observation.collection_batch,
                updated_at=now,
            )
        )
        return "updated"

    conn.execute(
        insert(trend_metrics_table).values(
            keyword_id=observation.keyword_id,
            date=observation.observed_on,
            country=observation.country,
            region=observation.region,
            interest=observation.interest,
            collection_method=observation.collection_method,
            collection_batch=observation.collection_batch,
            created_at=now,
            updated_at=now,
        )
    )
    return "inserted"


def get_series(conn: Connection, keyword_id: int, region: str = "") -> list[Observation]:
    rows = conn.execute(
        select(trend_metrics_table.c.date, trend_metrics_table.c.interest)
        .where(trend_metrics_table.c.keyword_id == keyword_id)
        .where(trend_metrics_table.c.region == region)
        .order_by(trend_metrics_table.c.date)
    ).all()

    return [Observation(observed_on=row.date, interest=row.interest) for row in rows]


def distinct_series_keys(conn: Connection) -> list[tuple[int, str]]:
    rows = conn.execute(
        select(trend_metrics_table.c.keyword_id, trend_metrics_table.c.region).distinct()
    ).all()
    return [(row.keyword_id, row.region) for row in rows]


def store_metrics(
    conn: Connection, keyword_id: int, region: str, observed_on: date, metrics: TrendMetrics
) -> None:
    conn.execute(
        update(trend_metrics_table)
        .where(trend_metrics_table.c.keyword_id == keyword_id)
        .where(trend_metrics_table.c.region == region)
        .where(trend_metrics_table.c.date == observed_on)
        .values(
            rolling_7d=metrics.rolling_7d,
            rolling_30d=metrics.rolling_30d,
            baseline_90d=metrics.baseline_90d,
            growth_7d=metrics.growth_7d,
            growth_30d=metrics.growth_30d,
            growth_score=metrics.growth_score,
            z_score=metrics.z_score,
            updated_at=datetime.now(timezone.utc),
        )
    )
