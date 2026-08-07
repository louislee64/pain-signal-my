from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from ulid import ULID
from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection

from intelligence.db import raw_documents_table

UpsertOutcome = Literal["inserted", "updated", "unchanged"]


@dataclass(frozen=True)
class RawDocumentInput:
    source_id: int
    external_id: str
    content_hash: str
    collected_at: datetime
    url: str | None = None
    title: str | None = None
    body: str | None = None
    published_at: datetime | None = None
    language_raw: str | None = None
    region_raw: str | None = None
    metadata: dict[str, Any] | None = None


def upsert(conn: Connection, document: RawDocumentInput) -> UpsertOutcome:
    """Insert a new raw document, or update it in place if the source has
    republished a different value for the same natural key. Raw documents
    are otherwise treated as an immutable log (see docs/data-model.md for
    why an in-place update is still considered part of "raw" here)."""

    existing = conn.execute(
        select(raw_documents_table.c.id, raw_documents_table.c.content_hash)
        .where(raw_documents_table.c.source_id == document.source_id)
        .where(raw_documents_table.c.external_id == document.external_id)
    ).first()

    if existing is None:
        conn.execute(
            insert(raw_documents_table).values(
                id=str(ULID()),
                source_id=document.source_id,
                external_id=document.external_id,
                url=document.url,
                title=document.title,
                body=document.body,
                published_at=document.published_at,
                collected_at=document.collected_at,
                content_hash=document.content_hash,
                language_raw=document.language_raw,
                region_raw=document.region_raw,
                metadata_json=document.metadata or {},
                created_at=document.collected_at,
            )
        )
        return "inserted"

    if existing.content_hash == document.content_hash:
        return "unchanged"

    conn.execute(
        update(raw_documents_table)
        .where(raw_documents_table.c.id == existing.id)
        .values(
            url=document.url,
            title=document.title,
            body=document.body,
            published_at=document.published_at,
            collected_at=document.collected_at,
            content_hash=document.content_hash,
            language_raw=document.language_raw,
            region_raw=document.region_raw,
            metadata_json=document.metadata or {},
        )
    )
    return "updated"
