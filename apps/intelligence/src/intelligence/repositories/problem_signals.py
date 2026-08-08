from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection

from intelligence.db import problem_signals_table


@dataclass(frozen=True)
class ProblemSignalInput:
    document_id: int
    topic_id: int
    signal_date: date
    classification_method: str
    region: str | None = None
    severity_score: int | None = None
    urgency_score: int | None = None
    economic_impact_score: int | None = None
    frequency_hint: str | None = None
    payer_type: str | None = None
    evidence: dict[str, Any] | None = None


def upsert(conn: Connection, signal: ProblemSignalInput) -> None:
    existing = conn.execute(
        select(problem_signals_table.c.id)
        .where(problem_signals_table.c.document_id == signal.document_id)
        .where(problem_signals_table.c.topic_id == signal.topic_id)
        .where(problem_signals_table.c.classification_method == signal.classification_method)
    ).first()

    now = datetime.now(timezone.utc)
    values = {
        "signal_date": signal.signal_date,
        "region": signal.region,
        "severity_score": signal.severity_score,
        "urgency_score": signal.urgency_score,
        "economic_impact_score": signal.economic_impact_score,
        "frequency_hint": signal.frequency_hint,
        "payer_type": signal.payer_type,
        "evidence_json": signal.evidence or {},
        "updated_at": now,
    }

    if existing is not None:
        conn.execute(
            update(problem_signals_table).where(problem_signals_table.c.id == existing.id).values(**values)
        )
        return

    conn.execute(
        insert(problem_signals_table).values(
            document_id=signal.document_id,
            topic_id=signal.topic_id,
            classification_method=signal.classification_method,
            created_at=now,
            **values,
        )
    )
