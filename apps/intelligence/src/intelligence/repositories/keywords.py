from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import insert, select
from sqlalchemy.engine import Connection

from intelligence.db import keywords_table

SOURCE_CONFIG = "config"
SOURCE_DISCOVERED = "discovered"


@dataclass(frozen=True)
class KeywordRecord:
    id: int
    keyword: str
    keyword_group: str
    language: str | None
    geo: str


def get_enabled_keywords(conn: Connection) -> list[KeywordRecord]:
    rows = conn.execute(
        select(
            keywords_table.c.id,
            keywords_table.c.keyword,
            keywords_table.c.keyword_group,
            keywords_table.c.language,
            keywords_table.c.geo,
        ).where(keywords_table.c.enabled.is_(True))
    ).all()

    return [
        KeywordRecord(
            id=row.id,
            keyword=row.keyword,
            keyword_group=row.keyword_group,
            language=row.language,
            geo=row.geo,
        )
        for row in rows
    ]


def find_by_keyword(conn: Connection, keyword: str, geo: str) -> KeywordRecord | None:
    row = conn.execute(
        select(
            keywords_table.c.id,
            keywords_table.c.keyword,
            keywords_table.c.keyword_group,
            keywords_table.c.language,
            keywords_table.c.geo,
        )
        .where(keywords_table.c.keyword == keyword)
        .where(keywords_table.c.geo == geo)
    ).first()

    if row is None:
        return None

    return KeywordRecord(
        id=row.id,
        keyword=row.keyword,
        keyword_group=row.keyword_group,
        language=row.language,
        geo=row.geo,
    )


def create_discovered_keyword(conn: Connection, keyword: str, geo: str, keyword_group: str) -> int:
    """Register a term surfaced by a discovery provider (§15A).

    Marked `source='discovered'` so `php artisan keywords:sync` leaves it alone —
    it was never in config/keywords.yaml, so its absence from that file must not
    be read as "removed".
    """

    now = datetime.now(timezone.utc)
    result = conn.execute(
        insert(keywords_table).values(
            keyword=keyword,
            keyword_group=keyword_group,
            language=None,
            geo=geo,
            source=SOURCE_DISCOVERED,
            enabled=True,
            created_at=now,
            updated_at=now,
        )
    )
    return result.inserted_primary_key[0]
