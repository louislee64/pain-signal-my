from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, insert, select, update
from sqlalchemy.engine import Connection

from intelligence.db import (
    ai_usage_table,
    document_topics_table,
    normalized_documents_table,
    raw_documents_table,
)


@dataclass(frozen=True)
class RawDocumentRow:
    id: str
    source_id: int
    title: str | None
    body: str | None
    region_raw: str | None
    language_raw: str | None
    published_at: datetime | None
    collected_at: datetime


@dataclass(frozen=True)
class ClassifiableDocument:
    id: int
    cleaned_text: str
    state: str | None
    signal_date: date


@dataclass(frozen=True)
class ExtractableDocument:
    """A document eligible for LLM extraction. Carries `raw_document_id` on top
    of ClassifiableDocument's fields because that is the FK `ai_usage` records
    spend against."""

    id: int
    raw_document_id: str
    cleaned_text: str
    state: str | None
    signal_date: date


@dataclass(frozen=True)
class NormalizedDocumentInput:
    raw_document_id: str
    cleaned_text: str | None
    language: str | None
    country: str | None
    state: str | None
    city: str | None
    normalized_content_hash: str | None
    processed_at: datetime
    duplicate_of_normalized_document_id: int | None = None


def get_unnormalized_raw_documents(
    conn: Connection, limit: int = 500, source_id: int | None = None
) -> list[RawDocumentRow]:
    already_normalized = select(normalized_documents_table.c.raw_document_id)

    query = select(
        raw_documents_table.c.id,
        raw_documents_table.c.source_id,
        raw_documents_table.c.title,
        raw_documents_table.c.body,
        raw_documents_table.c.region_raw,
        raw_documents_table.c.language_raw,
        raw_documents_table.c.published_at,
        raw_documents_table.c.collected_at,
    ).where(raw_documents_table.c.id.notin_(already_normalized))

    if source_id is not None:
        query = query.where(raw_documents_table.c.source_id == source_id)

    rows = conn.execute(query.limit(limit)).all()

    return [
        RawDocumentRow(
            id=row.id,
            source_id=row.source_id,
            title=row.title,
            body=row.body,
            region_raw=row.region_raw,
            language_raw=row.language_raw,
            published_at=row.published_at,
            collected_at=row.collected_at,
        )
        for row in rows
    ]


def find_by_content_hash(conn: Connection, content_hash: str) -> int | None:
    row = conn.execute(
        select(normalized_documents_table.c.id).where(
            normalized_documents_table.c.normalized_content_hash == content_hash
        )
    ).first()
    return row.id if row else None


def get_unclassified_documents(
    conn: Connection,
    classification_method: str,
    limit: int = 500,
    source_id: int | None = None,
) -> list[ClassifiableDocument]:
    """Documents with no document_topics row yet under `classification_method`,
    newest first.

    The ordering is load-bearing, not cosmetic. A document that matches no
    keyword produces no row, so it stays in this result set permanently and is
    re-scanned on every run (see classify_and_extract_signals). With `LIMIT` and
    no `ORDER BY`, Postgres was free to return the same arbitrary 500
    never-matching rows forever — so once the unmatched backlog grew past the
    batch size, newly ingested documents could starve and never be classified at
    all. That went unnoticed while the only source was fuel prices, which match
    nothing by design; adding a text source made it reachable.

    Newest-first bounds the damage in the direction the product cares about:
    §26's scoring window is 30 days, so the recent end is the end that matters.
    The residual limitation is the honest one — an unmatched backlog deeper than
    `limit` never gets revisited — and it costs nothing, because those documents
    produce no signals by definition.
    """
    already_classified = select(document_topics_table.c.document_id).where(
        document_topics_table.c.classification_method == classification_method
    )

    signal_date = func.coalesce(raw_documents_table.c.published_at, raw_documents_table.c.collected_at)

    query = (
        select(
            normalized_documents_table.c.id,
            normalized_documents_table.c.cleaned_text,
            normalized_documents_table.c.state,
            signal_date.label("signal_date"),
        )
        .select_from(normalized_documents_table)
        .join(raw_documents_table, raw_documents_table.c.id == normalized_documents_table.c.raw_document_id)
        .where(normalized_documents_table.c.cleaned_text.isnot(None))
        .where(normalized_documents_table.c.id.notin_(already_classified))
    )

    if source_id is not None:
        query = query.where(raw_documents_table.c.source_id == source_id)

    # `id` breaks ties so the order is total, not merely mostly-determined:
    # a whole feed can share one signal_date, and an unstable tail would
    # reintroduce the starvation this ordering exists to prevent.
    rows = conn.execute(
        query.order_by(signal_date.desc(), normalized_documents_table.c.id.desc()).limit(limit)
    ).all()

    return [
        ClassifiableDocument(
            id=row.id,
            cleaned_text=row.cleaned_text,
            state=row.state,
            signal_date=row.signal_date.date(),
        )
        for row in rows
    ]


def get_documents_for_llm_extraction(
    conn: Connection,
    prompt_version: str,
    limit: int = 50,
    source_id: int | None = None,
    min_text_length: int = 0,
) -> list[ExtractableDocument]:
    """Documents not yet sent to the LLM under this prompt version (§24).

    "Already processed" is defined by the `ai_usage` ledger rather than by
    whether a signal came out, because most documents legitimately produce
    nothing — they mention no problem. Keying on produced-signals (the way the
    free rule-based path in process.py does) would re-send every such document
    on every run and pay for the same "problem_present: false" forever.

    Failed calls are deliberately NOT counted as processed: a transient API
    error should be retried, and its ai_usage row exists to record the spend,
    not to blacklist the document.
    """

    already_processed = select(ai_usage_table.c.document_id).where(
        ai_usage_table.c.prompt_version == prompt_version,
        ai_usage_table.c.succeeded.is_(True),
        ai_usage_table.c.document_id.isnot(None),
    )

    signal_date = func.coalesce(raw_documents_table.c.published_at, raw_documents_table.c.collected_at)

    query = (
        select(
            normalized_documents_table.c.id,
            normalized_documents_table.c.raw_document_id,
            normalized_documents_table.c.cleaned_text,
            normalized_documents_table.c.state,
            signal_date.label("signal_date"),
        )
        .select_from(normalized_documents_table)
        .join(raw_documents_table, raw_documents_table.c.id == normalized_documents_table.c.raw_document_id)
        .where(normalized_documents_table.c.cleaned_text.isnot(None))
        .where(func.length(normalized_documents_table.c.cleaned_text) >= min_text_length)
        # Never spend on a document already known to duplicate another (§21).
        .where(normalized_documents_table.c.duplicate_of_normalized_document_id.is_(None))
        .where(raw_documents_table.c.id.notin_(already_processed))
    )

    if source_id is not None:
        query = query.where(raw_documents_table.c.source_id == source_id)

    rows = conn.execute(query.limit(limit)).all()

    return [
        ExtractableDocument(
            id=row.id,
            raw_document_id=row.raw_document_id,
            cleaned_text=row.cleaned_text,
            state=row.state,
            signal_date=row.signal_date.date(),
        )
        for row in rows
    ]


def upsert(conn: Connection, document: NormalizedDocumentInput) -> int:
    existing = conn.execute(
        select(normalized_documents_table.c.id).where(
            normalized_documents_table.c.raw_document_id == document.raw_document_id
        )
    ).first()

    values = {
        "cleaned_text": document.cleaned_text,
        "language": document.language,
        "country": document.country,
        "state": document.state,
        "city": document.city,
        "normalized_content_hash": document.normalized_content_hash,
        "duplicate_of_normalized_document_id": document.duplicate_of_normalized_document_id,
        "processed_at": document.processed_at,
    }

    if existing is not None:
        conn.execute(
            update(normalized_documents_table)
            .where(normalized_documents_table.c.id == existing.id)
            .values(**values)
        )
        return existing.id

    result = conn.execute(
        insert(normalized_documents_table).values(
            raw_document_id=document.raw_document_id, **values
        )
    )
    return result.inserted_primary_key[0]
