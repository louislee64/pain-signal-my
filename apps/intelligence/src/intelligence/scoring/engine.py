"""Opportunity engine — score every topic and persist an explainable result.

Milestone 4's acceptance criterion is "Each opportunity is explainable through
stored evidence", so every run writes the full score breakdown alongside the
headline numbers, plus the config version that produced them.
"""

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Engine

from intelligence.db import get_engine, opportunities_table, topics_table
from intelligence.observability import get_logger, log_event
from intelligence.scoring.config import ScoringConfig, get_scoring_config
from intelligence.scoring.measurements import gather_measurements
from intelligence.scoring.model import OpportunityScores, score_opportunity

logger = get_logger("intelligence.scoring")

# §3's funnel starts here. The engine only ever writes this on FIRST creation —
# §52 is explicit that a human promotes an opportunity through the funnel, so a
# rescoring run must never move a status a person has advanced.
INITIAL_STATUS = "observed"


def score_all_topics(
    engine: Engine | None = None,
    *,
    config: ScoringConfig | None = None,
    as_of: date | None = None,
) -> dict[str, Any]:
    engine = engine or get_engine()
    config = config or get_scoring_config()
    as_of = as_of or datetime.now(timezone.utc).date()

    with engine.begin() as conn:
        measurements = gather_measurements(conn, config, as_of)
        topic_names = {
            row.id: row.name for row in conn.execute(select(topics_table.c.id, topics_table.c.name)).all()
        }

    counts = {"scored": 0, "created": 0, "updated": 0}

    for topic_id, m in measurements.items():
        scores = score_opportunity(m, config, as_of)
        outcome = _persist(engine, topic_id, topic_names.get(topic_id, m.topic_slug), scores, config)

        counts["scored"] += 1
        counts[outcome] += 1

    log_event(logger, "scoring.finished", as_of=as_of, **counts)
    return {"as_of": as_of.isoformat(), **counts}


def _persist(
    engine: Engine,
    topic_id: int,
    topic_name: str,
    scores: OpportunityScores,
    config: ScoringConfig,
) -> str:
    now = datetime.now(timezone.utc)

    values = {
        "pain_score": round(scores.pain.score, 2),
        "commercial_score": round(scores.commercial.score, 2),
        "opportunity_score": round(scores.opportunity.score, 2),
        "confidence_score": round(scores.confidence.score, 2),
        "recommendation": scores.recommendation,
        "score_components": scores.to_dict(),
        "scoring_config_version": config.version,
        "scored_at": now,
        "updated_at": now,
    }

    with engine.begin() as conn:
        existing = conn.execute(
            select(opportunities_table.c.id).where(opportunities_table.c.topic_id == topic_id)
        ).first()

        if existing is not None:
            # Note what is NOT updated: status, title, and the human-authored
            # narrative fields (problem_statement, existing_workaround,
            # possible_solution, monetization_model). Rescoring refreshes
            # machine-derived numbers only — overwriting a human's funnel
            # decision or written analysis on a nightly run would be a
            # data-loss bug wearing the costume of a feature (§52).
            conn.execute(
                update(opportunities_table)
                .where(opportunities_table.c.id == existing.id)
                .values(**values)
            )
            return "updated"

        conn.execute(
            insert(opportunities_table).values(
                topic_id=topic_id,
                title=topic_name,
                status=INITIAL_STATUS,
                created_at=now,
                **values,
            )
        )
        return "created"
