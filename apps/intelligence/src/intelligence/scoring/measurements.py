"""Gather the measurements the scoring model needs, from Milestone 1-3 data.

Kept separate from scoring/model.py on purpose: how a number is *measured* and
how it is *scored* change for completely different reasons, and the scoring
arithmetic must stay testable without a database.

Commercial figures come from scoring/commercial.py, which reads §21's CRM
tables. They are zero for any topic nobody has investigated, and §29's cap keeps
those honest: an opportunity with no human validation cannot present as a
certainty however good its inferred signals look.
"""

from datetime import date, timedelta

from sqlalchemy import Date, and_, cast, func, select
from sqlalchemy.engine import Connection

from intelligence.db import (
    document_topics_table,
    keywords_table,
    normalized_documents_table,
    problem_signals_table,
    raw_documents_table,
    topics_table,
    trend_metrics_table,
)
from intelligence.scoring.commercial import (
    CommercialEvidenceCounts,
    gather_commercial_evidence,
)
from intelligence.scoring.config import ScoringConfig
from intelligence.scoring.model import TopicMeasurements


def _signal_base(window_start: date, window_end: date):
    return (
        select(problem_signals_table.c.topic_id)
        .where(problem_signals_table.c.signal_date >= window_start)
        .where(problem_signals_table.c.signal_date <= window_end)
    )


def gather_measurements(
    conn: Connection, config: ScoringConfig, as_of: date
) -> dict[int, TopicMeasurements]:
    """One TopicMeasurements per topic that has any signal in the current window."""

    window_days = config.window_days()
    window_start = as_of - timedelta(days=window_days - 1)
    previous_start = window_start - timedelta(days=window_days)
    previous_end = window_start - timedelta(days=1)

    topics = {
        row.id: (row.slug, row.parent_slug)
        for row in conn.execute(_topics_with_parent_slug()).all()
    }

    current = _aggregate_window(conn, window_start, as_of)
    previous = _previous_counts(conn, previous_start, previous_end)
    search = _search_interest_by_topic(conn, config, as_of)

    # §21's human evidence. Read once for every topic rather than per topic:
    # this is the one input to the score that a person had to go out and earn,
    # and it is cheap to fetch in bulk.
    commercial = gather_commercial_evidence(conn)
    no_evidence = CommercialEvidenceCounts()

    measurements: dict[int, TopicMeasurements] = {}

    for topic_id, agg in current.items():
        slug, parent_slug = topics.get(topic_id, (str(topic_id), None))
        human = commercial.get(topic_id, no_evidence)

        measurements[topic_id] = TopicMeasurements(
            topic_slug=slug,
            parent_slug=parent_slug,
            mention_count=agg["mention_count"],
            previous_mention_count=previous.get(topic_id, 0),
            avg_severity=agg["avg_severity"],
            distinct_regions=agg["distinct_regions"],
            search_growth_score=search.get(slug),
            signals_with_payer=agg["signals_with_payer"],
            dominant_frequency_hint=agg["dominant_frequency_hint"],
            avg_economic_impact=agg["avg_economic_impact"],
            avg_urgency=agg["avg_urgency"],
            distinct_sources=agg["distinct_sources"],
            avg_classification_confidence=agg["avg_classification_confidence"],
            latest_signal_date=agg["latest_signal_date"],
            interview_count=human.interview_count,
            problem_confirmed_count=human.problem_confirmed_count,
            independent_confirmations=human.independent_confirmations,
            paid_pilot_count=human.paid_pilot_count,
            paying_business_count=human.paying_business_count,
            has_strong_buyer_signal=human.has_strong_buyer_signal,
        )

    return measurements


def _topics_with_parent_slug():
    parent = topics_table.alias("parent")
    return select(
        topics_table.c.id,
        topics_table.c.slug,
        parent.c.slug.label("parent_slug"),
    ).select_from(topics_table.outerjoin(parent, topics_table.c.parent_id == parent.c.id))


def _aggregate_window(conn: Connection, window_start: date, window_end: date) -> dict[int, dict]:
    """Per-topic aggregates over the scoring window.

    Joins out to raw_documents so `distinct_sources` counts genuinely
    independent SOURCES rather than documents — §31 ranks "multiple independent
    companies reporting" far above "multiple posts", and counting documents
    would let one chatty source impersonate corroboration.
    """

    rows = conn.execute(
        select(
            problem_signals_table.c.topic_id,
            func.count(problem_signals_table.c.id).label("mention_count"),
            func.avg(problem_signals_table.c.severity_score).label("avg_severity"),
            func.avg(problem_signals_table.c.economic_impact_score).label("avg_economic_impact"),
            func.avg(problem_signals_table.c.urgency_score).label("avg_urgency"),
            func.count(func.distinct(problem_signals_table.c.region)).label("distinct_regions"),
            func.count(func.distinct(raw_documents_table.c.source_id)).label("distinct_sources"),
            func.count(problem_signals_table.c.payer_type).label("signals_with_payer"),
            func.max(problem_signals_table.c.signal_date).label("latest_signal_date"),
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
        .where(problem_signals_table.c.signal_date >= window_start)
        .where(problem_signals_table.c.signal_date <= window_end)
        .group_by(problem_signals_table.c.topic_id)
    ).all()

    confidence = _classification_confidence(conn, window_start, window_end)
    frequency = _dominant_frequency_hint(conn, window_start, window_end)

    return {
        row.topic_id: {
            "mention_count": row.mention_count,
            "avg_severity": float(row.avg_severity) if row.avg_severity is not None else None,
            "avg_economic_impact": (
                float(row.avg_economic_impact) if row.avg_economic_impact is not None else None
            ),
            "avg_urgency": float(row.avg_urgency) if row.avg_urgency is not None else None,
            "distinct_regions": row.distinct_regions,
            "distinct_sources": row.distinct_sources,
            "signals_with_payer": row.signals_with_payer,
            "latest_signal_date": row.latest_signal_date,
            "avg_classification_confidence": confidence.get(row.topic_id),
            "dominant_frequency_hint": frequency.get(row.topic_id),
        }
        for row in rows
    }


def _previous_counts(conn: Connection, start: date, end: date) -> dict[int, int]:
    rows = conn.execute(
        select(
            problem_signals_table.c.topic_id,
            func.count(problem_signals_table.c.id).label("mention_count"),
        )
        .where(problem_signals_table.c.signal_date >= start)
        .where(problem_signals_table.c.signal_date <= end)
        .group_by(problem_signals_table.c.topic_id)
    ).all()
    return {row.topic_id: row.mention_count for row in rows}


def _classification_confidence(conn: Connection, start: date, end: date) -> dict[int, float]:
    rows = conn.execute(
        select(
            document_topics_table.c.topic_id,
            func.avg(document_topics_table.c.confidence).label("avg_confidence"),
        )
        .select_from(document_topics_table)
        .join(
            problem_signals_table,
            and_(
                problem_signals_table.c.document_id == document_topics_table.c.document_id,
                problem_signals_table.c.topic_id == document_topics_table.c.topic_id,
            ),
        )
        .where(problem_signals_table.c.signal_date >= start)
        .where(problem_signals_table.c.signal_date <= end)
        .group_by(document_topics_table.c.topic_id)
    ).all()
    return {row.topic_id: float(row.avg_confidence) for row in rows if row.avg_confidence is not None}


def _dominant_frequency_hint(conn: Connection, start: date, end: date) -> dict[int, str]:
    """The most common non-null frequency_hint per topic.

    Modal rather than averaged: "daily" and "monthly" have no meaningful
    midpoint, and taking the most frequently observed cadence is the only
    honest summary of a categorical field.
    """

    rows = conn.execute(
        select(
            problem_signals_table.c.topic_id,
            problem_signals_table.c.frequency_hint,
            func.count(problem_signals_table.c.id).label("hits"),
        )
        .where(problem_signals_table.c.signal_date >= start)
        .where(problem_signals_table.c.signal_date <= end)
        .where(problem_signals_table.c.frequency_hint.isnot(None))
        .group_by(problem_signals_table.c.topic_id, problem_signals_table.c.frequency_hint)
        .order_by(problem_signals_table.c.topic_id, func.count(problem_signals_table.c.id).desc())
    ).all()

    dominant: dict[int, str] = {}
    for row in rows:
        dominant.setdefault(row.topic_id, row.frequency_hint)
    return dominant


def _search_interest_by_topic(
    conn: Connection, config: ScoringConfig, as_of: date
) -> dict[str, float]:
    """Latest Google Trends growth_score per topic, via the configured
    topic -> keyword-group map."""

    topic_map = config.raw.get("search_interest_topic_map") or {}
    if not topic_map:
        return {}

    groups = set(topic_map.values())

    # Only the most recent reading per keyword matters for "is this rising
    # now" — older points already shaped the baseline that growth_score divides
    # by. Expressed as a grouped-max join rather than a correlated subquery:
    # the correlated form auto-correlates both tables away and compiles to a
    # SELECT with no FROM clause.
    latest = (
        select(
            trend_metrics_table.c.keyword_id,
            func.max(trend_metrics_table.c.date).label("max_date"),
        )
        .group_by(trend_metrics_table.c.keyword_id)
        .subquery()
    )

    rows = conn.execute(
        select(
            keywords_table.c.keyword_group,
            func.avg(trend_metrics_table.c.growth_score).label("avg_growth"),
        )
        .select_from(trend_metrics_table)
        .join(
            latest,
            and_(
                latest.c.keyword_id == trend_metrics_table.c.keyword_id,
                latest.c.max_date == trend_metrics_table.c.date,
            ),
        )
        .join(keywords_table, keywords_table.c.id == trend_metrics_table.c.keyword_id)
        .where(keywords_table.c.keyword_group.in_(groups))
        .where(keywords_table.c.enabled.is_(True))
        .where(trend_metrics_table.c.growth_score.isnot(None))
        .group_by(keywords_table.c.keyword_group)
    ).all()

    by_group = {row.keyword_group: float(row.avg_growth) for row in rows}

    return {
        topic_slug: by_group[group]
        for topic_slug, group in topic_map.items()
        if group in by_group
    }
