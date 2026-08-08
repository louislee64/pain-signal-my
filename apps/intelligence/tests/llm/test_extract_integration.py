"""End-to-end LLM extraction against a real Postgres, using a stub provider.

No network, no API key, no spend — the provider is a stub that returns whatever
the test tells it to. What is being tested is the pipeline around the model: the
budget guard, the usage ledger, dedup, topic mapping, and the confidence floor.

Every fixture is prefixed "pytest_llm_" and torn down only by its own prefix, so
this can never touch the real config-synced rows sharing this database — the
lesson from the Milestone 2 test-isolation bug.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import delete, insert, select
from ulid import ULID

from intelligence.db import (
    ai_usage_table,
    document_topics_table,
    normalized_documents_table,
    problem_signals_table,
    raw_documents_table,
    sources_table,
    topics_table,
)
from intelligence.llm.base import PROMPT_VERSION, LLMProvider, LLMProviderError
from intelligence.llm.extract import EXTRACTION_METHOD, extract_problems
from intelligence.llm.schemas import BuyerType, ExtractionResult, Frequency, ProblemExtraction
from intelligence.llm.usage import LLMConfig, spend_this_month, spend_today

SOURCE_SLUG = "pytest_llm_source"
TOPIC_SLUG = "pytest_llm_topic"


class StubProvider(LLMProvider):
    name = "stub"
    model = "stub-model-1"

    def __init__(self, extractions=None, raises=None, cost=0.01):
        super().__init__({})
        self.extractions = list(extractions or [])
        self.raises = raises
        self.cost = cost
        self.calls: list[str] = []

    def check_available(self) -> None:
        return None

    def extract_problem(self, text: str, taxonomy_hint: str) -> ExtractionResult:
        self.calls.append(text)
        if self.raises:
            raise LLMProviderError(self.raises)

        extraction = (
            self.extractions.pop(0)
            if self.extractions
            else ProblemExtraction(problem_present=False)
        )
        return ExtractionResult(
            extraction=extraction,
            provider=self.name,
            model=self.model,
            prompt_version=PROMPT_VERSION,
            input_tokens=1000,
            output_tokens=100,
            estimated_cost=self.cost,
        )


def config(**overrides) -> LLMConfig:
    base = {
        "enabled": True,
        "provider": "stub",
        "max_documents_per_run": 10,
        "min_text_length": 10,
        "min_confidence": 0.5,
        "budget": {"daily_usd": None, "monthly_usd": None},
    }
    base.update(overrides)
    return LLMConfig(raw=base)


def _cleanup(engine) -> None:
    with engine.begin() as conn:
        source_id = conn.execute(
            select(sources_table.c.id).where(sources_table.c.slug == SOURCE_SLUG)
        ).scalar()
        topic_id = conn.execute(
            select(topics_table.c.id).where(topics_table.c.slug == TOPIC_SLUG)
        ).scalar()

        if source_id is not None:
            raw_ids = [
                r.id
                for r in conn.execute(
                    select(raw_documents_table.c.id).where(
                        raw_documents_table.c.source_id == source_id
                    )
                )
            ]
            if raw_ids:
                doc_ids = [
                    r.id
                    for r in conn.execute(
                        select(normalized_documents_table.c.id).where(
                            normalized_documents_table.c.raw_document_id.in_(raw_ids)
                        )
                    )
                ]
                conn.execute(delete(ai_usage_table).where(ai_usage_table.c.document_id.in_(raw_ids)))
                if doc_ids:
                    conn.execute(
                        delete(problem_signals_table).where(
                            problem_signals_table.c.document_id.in_(doc_ids)
                        )
                    )
                    conn.execute(
                        delete(document_topics_table).where(
                            document_topics_table.c.document_id.in_(doc_ids)
                        )
                    )
                    conn.execute(
                        delete(normalized_documents_table).where(
                            normalized_documents_table.c.id.in_(doc_ids)
                        )
                    )
                conn.execute(delete(raw_documents_table).where(raw_documents_table.c.id.in_(raw_ids)))
            conn.execute(delete(sources_table).where(sources_table.c.id == source_id))

        if topic_id is not None:
            conn.execute(delete(topics_table).where(topics_table.c.id == topic_id))


@pytest.fixture()
def engine():
    from intelligence.db import get_engine

    get_engine.cache_clear()
    engine = get_engine()
    _cleanup(engine)

    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            insert(sources_table).values(
                name=SOURCE_SLUG, slug=SOURCE_SLUG, source_type="test", collector="test",
                config={}, terms_status="reviewed", personal_data_risk="none", enabled=True,
                created_at=now, updated_at=now,
            )
        )
        conn.execute(
            insert(topics_table).values(
                slug=TOPIC_SLUG, name="Pytest LLM Topic", enabled=True,
                created_at=now, updated_at=now,
            )
        )

    yield engine
    _cleanup(engine)


def seed_documents(engine, count: int = 1, text: str = "A" * 200) -> list[int]:
    now = datetime.now(timezone.utc)
    ids: list[int] = []

    with engine.begin() as conn:
        source_id = conn.execute(
            select(sources_table.c.id).where(sources_table.c.slug == SOURCE_SLUG)
        ).scalar_one()

        for index in range(count):
            raw_id = str(ULID())
            conn.execute(
                insert(raw_documents_table).values(
                    id=raw_id, source_id=source_id, external_id=f"pytest_llm_{index}",
                    body=f"{text} {index}", content_hash=f"pytest_llm_hash_{index}",
                    published_at=now - timedelta(days=1), collected_at=now,
                    created_at=now,
                )
            )
            result = conn.execute(
                insert(normalized_documents_table).values(
                    raw_document_id=raw_id, cleaned_text=f"{text} {index}",
                    language="en", country="MY", processed_at=now,
                )
            )
            ids.append(result.inserted_primary_key[0])

    return ids


def signals(engine) -> list:
    with engine.begin() as conn:
        return conn.execute(
            select(problem_signals_table).where(
                problem_signals_table.c.classification_method == EXTRACTION_METHOD
            )
        ).all()


def usage_rows(engine) -> list:
    with engine.begin() as conn:
        return conn.execute(
            select(ai_usage_table).where(ai_usage_table.c.model == "stub-model-1")
        ).all()


class TestSafetyDefaults:
    def test_disabled_config_makes_no_calls(self, engine):
        seed_documents(engine, 3)
        provider = StubProvider()

        # No provider is injected: the pipeline would have to build the one
        # config names, which may be a paid one. It must refuse.
        run = extract_problems(engine, source_slug=SOURCE_SLUG, config=config(enabled=False))

        assert run.documents_seen == 0
        assert provider.calls == []
        assert "disabled" in run.stopped_reason

    def test_dry_run_reports_the_queue_without_spending(self, engine):
        seed_documents(engine, 3)
        provider = StubProvider()

        run = extract_problems(engine, source_slug=SOURCE_SLUG, config=config(), provider=provider, dry_run=True)

        assert run.documents_seen == 3
        assert provider.calls == []
        assert usage_rows(engine) == []

    def test_dry_run_works_while_extraction_is_still_disabled(self, engine):
        """The documented workflow is "see what it would cost, then decide".
        Gating the dry run behind `enabled: true` would mean turning spending on
        to find out whether you want to."""

        seed_documents(engine, 3)

        run = extract_problems(
            engine, source_slug=SOURCE_SLUG, config=config(enabled=False), dry_run=True
        )

        assert run.documents_seen == 3
        assert run.stopped_reason == "dry run — no calls made"

    def test_max_documents_per_run_caps_the_batch(self, engine):
        seed_documents(engine, 5)
        provider = StubProvider()

        extract_problems(engine, source_slug=SOURCE_SLUG, config=config(max_documents_per_run=2), provider=provider)

        assert len(provider.calls) == 2

    def test_explicit_limit_cannot_exceed_the_configured_cap(self, engine):
        seed_documents(engine, 5)
        provider = StubProvider()

        extract_problems(engine, source_slug=SOURCE_SLUG, config=config(max_documents_per_run=2), provider=provider, limit=100)

        assert len(provider.calls) == 2

    def test_short_documents_are_never_sent(self, engine):
        seed_documents(engine, 1, text="too short")
        provider = StubProvider()

        extract_problems(engine, source_slug=SOURCE_SLUG, config=config(min_text_length=80), provider=provider)

        assert provider.calls == []


    def test_source_scope_is_honoured(self, engine):
        """Written after this suite's first run charged 154 stub calls against
        real ingested documents: an unscoped run reads the WHOLE table, which is
        correct in production and destructive in a test. The pipeline must send
        nothing outside the named source."""

        seed_documents(engine, 2)
        provider = StubProvider()

        run = extract_problems(
            engine, source_slug=SOURCE_SLUG, config=config(max_documents_per_run=100), provider=provider
        )

        assert len(provider.calls) == 2
        assert run.documents_seen == 2
        with engine.begin() as conn:
            source_id = conn.execute(
                select(sources_table.c.id).where(sources_table.c.slug == SOURCE_SLUG)
            ).scalar_one()
            charged_elsewhere = conn.execute(
                select(ai_usage_table.c.id)
                .select_from(ai_usage_table.join(raw_documents_table))
                .where(raw_documents_table.c.source_id != source_id)
                .where(ai_usage_table.c.model == "stub-model-1")
            ).all()
        assert charged_elsewhere == []

    def test_an_unknown_source_stops_the_run_rather_than_scanning_everything(self, engine):
        seed_documents(engine, 2)
        provider = StubProvider()

        run = extract_problems(
            engine, source_slug="pytest_llm_no_such_source", config=config(), provider=provider
        )

        # Falling back to "all sources" on a typo would be the expensive
        # interpretation of an obvious mistake.
        assert provider.calls == []
        assert "unknown or disabled source" in run.stopped_reason


class TestBudgetGuard:
    def test_run_stops_once_the_daily_budget_is_reached(self, engine):
        seed_documents(engine, 5)
        # Each call costs $0.02; a $0.05 daily budget allows three before the
        # ledger reaches it, then the fourth is refused.
        provider = StubProvider(cost=0.02)

        run = extract_problems(engine, source_slug=SOURCE_SLUG, config=config(budget={"daily_usd": 0.05, "monthly_usd": None}), provider=provider
        )

        assert len(provider.calls) == 3
        assert "daily AI budget" in run.stopped_reason

    def test_monthly_budget_is_enforced_independently(self, engine):
        seed_documents(engine, 5)
        provider = StubProvider(cost=0.02)

        run = extract_problems(
            engine,
            source_slug=SOURCE_SLUG,
            config=config(budget={"daily_usd": None, "monthly_usd": 0.03}),
            provider=provider,
        )

        assert len(provider.calls) == 2
        assert "monthly AI budget" in run.stopped_reason

    def test_spend_helpers_agree_with_the_ledger(self, engine):
        seed_documents(engine, 2)
        extract_problems(engine, source_slug=SOURCE_SLUG, config=config(), provider=StubProvider(cost=0.25))

        with engine.begin() as conn:
            # Other rows may exist in this shared database, so assert the delta
            # is at least what this test spent rather than an exact total.
            assert spend_today(conn) >= 0.5
            assert spend_this_month(conn) >= spend_today(conn)


class TestUsageLedger:
    def test_every_successful_call_is_recorded_with_provenance(self, engine):
        seed_documents(engine, 2)

        extract_problems(engine, source_slug=SOURCE_SLUG, config=config(), provider=StubProvider(cost=0.03))

        rows = usage_rows(engine)
        assert len(rows) == 2
        for row in rows:
            assert row.succeeded is True
            assert row.provider == "stub"
            assert row.operation == "extract_problem"
            assert row.prompt_version == PROMPT_VERSION
            assert row.processing_version == EXTRACTION_METHOD
            assert float(row.estimated_cost) == 0.03
            assert row.document_id is not None

    def test_failed_calls_are_recorded_too(self, engine):
        seed_documents(engine, 2)

        run = extract_problems(engine, source_slug=SOURCE_SLUG, config=config(), provider=StubProvider(raises="upstream exploded")
        )

        rows = usage_rows(engine)
        assert run.failed == 2
        assert len(rows) == 2
        assert all(row.succeeded is False for row in rows)
        assert all("upstream exploded" in row.error for row in rows)

    def test_a_failed_document_is_retried_on_the_next_run(self, engine):
        seed_documents(engine, 1)

        extract_problems(engine, source_slug=SOURCE_SLUG, config=config(), provider=StubProvider(raises="timeout"))
        retry = StubProvider()
        extract_problems(engine, source_slug=SOURCE_SLUG, config=config(), provider=retry)

        # A transient error must not blacklist the document.
        assert len(retry.calls) == 1


class TestDeduplication:
    def test_a_processed_document_is_never_sent_twice(self, engine):
        seed_documents(engine, 2)

        first = StubProvider()
        extract_problems(engine, source_slug=SOURCE_SLUG, config=config(), provider=first)
        second = StubProvider()
        extract_problems(engine, source_slug=SOURCE_SLUG, config=config(), provider=second)

        assert len(first.calls) == 2
        assert second.calls == []

    def test_documents_producing_no_problem_are_still_marked_processed(self, engine):
        """The expensive-path difference from the free rule-based classifier:
        "no problem found" must be remembered, or every quiet document is paid
        for again on every run."""

        seed_documents(engine, 1)
        run = extract_problems(engine, source_slug=SOURCE_SLUG, config=config(), provider=StubProvider())

        assert run.no_problem == 1
        assert signals(engine) == []

        second = StubProvider()
        extract_problems(engine, source_slug=SOURCE_SLUG, config=config(), provider=second)
        assert second.calls == []


class TestPersistence:
    def _extraction(self, **overrides):
        defaults = {
            "problem_present": True,
            "topic": TOPIC_SLUG,
            "affected_role": "cashier",
            "buyer_type": BuyerType.BUSINESS_OWNER,
            "frequency": Frequency.DAILY,
            "severity": 70,
            "economic_impact": 60,
            "urgency": 55,
            "problem_summary": "Manual re-keying of sales into accounting.",
            "confidence": 0.9,
        }
        defaults.update(overrides)
        return ProblemExtraction(**defaults)

    def test_extraction_becomes_a_problem_signal_with_full_provenance(self, engine):
        seed_documents(engine, 1)

        run = extract_problems(engine, source_slug=SOURCE_SLUG, config=config(), provider=StubProvider([self._extraction()])
        )

        assert run.extracted == 1
        rows = signals(engine)
        assert len(rows) == 1
        row = rows[0]
        assert row.severity_score == 70
        assert row.economic_impact_score == 60
        assert row.urgency_score == 55
        assert row.frequency_hint == "daily"
        assert row.payer_type == "business_owner"
        assert row.evidence_json["affected_role"] == "cashier"
        assert row.evidence_json["model"] == "stub-model-1"
        assert row.evidence_json["prompt_version"] == PROMPT_VERSION

    def test_llm_signals_do_not_overwrite_rule_based_ones(self, engine):
        """Both methods classify into the same topic. They must coexist, or
        re-running one silently destroys the other's evidence."""

        document_ids = seed_documents(engine, 1)
        now = datetime.now(timezone.utc)
        with engine.begin() as conn:
            topic_id = conn.execute(
                select(topics_table.c.id).where(topics_table.c.slug == TOPIC_SLUG)
            ).scalar_one()
            conn.execute(
                insert(problem_signals_table).values(
                    document_id=document_ids[0], topic_id=topic_id,
                    signal_date=date.today(), classification_method="rule_based_keyword_v1",
                    severity_score=20, created_at=now, updated_at=now,
                )
            )

        extract_problems(engine, source_slug=SOURCE_SLUG, config=config(), provider=StubProvider([self._extraction()]))

        with engine.begin() as conn:
            rows = conn.execute(
                select(problem_signals_table).where(
                    problem_signals_table.c.document_id == document_ids[0]
                )
            ).all()

        assert len(rows) == 2
        by_method = {row.classification_method: row for row in rows}
        assert by_method["rule_based_keyword_v1"].severity_score == 20
        assert by_method[EXTRACTION_METHOD].severity_score == 70

    def test_a_subtopic_slug_is_preferred_over_its_parent(self, engine):
        seed_documents(engine, 1)
        # The stub returns a real parent topic plus this test's topic as the
        # subtopic; the more specific slug is the one that must be stored.
        extraction = self._extraction(topic="billing_invoice", subtopic=TOPIC_SLUG)

        extract_problems(engine, source_slug=SOURCE_SLUG, config=config(), provider=StubProvider([extraction]))

        rows = signals(engine)
        with engine.begin() as conn:
            topic_id = conn.execute(
                select(topics_table.c.id).where(topics_table.c.slug == TOPIC_SLUG)
            ).scalar_one()
        assert rows[0].topic_id == topic_id

    def test_an_invented_slug_is_dropped_not_guessed(self, engine):
        seed_documents(engine, 1)
        extraction = self._extraction(topic="totally_made_up_topic", subtopic=None)

        run = extract_problems(engine, source_slug=SOURCE_SLUG, config=config(), provider=StubProvider([extraction]))

        # A wrong topic silently inflates that topic's score; a missing one
        # only loses a signal.
        assert run.unknown_topic == 1
        assert signals(engine) == []

    def test_low_confidence_extractions_are_paid_for_but_not_trusted(self, engine):
        seed_documents(engine, 1)
        extraction = self._extraction(confidence=0.3)

        run = extract_problems(engine, source_slug=SOURCE_SLUG, config=config(min_confidence=0.5), provider=StubProvider([extraction])
        )

        assert run.low_confidence == 1
        assert signals(engine) == []
        # The call still happened, so the ledger still records the spend.
        assert len(usage_rows(engine)) == 1

    def test_problem_present_false_writes_nothing(self, engine):
        seed_documents(engine, 1)
        extraction = ProblemExtraction(problem_present=False, confidence=0.95)

        run = extract_problems(engine, source_slug=SOURCE_SLUG, config=config(), provider=StubProvider([extraction]))

        assert run.no_problem == 1
        assert signals(engine) == []
