from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.engine import Connection

from intelligence.db import topics_table


@dataclass(frozen=True)
class TopicRecord:
    id: int
    slug: str
    parent_id: int | None


def get_enabled_topics_by_slug(conn: Connection) -> dict[str, TopicRecord]:
    rows = conn.execute(
        select(topics_table.c.id, topics_table.c.slug, topics_table.c.parent_id).where(
            topics_table.c.enabled.is_(True)
        )
    ).all()

    return {
        row.slug: TopicRecord(id=row.id, slug=row.slug, parent_id=row.parent_id)
        for row in rows
    }
