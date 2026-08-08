"""Commercial evidence read from §21's CRM tables, against a real Postgres.

The point of these tests is that the Python engine and the Laravel API must
count the same things the same way. Laravel decides whether a promotion is
allowed; Python decides whether §29's cap lifts. If their counting rules drift,
an opportunity can be promoted to `paid_pilot` while still scoring as though
nobody had ever paid — and nothing would report the contradiction.

All fixtures are prefixed `pytest_comm_` and torn down only by that prefix.
"""

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import delete, insert, select

from conftest import PACKAGE_ROOT, REPO_ROOT

from intelligence.db import (
    commercial_evidence_table,
    customer_interviews_table,
    opportunities_table,
    topics_table,
)
from intelligence.scoring.commercial import (
    PAID_TYPES,
    STRONG_SIGNAL_TYPES,
    gather_commercial_evidence,
)

TOPIC_SLUG = "pytest_comm_topic"
SECOND_TOPIC_SLUG = "pytest_comm_topic_two"


def _cleanup(engine) -> None:
    with engine.begin() as conn:
        topic_ids = [
            r.id
            for r in conn.execute(
                select(topics_table.c.id).where(
                    topics_table.c.slug.in_([TOPIC_SLUG, SECOND_TOPIC_SLUG])
                )
            )
        ]
        if topic_ids:
            opportunity_ids = [
                r.id
                for r in conn.execute(
                    select(opportunities_table.c.id).where(
                        opportunities_table.c.topic_id.in_(topic_ids)
                    )
                )
            ]
            if opportunity_ids:
                conn.execute(
                    delete(customer_interviews_table).where(
                        customer_interviews_table.c.opportunity_id.in_(opportunity_ids)
                    )
                )
                conn.execute(
                    delete(commercial_evidence_table).where(
                        commercial_evidence_table.c.opportunity_id.in_(opportunity_ids)
                    )
                )
                conn.execute(
                    delete(opportunities_table).where(opportunities_table.c.id.in_(opportunity_ids))
                )
            conn.execute(delete(topics_table).where(topics_table.c.id.in_(topic_ids)))


@pytest.fixture()
def engine():
    from intelligence.db import get_engine

    get_engine.cache_clear()
    engine = get_engine()
    _cleanup(engine)
    yield engine
    _cleanup(engine)


def make_opportunity(engine, slug: str = TOPIC_SLUG) -> tuple[int, int]:
    """Returns (topic_id, opportunity_id)."""

    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        topic_id = conn.execute(
            insert(topics_table)
            .values(slug=slug, name=slug, enabled=True, created_at=now, updated_at=now)
            .returning(topics_table.c.id)
        ).scalar_one()

        opportunity_id = conn.execute(
            insert(opportunities_table)
            .values(
                topic_id=topic_id,
                title=f"Opportunity for {slug}",
                status="observed",
                created_at=now,
                updated_at=now,
            )
            .returning(opportunities_table.c.id)
        ).scalar_one()

    return topic_id, opportunity_id


def add_interview(
    engine, opportunity_id: int, *, company_ref=None, confirmed=None, pilot_interest=None
) -> None:
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            insert(customer_interviews_table).values(
                opportunity_id=opportunity_id,
                company_ref=company_ref,
                problem_confirmed=confirmed,
                pilot_interest=pilot_interest,
                interviewed_at=now,
                created_at=now,
                updated_at=now,
            )
        )


def add_evidence(engine, opportunity_id: int, evidence_type: str, company_ref=None, value=None) -> None:
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(
            insert(commercial_evidence_table).values(
                opportunity_id=opportunity_id,
                evidence_type=evidence_type,
                strength="medium",
                company_ref=company_ref,
                value=value,
                currency="MYR",
                occurred_at=now,
                created_at=now,
                updated_at=now,
            )
        )


def counts_for(engine, topic_id: int):
    with engine.begin() as conn:
        return gather_commercial_evidence(conn).get(topic_id)


class TestIndependence:
    def test_two_interviews_at_one_business_are_one_independent_confirmation(self, engine):
        # §7 Gate 3 asks for independent businesses. This is the rule that must
        # match Laravel's evidenceSummary() exactly.
        topic_id, opportunity_id = make_opportunity(engine)
        add_interview(engine, opportunity_id, company_ref="retailer-a", confirmed=True)
        add_interview(engine, opportunity_id, company_ref="retailer-a", confirmed=True)

        counts = counts_for(engine, topic_id)

        assert counts.problem_confirmed_count == 2
        assert counts.independent_confirmations == 1

    def test_two_businesses_are_two_independent_confirmations(self, engine):
        topic_id, opportunity_id = make_opportunity(engine)
        add_interview(engine, opportunity_id, company_ref="retailer-a", confirmed=True)
        add_interview(engine, opportunity_id, company_ref="retailer-b", confirmed=True)

        assert counts_for(engine, topic_id).independent_confirmations == 2

    def test_a_null_company_ref_cannot_prove_independence(self, engine):
        topic_id, opportunity_id = make_opportunity(engine)
        add_interview(engine, opportunity_id, company_ref=None, confirmed=True)
        add_interview(engine, opportunity_id, company_ref=None, confirmed=True)

        counts = counts_for(engine, topic_id)

        # Still evidence for Gate 2 (one confirmation); not evidence of
        # independence, which is what Gate 3 counts.
        assert counts.problem_confirmed_count == 2
        assert counts.independent_confirmations == 0

    def test_an_unconfirmed_interview_does_not_confirm_anything(self, engine):
        topic_id, opportunity_id = make_opportunity(engine)
        add_interview(engine, opportunity_id, company_ref="retailer-a", confirmed=False)
        add_interview(engine, opportunity_id, company_ref="retailer-b", confirmed=None)

        counts = counts_for(engine, topic_id)

        assert counts.interview_count == 2
        assert counts.problem_confirmed_count == 0
        assert counts.independent_confirmations == 0


class TestPayment:
    def test_two_payments_from_one_business_are_one_paying_business(self, engine):
        # §7 Gate 5 wants a second paying business: two pilots with the same
        # customer prove retention, not repeatability.
        topic_id, opportunity_id = make_opportunity(engine)
        add_evidence(engine, opportunity_id, "paid_pilot", "retailer-a", 4500)
        add_evidence(engine, opportunity_id, "repeat_customer", "retailer-a", 9000)

        counts = counts_for(engine, topic_id)

        assert counts.paying_business_count == 1
        assert counts.paid_pilot_count == 1

    def test_a_second_paying_business_is_counted(self, engine):
        topic_id, opportunity_id = make_opportunity(engine)
        add_evidence(engine, opportunity_id, "paid_pilot", "retailer-a", 4500)
        add_evidence(engine, opportunity_id, "paid_pilot", "retailer-b", 3800)

        counts = counts_for(engine, topic_id)

        assert counts.paying_business_count == 2
        assert counts.paid_pilot_count == 2

    def test_a_payment_with_no_company_ref_cannot_count_toward_repeatability(self, engine):
        topic_id, opportunity_id = make_opportunity(engine)
        add_evidence(engine, opportunity_id, "paid_pilot", None, 4500)

        counts = counts_for(engine, topic_id)

        # The payment is real and counted; it just cannot prove a *second*
        # business, which is what the API warns about at record time.
        assert counts.paid_pilot_count == 1
        assert counts.paying_business_count == 0

    def test_soft_evidence_is_not_a_payment(self, engine):
        topic_id, opportunity_id = make_opportunity(engine)
        for soft in ("pilot_interest", "customer_request", "interview"):
            add_evidence(engine, opportunity_id, soft, "retailer-a")

        counts = counts_for(engine, topic_id)

        assert counts.paying_business_count == 0
        assert counts.paid_pilot_count == 0


class TestStrongSignal:
    def test_pilot_interest_alone_is_not_a_strong_signal(self, engine):
        # §7 Gate 4: paying is "considerably more valuable than 'I would
        # probably use this'".
        topic_id, opportunity_id = make_opportunity(engine)
        add_evidence(engine, opportunity_id, "pilot_interest", "retailer-a")

        assert counts_for(engine, topic_id).has_strong_buyer_signal is False

    @pytest.mark.parametrize("evidence_type", STRONG_SIGNAL_TYPES)
    def test_each_strong_type_sets_the_flag(self, engine, evidence_type):
        topic_id, opportunity_id = make_opportunity(engine)
        add_evidence(engine, opportunity_id, evidence_type, "retailer-a")

        assert counts_for(engine, topic_id).has_strong_buyer_signal is True

    def test_paid_types_are_a_subset_of_strong_types(self):
        # Money changing hands must never fail to count as a strong signal.
        # A type in one list and not the other would let an opportunity clear
        # Gate 4 while failing Gate 3, which is not a state the funnel contains.
        assert set(PAID_TYPES) <= set(STRONG_SIGNAL_TYPES)


def _find_php_model() -> Path | None:
    """Locate the Laravel model in whichever layout we are running under.

    A CI checkout has apps/api beside apps/intelligence; the intelligence
    container mounts only its own directory and so cannot see it at all. Both are
    normal, which is why this returns None rather than raising — but it must
    genuinely find the file when it is there, or the test silently stops
    guarding anything.
    """

    candidates = [PACKAGE_ROOT.parent / "api"]
    if REPO_ROOT is not None:
        candidates.append(REPO_ROOT / "apps" / "api")

    for base in candidates:
        path = base / "app" / "Models" / "CommercialEvidence.php"
        if path.exists():
            return path

    return None


PHP_MODEL = _find_php_model()


class TestCrossLanguageAgreement:
    """The two implementations must classify evidence identically.

    Laravel decides whether a stage promotion is allowed; Python decides whether
    §29's cap lifts. If their type lists drift, an opportunity can sit at
    `paid_pilot` while scoring as though nobody had ever paid — a contradiction
    nothing else in the system would report.

    Asserted by reading the PHP source rather than by restating the lists in a
    fixture, because a fixture would be a third copy that can drift too. Skipped
    where the Laravel app is not on disk (the intelligence container mounts only
    its own directory), so it runs in CI, where the whole repo is checked out.
    """

    def _php_const(self, name: str) -> set[str]:
        source = PHP_MODEL.read_text()  # type: ignore[union-attr]
        start = source.index(f"const {name} = [")
        body = source[start : source.index("];", start)]
        return set(re.findall(r"'([a-z_]+)'", body))

    @pytest.mark.skipif(PHP_MODEL is None, reason="Laravel app not on disk in this container")
    def test_strong_signal_types_match(self):
        assert self._php_const("STRONG_SIGNAL_TYPES") == set(STRONG_SIGNAL_TYPES)

    @pytest.mark.skipif(PHP_MODEL is None, reason="Laravel app not on disk in this container")
    def test_paid_types_match(self):
        assert self._php_const("PAID_TYPES") == set(PAID_TYPES)


class TestScoping:
    def test_evidence_does_not_leak_between_topics(self, engine):
        topic_a, opportunity_a = make_opportunity(engine, TOPIC_SLUG)
        topic_b, _ = make_opportunity(engine, SECOND_TOPIC_SLUG)
        add_evidence(engine, opportunity_a, "paid_pilot", "retailer-a", 4500)

        assert counts_for(engine, topic_a).paid_pilot_count == 1
        assert counts_for(engine, topic_b) is None

    def test_a_topic_with_no_opportunity_row_simply_does_not_appear(self, engine):
        now = datetime.now(timezone.utc)
        with engine.begin() as conn:
            topic_id = conn.execute(
                insert(topics_table)
                .values(slug=TOPIC_SLUG, name=TOPIC_SLUG, enabled=True, created_at=now, updated_at=now)
                .returning(topics_table.c.id)
            ).scalar_one()

        # Correct rather than a gap: no opportunity means nobody has had
        # anything to record against it.
        assert counts_for(engine, topic_id) is None

    def test_pilot_interest_is_counted_separately_from_confirmation(self, engine):
        topic_id, opportunity_id = make_opportunity(engine)
        add_interview(engine, opportunity_id, company_ref="retailer-a", confirmed=True, pilot_interest=True)
        add_interview(engine, opportunity_id, company_ref="retailer-b", confirmed=True, pilot_interest=False)

        counts = counts_for(engine, topic_id)

        assert counts.problem_confirmed_count == 2
        assert counts.pilot_interest_count == 1


class TestCapLifts:
    """The behaviour the whole milestone exists to enable."""

    def test_recorded_payment_lifts_the_79_point_cap(self, engine):
        from datetime import date

        from intelligence.scoring.config import load_scoring_config
        from intelligence.scoring.model import (
            TopicMeasurements,
            is_commercially_validated,
            score_opportunity,
        )

        from conftest import SCORING_CONFIG_PATH

        config = load_scoring_config(SCORING_CONFIG_PATH)
        as_of = date(2026, 8, 8)

        # Everything maxed except human evidence: §29 caps this at 79 however
        # good the inferred signals are.
        speculative = TopicMeasurements(
            topic_slug="billing_invoice",
            mention_count=500,
            previous_mention_count=10,
            avg_severity=100,
            distinct_regions=16,
            search_growth_score=5.0,
            signals_with_payer=500,
            dominant_frequency_hint="daily",
            avg_economic_impact=100,
            avg_urgency=100,
            distinct_sources=10,
            avg_classification_confidence=100,
            latest_signal_date=as_of,
        )

        assert is_commercially_validated(speculative) is False
        capped = score_opportunity(speculative, config, as_of)
        assert float(capped.opportunity.score) <= 79.0

        # One recorded payment, and the same topic is no longer capped.
        with_payment = TopicMeasurements(
            **{
                **speculative.__dict__,
                "paid_pilot_count": 1,
                "paying_business_count": 1,
            }
        )

        assert is_commercially_validated(with_payment) is True
        uncapped = score_opportunity(with_payment, config, as_of)
        assert float(uncapped.opportunity.score) > 79.0

    def test_confirmations_without_a_strong_signal_stay_capped(self, engine):
        from datetime import date

        from intelligence.scoring.config import load_scoring_config
        from intelligence.scoring.model import TopicMeasurements, is_commercially_validated

        from conftest import SCORING_CONFIG_PATH

        load_scoring_config(SCORING_CONFIG_PATH)

        # §7 Gate 3 needs both halves. "Several businesses agree it is annoying"
        # is not commercial validation.
        agreed_but_unpaid = TopicMeasurements(
            topic_slug="billing_invoice",
            problem_confirmed_count=5,
            independent_confirmations=5,
            has_strong_buyer_signal=False,
        )

        assert is_commercially_validated(agreed_but_unpaid) is False
