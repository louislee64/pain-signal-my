from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection

from intelligence.db import document_topics_table


@dataclass(frozen=True)
class DocumentTopicInput:
    document_id: int
    topic_id: int
    confidence: int
    classification_method: str
    model_version: str | None = None


def upsert(conn: Connection, assignment: DocumentTopicInput) -> None:
    existing = conn.execute(
        select(document_topics_table.c.id)
        .where(document_topics_table.c.document_id == assignment.document_id)
        .where(document_topics_table.c.topic_id == assignment.topic_id)
        .where(document_topics_table.c.classification_method == assignment.classification_method)
    ).first()

    now = datetime.now(timezone.utc)

    if existing is not None:
        conn.execute(
            update(document_topics_table)
            .where(document_topics_table.c.id == existing.id)
            .values(confidence=assignment.confidence, model_version=assignment.model_version, updated_at=now)
        )
        return

    conn.execute(
        insert(document_topics_table).values(
            document_id=assignment.document_id,
            topic_id=assignment.topic_id,
            confidence=assignment.confidence,
            classification_method=assignment.classification_method,
            model_version=assignment.model_version,
            created_at=now,
            updated_at=now,
        )
    )
