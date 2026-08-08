"""Pain / Commercial / Confidence / Opportunity scoring (PROJECT_SPEC.md §26-§30).

Pure functions: measured inputs in, scores plus a full explanation out. No
database, no config file reads beyond the ScoringConfig handed in — so the
arithmetic can be tested exhaustively, which §71 demands ("Write exhaustive
tests").

Milestone 4's acceptance criterion is "Each opportunity is explainable through
stored evidence", so every score returns a ScoreBreakdown carrying each
dimension's raw input, its normalized 0-100 value, its weight, and its weighted
contribution. That structure is what gets persisted — not just the final number
— so an opportunity stays explainable even after the weights have since changed.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from intelligence.scoring.config import ScoringConfig


def _jsonable(value: Any) -> Any:
    """Coerce a raw dimension input into something JSONB can store.

    Breakdowns are persisted verbatim to make each score explainable, so a raw
    value that happens to be a date or Decimal must not be able to fail the
    whole scoring run at write time.
    """

    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


@dataclass(frozen=True)
class Dimension:
    """One weighted input to a score, kept with everything needed to explain it."""

    name: str
    raw: Any
    normalized: float
    weight: float

    @property
    def contribution(self) -> float:
        return self.normalized * self.weight

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw": _jsonable(self.raw),
            "normalized": round(self.normalized, 2),
            "weight": self.weight,
            "contribution": round(self.contribution, 2),
        }


@dataclass(frozen=True)
class ScoreBreakdown:
    score: float
    dimensions: list[Dimension] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 2),
            "dimensions": {d.name: d.to_dict() for d in self.dimensions},
            "notes": self.notes,
        }


@dataclass(frozen=True)
class TopicMeasurements:
    """Everything measured about one topic, gathered from Milestones 1-3 data.

    Deliberately a plain value object rather than a DB row: the scoring layer
    should be testable without a database, and swapping how a measurement is
    gathered must not ripple into how it is scored.
    """

    topic_slug: str
    parent_slug: str | None = None

    # §26 inputs
    mention_count: int = 0
    previous_mention_count: int = 0
    avg_severity: float | None = None
    distinct_regions: int = 0
    search_growth_score: float | None = None

    # §27 inputs
    signals_with_payer: int = 0
    dominant_frequency_hint: str | None = None
    avg_economic_impact: float | None = None
    avg_urgency: float | None = None

    # §30 inputs
    distinct_sources: int = 0
    avg_classification_confidence: float | None = None
    latest_signal_date: date | None = None

    # §21's commercial CRM fills these (scoring/commercial.py). They stay zero
    # for any topic nobody has investigated, which is exactly why §29 caps an
    # uncommercially-validated score.
    interview_count: int = 0
    problem_confirmed_count: int = 0

    # §7 Gate 3 asks for independent *businesses*, not interviews: two
    # conversations at one company are one company's opinion. Counted by
    # distinct pseudonymous company_ref, so it can be lower than
    # problem_confirmed_count and never higher.
    independent_confirmations: int = 0

    paid_pilot_count: int = 0

    # §7 Gate 5 asks for a *second paying business*. Distinct businesses that
    # paid, not payment events — two pilots with one customer prove retention,
    # not repeatability.
    paying_business_count: int = 0

    has_strong_buyer_signal: bool = False


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def saturating(value: float, target: float) -> float:
    """Map a raw count onto 0-100, hitting 100 at `target` and clipping above.

    Clipping rather than letting a runaway count dominate is deliberate: one
    topic with 5000 mentions should read as "clearly saturated", not as 100x
    more important than one with 50.
    """

    if target <= 0:
        return 0.0
    return clamp(value / target * 100.0)


def percent_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return (current - previous) / previous * 100.0


def score_pain(m: TopicMeasurements, config: ScoringConfig) -> ScoreBreakdown:
    weights = config.weights("pain_score")
    notes: list[str] = []

    frequency = saturating(m.mention_count, config.normalization("mention_frequency_target"))

    growth_pct = percent_change(m.mention_count, m.previous_mention_count)
    if growth_pct is None:
        # No prior window to compare against. Scored 0 rather than guessed:
        # "we cannot tell yet" must not read as "growing".
        growth_normalized = 0.0
        notes.append("growth: no prior window to compare against, scored 0")
    else:
        # Decline maps to 0, not to a negative contribution — a shrinking
        # problem is uninteresting, not actively repellent.
        growth_normalized = saturating(
            max(0.0, growth_pct), config.normalization("growth_percent_target")
        )

    severity = m.avg_severity if m.avg_severity is not None else 0.0
    if m.avg_severity is None:
        notes.append("severity: no extracted severity on any signal, scored 0")

    spread = saturating(m.distinct_regions, config.normalization("geographic_spread_target"))

    if m.search_growth_score is None:
        search = 0.0
        notes.append("search_interest: no trend data for this topic, scored 0")
    else:
        search = saturating(
            m.search_growth_score, config.normalization("search_interest_growth_target")
        )

    dimensions = [
        Dimension("mention_frequency", m.mention_count, frequency, weights["mention_frequency"]),
        Dimension("growth", growth_pct, growth_normalized, weights["growth"]),
        Dimension("severity", m.avg_severity, clamp(severity), weights["severity"]),
        Dimension("geographic_spread", m.distinct_regions, spread, weights["geographic_spread"]),
        Dimension("search_interest", m.search_growth_score, search, weights["search_interest"]),
    ]

    return ScoreBreakdown(
        score=clamp(sum(d.contribution for d in dimensions)),
        dimensions=dimensions,
        notes=notes,
    )


def score_commercial(m: TopicMeasurements, config: ScoringConfig) -> ScoreBreakdown:
    weights = config.weights("commercial_score")
    notes: list[str] = []

    # What share of signals actually named who would pay. §5 insists the buyer
    # is stored separately from the affected user precisely because "someone is
    # annoyed" and "someone will pay" are different claims.
    if m.mention_count > 0:
        payer_clarity = clamp(m.signals_with_payer / m.mention_count * 100.0)
    else:
        payer_clarity = 0.0

    recurrence = config.recurrence_score(m.dominant_frequency_hint)
    economic_impact = m.avg_economic_impact if m.avg_economic_impact is not None else 0.0
    if m.avg_economic_impact is None:
        notes.append("economic_impact: not extracted on any signal, scored 0")

    fit = config.implementation_fit(m.topic_slug, m.parent_slug)
    urgency = m.avg_urgency if m.avg_urgency is not None else 0.0

    commercial_evidence = score_commercial_evidence(m)
    if commercial_evidence == 0.0:
        notes.append(
            "commercial_evidence: no interviews, pilots or paying customers recorded "
            "(record them via POST /api/v1/opportunities/{id}/interviews and /evidence)"
        )

    dimensions = [
        Dimension("payer_clarity", m.signals_with_payer, payer_clarity, weights["payer_clarity"]),
        Dimension("recurrence", m.dominant_frequency_hint, recurrence, weights["recurrence"]),
        Dimension(
            "economic_impact", m.avg_economic_impact, clamp(economic_impact), weights["economic_impact"]
        ),
        Dimension("implementation_fit", m.topic_slug, fit, weights["implementation_fit"]),
        Dimension("urgency", m.avg_urgency, clamp(urgency), weights["urgency"]),
        Dimension(
            "commercial_evidence",
            {
                "interviews": m.interview_count,
                "problem_confirmed": m.problem_confirmed_count,
                "independent_confirmations": m.independent_confirmations,
                "paid_pilots": m.paid_pilot_count,
                "paying_businesses": m.paying_business_count,
                "strong_commercial_signal": m.has_strong_buyer_signal,
            },
            commercial_evidence,
            weights["commercial_evidence"],
        ),
    ]

    return ScoreBreakdown(
        score=clamp(sum(d.contribution for d in dimensions)),
        dimensions=dimensions,
        notes=notes,
    )


def score_commercial_evidence(m: TopicMeasurements) -> float:
    """§31's evidence hierarchy, collapsed to 0-100.

    The ordering is the point: a repeat paying customer outranks a paid pilot,
    which outranks a confirmed problem, which outranks an interview that
    happened. §29 — "Paid evidence must outrank inferred social evidence" — is
    enforced here by construction rather than by weighting luck.
    """

    if m.paying_business_count >= 2:
        return 100.0
    if m.paid_pilot_count >= 1:
        return 85.0
    if m.problem_confirmed_count >= 2:
        return 60.0
    if m.problem_confirmed_count == 1:
        return 40.0
    if m.interview_count >= 1:
        return 20.0
    return 0.0


def score_confidence(m: TopicMeasurements, config: ScoringConfig, as_of: date) -> ScoreBreakdown:
    weights = config.weights("confidence_score")

    diversity = saturating(m.distinct_sources, config.normalization("source_diversity_target"))
    sample = saturating(m.mention_count, config.normalization("sample_size_target"))

    if m.latest_signal_date is None:
        recency = 0.0
    else:
        age_days = (as_of - m.latest_signal_date).days
        halflife = config.normalization("data_recency_halflife_days")
        recency = clamp(100.0 * max(0.0, 1.0 - age_days / halflife)) if halflife > 0 else 0.0

    # Any confirmed-by-a-human evidence is what makes a finding trustworthy
    # rather than merely plausible — this is the same hierarchy as §31.
    validation = score_commercial_evidence(m)

    classification = (
        m.avg_classification_confidence if m.avg_classification_confidence is not None else 0.0
    )

    dimensions = [
        Dimension("source_diversity", m.distinct_sources, diversity, weights["source_diversity"]),
        Dimension("sample_size", m.mention_count, sample, weights["sample_size"]),
        Dimension("data_recency", m.latest_signal_date, recency, weights["data_recency"]),
        Dimension(
            "commercial_validation", m.problem_confirmed_count, validation, weights["commercial_validation"]
        ),
        Dimension(
            "classification_confidence",
            m.avg_classification_confidence,
            clamp(classification),
            weights["classification_confidence"],
        ),
    ]

    return ScoreBreakdown(
        score=clamp(sum(d.contribution for d in dimensions)), dimensions=dimensions
    )


@dataclass(frozen=True)
class OpportunityScores:
    pain: ScoreBreakdown
    commercial: ScoreBreakdown
    confidence: ScoreBreakdown
    opportunity: ScoreBreakdown
    recommendation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pain_score": self.pain.to_dict(),
            "commercial_score": self.commercial.to_dict(),
            "confidence_score": self.confidence.to_dict(),
            "opportunity_score": self.opportunity.to_dict(),
            "recommendation": self.recommendation,
        }


def is_commercially_validated(m: TopicMeasurements) -> bool:
    """Whether a human has established this is real, per §7's gates.

    Money already changing hands (§7 Gate 4, "A customer pays money") clears
    this on its own — it is strictly stronger evidence than Gate 3's
    "multiple businesses confirm + one strong commercial signal", and requiring
    a paid pilot to *also* collect two interview confirmations would let the
    §29 cap suppress the one thing the spec most wants surfaced.

    Absent payment, Gate 3's full bar applies.
    """

    if m.paid_pilot_count >= 1 or m.paying_business_count >= 1:
        return True

    return m.independent_confirmations >= 2 and m.has_strong_buyer_signal


def score_opportunity(
    m: TopicMeasurements, config: ScoringConfig, as_of: date
) -> OpportunityScores:
    pain = score_pain(m, config)
    commercial = score_commercial(m, config)
    confidence = score_confidence(m, config, as_of)

    weights = config.weights("opportunity_score")
    raw = pain.score * weights["pain_score"] + commercial.score * weights["commercial_score"]

    notes: list[str] = []
    score = raw

    # §29's "Later:" bonuses. Applied to the blended score rather than to the
    # commercial_evidence dimension — see config/scoring.yaml for why that
    # reading is the one that actually delivers the clause's stated purpose.
    if m.paid_pilot_count >= 1:
        bonus = config.paid_pilot_bonus()
        score += bonus
        notes.append(f"+{bonus:g} paid pilot bonus (§29)")

    if m.paying_business_count >= 2:
        bonus = config.repeat_customer_bonus()
        score += bonus
        notes.append(f"+{bonus:g} repeat paying customer bonus (§29)")

    score = clamp(score)

    # §29: an opportunity nobody has validated cannot present as a top-tier
    # certainty, however persuasive the inferred signals look.
    if not is_commercially_validated(m):
        cap = config.opportunity_cap_without_commercial_validation()
        if score > cap:
            notes.append(
                f"capped at {cap:g} — not commercially validated "
                f"(uncapped {score:.2f}); see PROJECT_SPEC.md §29"
            )
            score = cap

    dimensions = [
        Dimension("pain_score", pain.score, pain.score, weights["pain_score"]),
        Dimension("commercial_score", commercial.score, commercial.score, weights["commercial_score"]),
    ]

    opportunity = ScoreBreakdown(score=score, dimensions=dimensions, notes=notes)

    return OpportunityScores(
        pain=pain,
        commercial=commercial,
        confidence=confidence,
        opportunity=opportunity,
        recommendation=recommend(
            m, config, commercial.score, confidence.score, opportunity.score
        ),
    )


# §34's vocabulary.
IGNORE = "IGNORE"
WATCH = "WATCH"
INVESTIGATE = "INVESTIGATE"
VALIDATE = "VALIDATE"
SELL_PILOT = "SELL_PILOT"
PRODUCTIZE = "PRODUCTIZE"


def recommend(
    m: TopicMeasurements,
    config: ScoringConfig,
    commercial_score: float,
    confidence_score: float,
    opportunity_score: float,
) -> str:
    """§35's deterministic state machine.

    Evaluated in the spec's own order. §35 is explicit that "LLM can explain the
    recommendation. LLM should not decide the status itself." — hence a plain
    rule chain with every threshold read from config.

    The most-advanced states are checked first: a topic with paying customers
    should read PRODUCTIZE even though it also satisfies every earlier rule.
    """

    if m.paying_business_count >= config.recommendation_rule("productize_min_paid_customers"):
        return PRODUCTIZE

    if m.has_strong_buyer_signal or m.paid_pilot_count >= 1:
        return SELL_PILOT

    if commercial_score < config.recommendation_rule("ignore_below_commercial_score"):
        return IGNORE

    if confidence_score < config.recommendation_rule("watch_below_confidence"):
        return WATCH

    if m.problem_confirmed_count >= config.recommendation_rule("validate_min_problem_confirmed"):
        return VALIDATE

    if (
        opportunity_score >= config.recommendation_rule("investigate_min_opportunity_score")
        and m.interview_count == 0
    ):
        return INVESTIGATE

    return WATCH
