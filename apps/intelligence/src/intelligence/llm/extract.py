"""LLM extraction pipeline (PROJECT_SPEC.md §24).

Reads normalized documents, asks a provider what problem each describes, and
writes the result as `problem_signals` rows under its own classification method
so LLM output sits alongside rule-based output without either overwriting the
other. The scoring engine then reads both.

Every guard in this file exists because this is the first code path in the
project that spends money per document:

- extraction is off unless config/llm.yaml says `enabled: true`
- the budget is checked before each call, not after the run
- usage is recorded whether the call succeeded or failed
- documents already paid for under this prompt version are never re-sent
- a run is capped at `max_documents_per_run` regardless of budget
"""

from dataclasses import dataclass

from sqlalchemy.engine import Engine

from intelligence.llm.base import PROMPT_VERSION, LLMProvider, LLMProviderError
from intelligence.llm.registry import build_llm_provider
from intelligence.llm.schemas import ExtractionResult
from intelligence.llm.usage import (
    BudgetExceededError,
    LLMConfig,
    check_budget,
    load_llm_config,
    record_usage,
)
from intelligence.observability import get_logger, log_event
from intelligence.repositories import document_topics, normalized_documents, sources, topics
from intelligence.repositories.document_topics import DocumentTopicInput
from intelligence.repositories.problem_signals import ProblemSignalInput, upsert as upsert_signal
from intelligence.taxonomy import load_taxonomy_hint

logger = get_logger("intelligence.llm.extract")

OPERATION = "extract_problem"

# Distinct from CLASSIFICATION_METHOD in classify.py. Both methods can classify
# the same document into the same topic; keeping them apart means the scoring
# engine can tell "a keyword matched" from "a model read it and agreed", and
# means re-running one never destroys the other's rows.
EXTRACTION_METHOD = f"llm_{PROMPT_VERSION}"


@dataclass
class ExtractionRun:
    documents_seen: int = 0
    extracted: int = 0
    no_problem: int = 0
    low_confidence: int = 0
    unknown_topic: int = 0
    failed: int = 0
    stopped_reason: str | None = None
    estimated_cost: float = 0.0

    def as_dict(self) -> dict:
        return {
            "documents_seen": self.documents_seen,
            "extracted": self.extracted,
            "no_problem": self.no_problem,
            "low_confidence": self.low_confidence,
            "unknown_topic": self.unknown_topic,
            "failed": self.failed,
            "stopped_reason": self.stopped_reason,
            "estimated_cost": round(self.estimated_cost, 6),
        }


def _persist(
    engine: Engine,
    document: normalized_documents.ExtractableDocument,
    result: ExtractionResult,
    topic_by_slug: dict,
    run: ExtractionRun,
    min_confidence: float,
) -> None:
    extraction = result.extraction

    if not extraction.problem_present:
        run.no_problem += 1
        return

    if extraction.confidence < min_confidence:
        # Recorded as seen and paid for, but no signal written: a low-confidence
        # extraction entering the evidence base would be indistinguishable from
        # a confident one once it is a row.
        run.low_confidence += 1
        log_event(
            logger,
            "llm.extract.low_confidence",
            document_id=document.id,
            confidence=extraction.confidence,
        )
        return

    # Prefer the subtopic: it is the more specific claim, and topics.yaml nests
    # subtopic slugs under their parent so the scoring engine resolves the
    # parent's implementation_fit either way.
    slug = extraction.subtopic or extraction.topic
    topic = topic_by_slug.get(slug) if slug else None

    if topic is None:
        # The prompt says never to invent a slug. When one appears anyway it is
        # dropped rather than coerced to a nearby topic — a wrong topic is worse
        # than a missing one, because it silently inflates that topic's score.
        run.unknown_topic += 1
        log_event(logger, "llm.extract.unknown_topic_slug", slug=slug, document_id=document.id)
        return

    with engine.begin() as conn:
        document_topics.upsert(
            conn,
            DocumentTopicInput(
                document_id=document.id,
                topic_id=topic.id,
                confidence=extraction.confidence,
                classification_method=EXTRACTION_METHOD,
            ),
        )

        upsert_signal(
            conn,
            ProblemSignalInput(
                document_id=document.id,
                topic_id=topic.id,
                signal_date=document.signal_date,
                classification_method=EXTRACTION_METHOD,
                region=document.state,
                severity_score=extraction.severity,
                urgency_score=extraction.urgency,
                economic_impact_score=extraction.economic_impact,
                frequency_hint=extraction.frequency.value,
                payer_type=extraction.buyer_type.value,
                evidence={
                    "affected_role": extraction.affected_role,
                    "problem_summary": extraction.problem_summary,
                    "suggested_solution_category": extraction.suggested_solution_category,
                    "topic": extraction.topic,
                    "subtopic": extraction.subtopic,
                    "confidence": extraction.confidence,
                    # §70: which model and prompt produced this, stored on the
                    # row itself so a signal can be traced without joining back
                    # through ai_usage by timestamp.
                    "provider": result.provider,
                    "model": result.model,
                    "prompt_version": result.prompt_version,
                },
            ),
        )

    run.extracted += 1


def extract_problems(
    engine: Engine,
    *,
    config: LLMConfig | None = None,
    provider: LLMProvider | None = None,
    limit: int | None = None,
    source_slug: str | None = None,
    dry_run: bool = False,
) -> ExtractionRun:
    config = config if config is not None else load_llm_config()
    run = ExtractionRun()

    # The disabled check comes AFTER the dry-run branch below, not here: a dry
    # run makes no calls, and its whole purpose is to show what a run would cost
    # BEFORE you decide to enable spending. Gating it behind `enabled: true`
    # would mean turning spending on to find out whether you want to.
    if not dry_run:
        if not config.enabled and provider is None:
            # `provider is None` means we would build whatever config names,
            # which may be a paid one. An explicitly injected provider (tests,
            # fixtures) is the caller taking responsibility for what it costs.
            run.stopped_reason = (
                "llm extraction is disabled (set enabled: true in config/llm.yaml)"
            )
            log_event(logger, "llm.extract.disabled")
            return run

        provider = provider if provider is not None else build_llm_provider(
            config.provider, config.provider_config
        )
        provider.check_available()

    batch = limit if limit is not None else config.max_documents_per_run
    batch = min(batch, config.max_documents_per_run)

    with engine.begin() as conn:
        source_id = None
        if source_slug is not None:
            source = sources.get_enabled_source_by_slug(conn, source_slug)
            if source is None:
                run.stopped_reason = f"unknown or disabled source '{source_slug}'"
                return run
            source_id = source.id

        pending = normalized_documents.get_documents_for_llm_extraction(
            conn,
            PROMPT_VERSION,
            limit=batch,
            source_id=source_id,
            min_text_length=config.min_text_length,
        )
        topic_by_slug = topics.get_enabled_topics_by_slug(conn)

    if dry_run:
        run.documents_seen = len(pending)
        run.stopped_reason = "dry run — no calls made"
        log_event(logger, "llm.extract.dry_run", documents=len(pending))
        return run

    taxonomy_hint = load_taxonomy_hint()

    for document in pending:
        try:
            check_budget(engine, config)
        except BudgetExceededError as exc:
            run.stopped_reason = str(exc)
            log_event(logger, "llm.extract.budget_stop", reason=str(exc))
            break

        run.documents_seen += 1

        try:
            result = provider.extract_problem(document.cleaned_text, taxonomy_hint)
        except LLMProviderError as exc:
            run.failed += 1
            record_usage(
                engine,
                provider=provider.name,
                model=getattr(provider, "model", "unknown"),
                operation=OPERATION,
                document_id=document.raw_document_id,
                prompt_version=PROMPT_VERSION,
                processing_version=EXTRACTION_METHOD,
                succeeded=False,
                error=str(exc)[:1000],
            )
            log_event(logger, "llm.extract.failed", document_id=document.id, error=str(exc))
            continue

        # Recorded before the result is used, so a crash during persistence
        # still leaves the spend on the ledger.
        record_usage(
            engine,
            provider=result.provider,
            model=result.model,
            operation=OPERATION,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            estimated_cost=result.estimated_cost,
            document_id=document.raw_document_id,
            prompt_version=result.prompt_version,
            processing_version=EXTRACTION_METHOD,
            succeeded=True,
        )
        run.estimated_cost += result.estimated_cost

        _persist(engine, document, result, topic_by_slug, run, config.min_confidence)

    log_event(logger, "llm.extract.finished", **run.as_dict())
    return run
