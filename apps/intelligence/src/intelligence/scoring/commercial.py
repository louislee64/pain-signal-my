"""Human commercial evidence, read per topic (PROJECT_SPEC.md §21, §7).

Until Milestone 6 these figures were honestly zero and §29's 79-point cap was
doing its job unaided. Now they come from real rows, which means the cap can
finally lift — but only for opportunities where a person actually went and found
out something.

Kept separate from measurements.py because the two answer different questions
from different tables. measurements.py asks "what does the internet say about
this topic"; this asks "what did we learn by talking to businesses". They join
on opportunity → topic, and conflating them would make the scoring engine's one
genuinely human input indistinguishable from its inferred ones.

Two counting rules are load-bearing and easy to get wrong:

  * §7 Gate 3 wants independent *businesses*, so confirmations are counted by
    distinct `company_ref`. Two conversations at one company are one company's
    opinion.
  * §7 Gate 5 wants a *second paying* business, so payments are also counted by
    distinct `company_ref`. Two pilots with one customer prove retention, not
    repeatability.
"""

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.engine import Connection

from intelligence.db import (
    commercial_evidence_table,
    customer_interviews_table,
    opportunities_table,
)

# §7 Gate 3's "at least one strong commercial signal". Mirrors
# CommercialEvidence::STRONG_SIGNAL_TYPES in the Laravel model — the two must
# agree, or the API would refuse a promotion the engine is suggesting.
#
# `pilot_interest` is deliberately absent: §7 Gate 4 says a customer paying is
# "considerably more valuable than 'I would probably use this'", and stated
# interest is the polite end of that sentence.
STRONG_SIGNAL_TYPES = (
    "proposal",
    "deposit",
    "purchase_order",
    "existing_spend",
    "paid_pilot",
    "repeat_customer",
)

# Money actually changed hands (§7 Gate 4).
PAID_TYPES = ("paid_pilot", "deposit", "purchase_order", "repeat_customer")


@dataclass(frozen=True)
class CommercialEvidenceCounts:
    interview_count: int = 0
    problem_confirmed_count: int = 0
    independent_confirmations: int = 0
    paid_pilot_count: int = 0
    paying_business_count: int = 0
    has_strong_buyer_signal: bool = False
    pilot_interest_count: int = 0
    evidence_types: tuple[str, ...] = field(default_factory=tuple)


def gather_commercial_evidence(conn: Connection) -> dict[int, CommercialEvidenceCounts]:
    """Counts keyed by TOPIC id, not opportunity id.

    The scoring engine works in topics; the CRM tables hang off opportunities.
    Joining here rather than at the call site keeps that translation in one
    place — and there is exactly one opportunity per topic, so the mapping is
    unambiguous.

    Topics with no opportunity row yet simply do not appear, which is correct:
    no opportunity means nobody has had anything to record against it.
    """

    counts: dict[int, dict] = {}

    interviews = conn.execute(
        select(
            opportunities_table.c.topic_id,
            func.count(customer_interviews_table.c.id).label("interview_count"),
        )
        .select_from(
            customer_interviews_table.join(
                opportunities_table,
                opportunities_table.c.id == customer_interviews_table.c.opportunity_id,
            )
        )
        .group_by(opportunities_table.c.topic_id)
    ).all()

    for row in interviews:
        counts.setdefault(row.topic_id, {})["interview_count"] = int(row.interview_count)

    confirmed = conn.execute(
        select(
            opportunities_table.c.topic_id,
            func.count(customer_interviews_table.c.id).label("confirmed_count"),
            # DISTINCT on the pseudonymous business label. NULLs are excluded by
            # count(distinct ...) in SQL, which is exactly right: an interview
            # with no company_ref cannot be shown to be independent, so it counts
            # for Gate 2 (which needs one confirmation) but not Gate 3.
            func.count(func.distinct(customer_interviews_table.c.company_ref)).label("independent"),
        )
        .select_from(
            customer_interviews_table.join(
                opportunities_table,
                opportunities_table.c.id == customer_interviews_table.c.opportunity_id,
            )
        )
        .where(customer_interviews_table.c.problem_confirmed.is_(True))
        .group_by(opportunities_table.c.topic_id)
    ).all()

    for row in confirmed:
        entry = counts.setdefault(row.topic_id, {})
        entry["problem_confirmed_count"] = int(row.confirmed_count)
        entry["independent_confirmations"] = int(row.independent)

    pilot_interest = conn.execute(
        select(
            opportunities_table.c.topic_id,
            func.count(customer_interviews_table.c.id).label("pilot_interest_count"),
        )
        .select_from(
            customer_interviews_table.join(
                opportunities_table,
                opportunities_table.c.id == customer_interviews_table.c.opportunity_id,
            )
        )
        .where(customer_interviews_table.c.pilot_interest.is_(True))
        .group_by(opportunities_table.c.topic_id)
    ).all()

    for row in pilot_interest:
        counts.setdefault(row.topic_id, {})["pilot_interest_count"] = int(row.pilot_interest_count)

    evidence = conn.execute(
        select(
            opportunities_table.c.topic_id,
            commercial_evidence_table.c.evidence_type,
            commercial_evidence_table.c.company_ref,
            func.count(commercial_evidence_table.c.id).label("n"),
        )
        .select_from(
            commercial_evidence_table.join(
                opportunities_table,
                opportunities_table.c.id == commercial_evidence_table.c.opportunity_id,
            )
        )
        .group_by(
            opportunities_table.c.topic_id,
            commercial_evidence_table.c.evidence_type,
            commercial_evidence_table.c.company_ref,
        )
    ).all()

    # Grouped in Python rather than in five more SQL round trips: the row count
    # here is small (one per topic × type × business) and the distinct-business
    # logic reads far more clearly as a set than as nested aggregates.
    paying_businesses: dict[int, set[str]] = {}
    for row in evidence:
        entry = counts.setdefault(row.topic_id, {})

        types = entry.setdefault("evidence_types", set())
        types.add(row.evidence_type)

        if row.evidence_type == "paid_pilot":
            entry["paid_pilot_count"] = entry.get("paid_pilot_count", 0) + int(row.n)

        if row.evidence_type in PAID_TYPES and row.company_ref:
            paying_businesses.setdefault(row.topic_id, set()).add(row.company_ref)

    result: dict[int, CommercialEvidenceCounts] = {}
    for topic_id, entry in counts.items():
        types = tuple(sorted(entry.get("evidence_types", set())))
        result[topic_id] = CommercialEvidenceCounts(
            interview_count=entry.get("interview_count", 0),
            problem_confirmed_count=entry.get("problem_confirmed_count", 0),
            independent_confirmations=entry.get("independent_confirmations", 0),
            paid_pilot_count=entry.get("paid_pilot_count", 0),
            paying_business_count=len(paying_businesses.get(topic_id, set())),
            has_strong_buyer_signal=any(t in STRONG_SIGNAL_TYPES for t in types),
            pilot_interest_count=entry.get("pilot_interest_count", 0),
            evidence_types=types,
        )

    return result
