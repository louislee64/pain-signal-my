from sqlalchemy.engine import Engine

from intelligence.classify import CLASSIFICATION_METHOD, classify_text
from intelligence.observability import get_logger, log_event
from intelligence.repositories import document_topics, normalized_documents, problem_signals, sources, topics
from intelligence.repositories.document_topics import DocumentTopicInput
from intelligence.repositories.problem_signals import ProblemSignalInput
from intelligence.signals import extract_signal

logger = get_logger("intelligence.process")


def classify_and_extract_signals(
    engine: Engine, *, batch_size: int = 500, source_slug: str | None = None
) -> dict[str, int]:
    """For every normalized document with no document_topics row yet under
    CLASSIFICATION_METHOD, match it against the taxonomy and store one
    problem_signals row per matched topic. A document with zero keyword
    matches produces no rows, so — unlike matched documents — it will be
    re-scanned on every run; acceptable since rule-based matching is cheap
    (no LLM cost), unlike the extraction this stands in for (§24)."""

    counts = {"documents": 0, "topic_matches": 0}

    with engine.begin() as conn:
        source_id = None
        if source_slug is not None:
            source = sources.get_enabled_source_by_slug(conn, source_slug)
            source_id = source.id if source else None

        pending = normalized_documents.get_unclassified_documents(
            conn, CLASSIFICATION_METHOD, limit=batch_size, source_id=source_id
        )
        topic_by_slug = topics.get_enabled_topics_by_slug(conn)

    for document in pending:
        matches = classify_text(document.cleaned_text)
        signal = extract_signal(document.cleaned_text)
        counts["documents"] += 1

        with engine.begin() as conn:
            for match in matches:
                topic = topic_by_slug.get(match.topic_slug)
                if topic is None:
                    log_event(logger, "process.unknown_topic_slug", slug=match.topic_slug)
                    continue

                document_topics.upsert(
                    conn,
                    DocumentTopicInput(
                        document_id=document.id,
                        topic_id=topic.id,
                        confidence=match.confidence,
                        classification_method=CLASSIFICATION_METHOD,
                    ),
                )

                problem_signals.upsert(
                    conn,
                    ProblemSignalInput(
                        document_id=document.id,
                        topic_id=topic.id,
                        signal_date=document.signal_date,
                        classification_method=CLASSIFICATION_METHOD,
                        region=document.state,
                        severity_score=signal.severity_score,
                        urgency_score=signal.urgency_score,
                        economic_impact_score=signal.economic_impact_score,
                        frequency_hint=signal.frequency_hint,
                        payer_type=signal.payer_type,
                        evidence={
                            **signal.evidence,
                            "matched_topic_keywords": list(match.matched_keywords),
                        },
                    ),
                )
                counts["topic_matches"] += 1

    log_event(logger, "process.finished", **counts)
    return counts
