import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.engine import Connection, Engine

from intelligence.language import detect_language
from intelligence.observability import get_logger, log_event
from intelligence.repositories import normalized_documents, sources
from intelligence.repositories.normalized_documents import NormalizedDocumentInput, RawDocumentRow

logger = get_logger("intelligence.normalize")

HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class NormalizeResult:
    document_id: int
    is_duplicate: bool


def clean_text(title: str | None, body: str | None) -> str:
    combined = " ".join(part for part in (title, body) if part)
    without_tags = HTML_TAG_PATTERN.sub(" ", combined)
    return WHITESPACE_PATTERN.sub(" ", without_tags).strip()


def compute_normalized_hash(cleaned_text: str) -> str:
    canonical = WHITESPACE_PATTERN.sub(" ", cleaned_text.strip().lower())
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_document(raw: RawDocumentRow, conn: Connection) -> NormalizeResult:
    cleaned_text = clean_text(raw.title, raw.body)
    language = detect_language(cleaned_text)
    content_hash = compute_normalized_hash(cleaned_text) if cleaned_text else None

    duplicate_of_id = normalized_documents.find_by_content_hash(conn, content_hash) if content_hash else None

    document_id = normalized_documents.upsert(
        conn,
        NormalizedDocumentInput(
            raw_document_id=raw.id,
            cleaned_text=cleaned_text or None,
            language=language,
            country="MY",
            state=raw.region_raw,
            city=None,
            normalized_content_hash=content_hash,
            processed_at=datetime.now(timezone.utc),
            duplicate_of_normalized_document_id=duplicate_of_id,
        ),
    )

    return NormalizeResult(document_id=document_id, is_duplicate=duplicate_of_id is not None)


def normalize_pending_documents(
    engine: Engine, *, batch_size: int = 500, source_slug: str | None = None
) -> dict[str, int]:
    counts = {"processed": 0, "duplicates": 0}

    with engine.begin() as conn:
        source_id = None
        if source_slug is not None:
            source = sources.get_enabled_source_by_slug(conn, source_slug)
            source_id = source.id if source else None

        pending = normalized_documents.get_unnormalized_raw_documents(
            conn, limit=batch_size, source_id=source_id
        )

    for raw in pending:
        with engine.begin() as conn:
            result = normalize_document(raw, conn)

        counts["processed"] += 1
        if result.is_duplicate:
            counts["duplicates"] += 1

    log_event(logger, "normalize.finished", **counts)
    return counts
