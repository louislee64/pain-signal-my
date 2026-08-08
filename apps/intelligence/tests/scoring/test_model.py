"""Exhaustive scoring tests (PROJECT_SPEC.md §71: "Write exhaustive tests").

These pin the ARITHMETIC and the INVARIANTS, not the specific weight values —
config/scoring.yaml holds a starting hypothesis that §57 expects to be
recalibrated against real commercial outcomes, and a test suite that breaks
every time a weight is tuned would punish exactly the feedback loop the whole
system exists to run. Where a test does depend on a value, it derives it from
the loaded config rather than restating a literal.
"""

from datetime import date, timedelta
from pathlib import Path

import pytest

from intelligence.scoring.config import ScoringConfigError, load_scoring_config
from intelligence.scoring.model import (
    IGNORE,
    INVESTIGATE,
    PRODUCTIZE,
    SELL_PILOT,
    VALIDATE,
    WATCH,
    TopicMeasurements,
    percent_change,
    saturating,
    score_commercial,
    score_commercial_evidence,
    score_confidence,
    score_opportunity,
    score_pain,
)

CONFIG_PATH = str(Path(__file__).parent.parent.parent.parent.parent / "config" / "scoring.yaml")
TODAY = date(2026, 8, 8)


@pytest.fixture(scope="module")
def config():
    return load_scoring_config(CONFIG_PATH)


def measurements(**overrides) -> TopicMeasurements:
    base = dict(topic_slug="billing_invoice", mention_count=10, previous_mention_count=10)
    base.update(overrides)
    return TopicMeasurements(**base)


# --------------------------------------------------------------------------
# Normalization helpers
# --------------------------------------------------------------------------

def test_saturating_reaches_100_at_target():
    assert saturating(50, 50) == 100.0


def test_saturating_clips_above_target():
    # One topic with a runaway count should read "clearly saturated", not
    # "100x more important".
    assert saturating(5000, 50) == 100.0


def test_saturating_is_linear_below_target():
    assert saturating(25, 50) == 50.0


def test_saturating_handles_zero_target_without_dividing_by_zero():
    assert saturating(10, 0) == 0.0


def test_percent_change_returns_none_from_a_zero_base():
    assert percent_change(10, 0) is None


def test_percent_change_computes_growth_and_decline():
    assert percent_change(20, 10) == 100.0
    assert percent_change(5, 10) == -50.0


# --------------------------------------------------------------------------
# Pain score (§26)
# --------------------------------------------------------------------------

def test_pain_score_is_zero_when_nothing_is_measured(config):
    result = score_pain(TopicMeasurements(topic_slug="billing_invoice"), config)
    assert result.score == 0.0


def test_pain_score_is_bounded_to_100_with_everything_maxed(config):
    result = score_pain(
        measurements(
            mention_count=10_000,
            previous_mention_count=1,
            avg_severity=100,
            distinct_regions=99,
            search_growth_score=99.0,
        ),
        config,
    )
    assert result.score == 100.0


def test_pain_dimensions_sum_to_the_score(config):
    result = score_pain(
        measurements(mention_count=25, previous_mention_count=10, avg_severity=60, distinct_regions=3),
        config,
    )
    total = sum(d.contribution for d in result.dimensions)
    assert result.score == pytest.approx(total)


def test_pain_score_declining_topic_scores_zero_growth_not_negative(config):
    # A shrinking problem is uninteresting, not actively repellent — it must
    # not drag the other dimensions down.
    declining = score_pain(measurements(mention_count=5, previous_mention_count=50, avg_severity=80), config)
    growth = next(d for d in declining.dimensions if d.name == "growth")

    assert growth.normalized == 0.0
    assert growth.contribution == 0.0
    assert declining.score > 0  # severity still counts


def test_pain_score_records_a_note_when_growth_has_no_prior_window(config):
    result = score_pain(measurements(mention_count=10, previous_mention_count=0), config)
    assert any("no prior window" in n for n in result.notes)


def test_pain_score_missing_search_data_scores_zero_and_says_so(config):
    result = score_pain(measurements(search_growth_score=None), config)
    assert any("search_interest" in n for n in result.notes)


def test_pain_score_rises_with_wider_geographic_spread(config):
    narrow = score_pain(measurements(distinct_regions=1), config).score
    wide = score_pain(measurements(distinct_regions=5), config).score
    assert wide > narrow


# --------------------------------------------------------------------------
# Commercial score (§27) and the evidence hierarchy (§31)
# --------------------------------------------------------------------------

def test_commercial_score_payer_clarity_is_the_share_of_signals_naming_a_buyer(config):
    result = score_commercial(measurements(mention_count=10, signals_with_payer=5), config)
    payer = next(d for d in result.dimensions if d.name == "payer_clarity")
    assert payer.normalized == 50.0


def test_commercial_score_payer_clarity_is_zero_with_no_mentions(config):
    result = score_commercial(measurements(mention_count=0, signals_with_payer=0), config)
    payer = next(d for d in result.dimensions if d.name == "payer_clarity")
    assert payer.normalized == 0.0


def test_recurrence_ranks_daily_above_weekly_above_monthly_above_unknown(config):
    scores = [
        score_commercial(measurements(dominant_frequency_hint=hint), config).score
        for hint in ("daily", "weekly", "monthly", None)
    ]
    assert scores == sorted(scores, reverse=True)


def test_implementation_fit_penalises_topics_software_cannot_solve(config):
    # §28 exists precisely to stop a high-pain, low-fit problem climbing the
    # ranking. Cost pressure is real but not fixable by shipping software.
    software = score_commercial(measurements(topic_slug="billing_invoice"), config)
    not_software = score_commercial(measurements(topic_slug="price_cost_pressure"), config)

    software_fit = next(d for d in software.dimensions if d.name == "implementation_fit")
    other_fit = next(d for d in not_software.dimensions if d.name == "implementation_fit")

    assert software_fit.normalized > other_fit.normalized
    assert software.score > not_software.score


def test_subtopics_inherit_their_parents_implementation_fit(config):
    parent = score_commercial(measurements(topic_slug="billing_invoice"), config)
    child = score_commercial(measurements(topic_slug="einvoice", parent_slug="billing_invoice"), config)

    parent_fit = next(d for d in parent.dimensions if d.name == "implementation_fit")
    child_fit = next(d for d in child.dimensions if d.name == "implementation_fit")

    assert child_fit.normalized == parent_fit.normalized


def test_unknown_topic_falls_back_to_the_configured_default_fit(config):
    result = score_commercial(measurements(topic_slug="not_in_the_config_at_all"), config)
    fit = next(d for d in result.dimensions if d.name == "implementation_fit")
    assert fit.normalized == config.implementation_fit("not_in_the_config_at_all")


def test_evidence_hierarchy_orders_paid_above_confirmed_above_interviewed():
    """§29: "Paid evidence must outrank inferred social evidence."."""
    nothing = score_commercial_evidence(TopicMeasurements(topic_slug="t"))
    interviewed = score_commercial_evidence(TopicMeasurements(topic_slug="t", interview_count=3))
    confirmed_once = score_commercial_evidence(TopicMeasurements(topic_slug="t", problem_confirmed_count=1))
    confirmed_twice = score_commercial_evidence(TopicMeasurements(topic_slug="t", problem_confirmed_count=2))
    piloted = score_commercial_evidence(TopicMeasurements(topic_slug="t", paid_pilot_count=1))
    repeat_paying = score_commercial_evidence(TopicMeasurements(topic_slug="t", paid_customer_count=2))

    assert nothing < interviewed < confirmed_once < confirmed_twice < piloted < repeat_paying
    assert repeat_paying == 100.0


def test_a_paid_pilot_beats_any_amount_of_interviewing():
    many_interviews = TopicMeasurements(topic_slug="t", interview_count=50)
    one_pilot = TopicMeasurements(topic_slug="t", paid_pilot_count=1)

    assert score_commercial_evidence(one_pilot) > score_commercial_evidence(many_interviews)


# --------------------------------------------------------------------------
# Confidence (§30)
# --------------------------------------------------------------------------

def test_confidence_is_zero_with_no_evidence_at_all(config):
    result = score_confidence(TopicMeasurements(topic_slug="t"), config, TODAY)
    assert result.score == 0.0


def test_confidence_rises_with_source_diversity(config):
    single = score_confidence(measurements(distinct_sources=1), config, TODAY).score
    several = score_confidence(measurements(distinct_sources=3), config, TODAY).score
    assert several > single


def test_confidence_decays_as_data_gets_stale(config):
    fresh = score_confidence(measurements(latest_signal_date=TODAY), config, TODAY).score
    old = score_confidence(measurements(latest_signal_date=TODAY - timedelta(days=25)), config, TODAY).score
    assert fresh > old


def test_confidence_recency_floors_at_zero_for_very_old_data(config):
    ancient = score_confidence(
        measurements(latest_signal_date=TODAY - timedelta(days=3650)), config, TODAY
    )
    recency = next(d for d in ancient.dimensions if d.name == "data_recency")
    assert recency.normalized == 0.0


def test_confidence_is_independent_of_opportunity_score(config):
    """§30: a high opportunity score with low confidence must be expressible —
    "looks attractive, but the evidence is still weak"."""
    thin_but_promising = measurements(
        mention_count=3,
        previous_mention_count=1,
        avg_severity=95,
        avg_economic_impact=95,
        avg_urgency=95,
        signals_with_payer=3,
        dominant_frequency_hint="daily",
        distinct_sources=1,
        latest_signal_date=TODAY,
    )
    result = score_opportunity(thin_but_promising, config, TODAY)

    assert result.opportunity.score > result.confidence.score


# --------------------------------------------------------------------------
# Opportunity score (§29)
# --------------------------------------------------------------------------

def test_opportunity_blends_pain_and_commercial_by_configured_weights(config):
    m = measurements(
        mention_count=20, previous_mention_count=10, avg_severity=70,
        avg_economic_impact=70, avg_urgency=70, signals_with_payer=20,
        dominant_frequency_hint="daily",
        # Validated via Gate 3 (confirmations + strong buyer signal) rather than
        # via payment, so the cap does not apply and no §29 bonus is added —
        # leaving the bare blend to assert against.
        problem_confirmed_count=2, has_strong_buyer_signal=True,
    )
    result = score_opportunity(m, config, TODAY)
    weights = config.weights("opportunity_score")

    expected = (
        result.pain.score * weights["pain_score"]
        + result.commercial.score * weights["commercial_score"]
    )
    assert result.opportunity.score == pytest.approx(expected)
    assert result.opportunity.notes == []


def test_paid_pilot_adds_the_configured_bonus(config):
    """A paid pilot legitimately moves the score twice — it lifts the §27
    commercial_evidence dimension *and* adds §29's bonus. This isolates the
    bonus by measuring it against the blend of this same result's own
    pain/commercial scores, so the dimension effect is already accounted for.
    """
    result = score_opportunity(
        measurements(
            mention_count=20, previous_mention_count=10, avg_severity=70,
            avg_economic_impact=70, avg_urgency=70, signals_with_payer=20,
            dominant_frequency_hint="daily", problem_confirmed_count=2,
            paid_pilot_count=1,
        ),
        config,
        TODAY,
    )
    weights = config.weights("opportunity_score")
    blend = (
        result.pain.score * weights["pain_score"]
        + result.commercial.score * weights["commercial_score"]
    )

    assert result.opportunity.score == pytest.approx(blend + config.paid_pilot_bonus())
    assert any("paid pilot bonus" in n for n in result.opportunity.notes)


def test_a_pilot_also_lifts_the_commercial_evidence_dimension(config):
    base = dict(
        mention_count=20, previous_mention_count=10, avg_severity=70,
        avg_economic_impact=70, avg_urgency=70, signals_with_payer=20,
        dominant_frequency_hint="daily", problem_confirmed_count=2,
    )
    without = score_commercial(measurements(**base), config)
    with_pilot = score_commercial(measurements(**base, paid_pilot_count=1), config)

    before = next(d for d in without.dimensions if d.name == "commercial_evidence")
    after = next(d for d in with_pilot.dimensions if d.name == "commercial_evidence")

    assert after.normalized > before.normalized


def test_repeat_paying_customers_add_a_larger_bonus_than_a_single_pilot(config):
    base_inputs = dict(
        mention_count=20, previous_mention_count=10, avg_severity=70,
        avg_economic_impact=70, avg_urgency=70, signals_with_payer=20,
        dominant_frequency_hint="daily", problem_confirmed_count=2,
    )
    pilot_only = score_opportunity(measurements(**base_inputs, paid_pilot_count=1), config, TODAY)
    repeat = score_opportunity(
        measurements(**base_inputs, paid_pilot_count=1, paid_customer_count=2), config, TODAY
    )

    assert config.repeat_customer_bonus() > config.paid_pilot_bonus()
    assert repeat.opportunity.score > pilot_only.opportunity.score


def test_a_paid_pilot_alone_counts_as_commercial_validation(config):
    """§7 Gate 4 — "A customer pays money" — is strictly stronger evidence than
    Gate 3, so it must clear the §29 cap on its own rather than also requiring
    interview confirmations."""
    paid = measurements(
        mention_count=10_000, previous_mention_count=1, avg_severity=100,
        distinct_regions=99, search_growth_score=99.0, avg_economic_impact=100,
        avg_urgency=100, signals_with_payer=10_000, dominant_frequency_hint="daily",
        paid_pilot_count=1,
    )
    result = score_opportunity(paid, config, TODAY)

    assert not any("capped" in n for n in result.opportunity.notes)
    assert result.opportunity.score > config.opportunity_cap_without_commercial_validation()


def test_commercial_is_weighted_above_pain(config):
    """§29: "Commercial evidence deliberately weighs slightly more heavily."."""
    weights = config.weights("opportunity_score")
    assert weights["commercial_score"] > weights["pain_score"]


def test_uncommercially_validated_opportunity_is_capped(config):
    # Everything inferred is maxed, but no human has confirmed anything.
    speculative = measurements(
        mention_count=10_000, previous_mention_count=1, avg_severity=100,
        distinct_regions=99, search_growth_score=99.0, avg_economic_impact=100,
        avg_urgency=100, signals_with_payer=10_000, dominant_frequency_hint="daily",
    )
    result = score_opportunity(speculative, config, TODAY)
    cap = config.opportunity_cap_without_commercial_validation()

    assert result.opportunity.score == cap
    assert any("capped" in n for n in result.opportunity.notes)


def test_commercial_validation_lifts_an_opportunity_above_the_cap(config):
    inputs = dict(
        mention_count=10_000, previous_mention_count=1, avg_severity=100,
        distinct_regions=99, search_growth_score=99.0, avg_economic_impact=100,
        avg_urgency=100, signals_with_payer=10_000, dominant_frequency_hint="daily",
    )
    cap = config.opportunity_cap_without_commercial_validation()

    speculative = score_opportunity(measurements(**inputs), config, TODAY)
    validated = score_opportunity(
        measurements(**inputs, problem_confirmed_count=2, paid_pilot_count=1), config, TODAY
    )

    assert speculative.opportunity.score == cap
    assert validated.opportunity.score > cap


def test_real_paying_customers_outrank_pure_speculation(config):
    """§29's whole purpose: "This stops AI-generated speculation from
    outranking actual paying customers."."""
    speculation = score_opportunity(
        measurements(
            mention_count=10_000, previous_mention_count=1, avg_severity=100,
            distinct_regions=99, search_growth_score=99.0, avg_economic_impact=100,
            avg_urgency=100, signals_with_payer=10_000, dominant_frequency_hint="daily",
        ),
        config,
        TODAY,
    )
    modest_but_paid = score_opportunity(
        measurements(
            mention_count=8, previous_mention_count=6, avg_severity=55,
            avg_economic_impact=55, avg_urgency=50, signals_with_payer=6,
            dominant_frequency_hint="weekly",
            problem_confirmed_count=3, paid_pilot_count=1, paid_customer_count=2,
        ),
        config,
        TODAY,
    )

    assert modest_but_paid.opportunity.score > speculation.opportunity.score


def test_every_score_is_explainable_through_stored_components(config):
    """Milestone 4's acceptance criterion."""
    result = score_opportunity(
        measurements(mention_count=20, previous_mention_count=10, avg_severity=70), config, TODAY
    )
    payload = result.to_dict()

    for score_name in ("pain_score", "commercial_score", "confidence_score", "opportunity_score"):
        assert "score" in payload[score_name]
        assert payload[score_name]["dimensions"], f"{score_name} must expose its dimensions"
        for dimension in payload[score_name]["dimensions"].values():
            assert {"raw", "normalized", "weight", "contribution"} <= set(dimension)


def test_stored_components_reconstruct_the_headline_score(config):
    result = score_opportunity(
        measurements(mention_count=20, previous_mention_count=10, avg_severity=70), config, TODAY
    )
    pain = result.to_dict()["pain_score"]
    recomputed = sum(d["contribution"] for d in pain["dimensions"].values())

    assert pain["score"] == pytest.approx(recomputed, abs=0.05)


# --------------------------------------------------------------------------
# Recommendation state machine (§35)
# --------------------------------------------------------------------------

def test_low_commercial_score_is_ignored(config):
    result = score_opportunity(measurements(topic_slug="price_cost_pressure"), config, TODAY)
    assert result.recommendation == IGNORE


def test_thin_evidence_is_watched_not_investigated(config):
    result = score_opportunity(
        measurements(
            mention_count=2, avg_economic_impact=90, avg_urgency=90,
            signals_with_payer=2, dominant_frequency_hint="daily", distinct_sources=1,
        ),
        config,
        TODAY,
    )
    assert result.recommendation == WATCH


def test_strong_uninterviewed_opportunity_is_investigated(config):
    result = score_opportunity(
        measurements(
            mention_count=40, previous_mention_count=10, avg_severity=85,
            distinct_regions=5, search_growth_score=2.0, avg_economic_impact=85,
            avg_urgency=85, signals_with_payer=40, dominant_frequency_hint="daily",
            distinct_sources=3, avg_classification_confidence=90,
            latest_signal_date=TODAY, interview_count=0,
        ),
        config,
        TODAY,
    )
    assert result.recommendation == INVESTIGATE


def test_confirmed_problem_moves_to_validate(config):
    threshold = int(config.recommendation_rule("validate_min_problem_confirmed"))
    result = score_opportunity(
        measurements(
            mention_count=30, avg_severity=80, avg_economic_impact=80, avg_urgency=80,
            signals_with_payer=30, dominant_frequency_hint="daily", distinct_sources=3,
            avg_classification_confidence=90, latest_signal_date=TODAY,
            problem_confirmed_count=threshold, interview_count=5,
        ),
        config,
        TODAY,
    )
    assert result.recommendation == VALIDATE


def test_a_strong_buyer_signal_means_sell_pilot(config):
    result = score_opportunity(
        measurements(
            mention_count=30, avg_severity=80, avg_economic_impact=80, avg_urgency=80,
            signals_with_payer=30, dominant_frequency_hint="daily", distinct_sources=3,
            latest_signal_date=TODAY, problem_confirmed_count=3, has_strong_buyer_signal=True,
        ),
        config,
        TODAY,
    )
    assert result.recommendation == SELL_PILOT


def test_repeat_paying_customers_mean_productize(config):
    threshold = int(config.recommendation_rule("productize_min_paid_customers"))
    result = score_opportunity(
        measurements(
            mention_count=30, avg_severity=80, avg_economic_impact=80, avg_urgency=80,
            signals_with_payer=30, dominant_frequency_hint="daily", distinct_sources=3,
            latest_signal_date=TODAY, problem_confirmed_count=3,
            paid_pilot_count=2, paid_customer_count=threshold,
        ),
        config,
        TODAY,
    )
    assert result.recommendation == PRODUCTIZE


def test_productize_wins_over_earlier_states_it_also_satisfies(config):
    # A topic with paying customers also satisfies SELL_PILOT and VALIDATE; the
    # most advanced state must win.
    result = score_opportunity(
        measurements(
            mention_count=30, avg_severity=80, avg_economic_impact=80, avg_urgency=80,
            signals_with_payer=30, dominant_frequency_hint="daily", distinct_sources=3,
            latest_signal_date=TODAY, problem_confirmed_count=5,
            paid_pilot_count=3, paid_customer_count=5, has_strong_buyer_signal=True,
        ),
        config,
        TODAY,
    )
    assert result.recommendation == PRODUCTIZE


def test_recommendation_is_always_one_of_the_documented_states(config):
    """§34 fixes the vocabulary; nothing may invent a seventh state."""
    allowed = {IGNORE, WATCH, INVESTIGATE, VALIDATE, SELL_PILOT, PRODUCTIZE}

    for mentions in (0, 1, 5, 50, 500):
        for confirmed in (0, 1, 3):
            for pilots in (0, 1):
                for customers in (0, 1, 5):
                    result = score_opportunity(
                        measurements(
                            mention_count=mentions,
                            previous_mention_count=1,
                            avg_severity=50,
                            avg_economic_impact=50,
                            avg_urgency=50,
                            signals_with_payer=mentions,
                            dominant_frequency_hint="weekly",
                            distinct_sources=2,
                            latest_signal_date=TODAY,
                            problem_confirmed_count=confirmed,
                            paid_pilot_count=pilots,
                            paid_customer_count=customers,
                        ),
                        config,
                        TODAY,
                    )
                    assert result.recommendation in allowed


# --------------------------------------------------------------------------
# Config loading
# --------------------------------------------------------------------------

def test_missing_config_file_fails_loudly():
    with pytest.raises(ScoringConfigError, match="not found"):
        load_scoring_config("/nowhere/scoring.yaml")


def test_missing_key_fails_loudly_rather_than_defaulting(tmp_path):
    """A silent default would be a hard-coded weight in disguise — exactly what
    §26 forbids — and would make a typo'd key look like a decision."""
    path = tmp_path / "scoring.yaml"
    path.write_text("version: 1\n")

    with pytest.raises(ScoringConfigError, match="pain_score.weights"):
        load_scoring_config(str(path)).weights("pain_score")


def test_shipped_config_defines_every_weight_the_engine_reads(config):
    # Guards against the config and the engine drifting apart.
    for score_name in ("pain_score", "commercial_score", "opportunity_score", "confidence_score"):
        assert config.weights(score_name)


def test_shipped_weights_sum_to_one_per_score(config):
    # Not required by the spec, but it is what makes each score land on 0-100
    # rather than some arbitrary ceiling.
    for score_name in ("pain_score", "commercial_score", "opportunity_score", "confidence_score"):
        assert sum(config.weights(score_name).values()) == pytest.approx(1.0), score_name


def test_breakdown_is_json_serializable(config):
    """Breakdowns are persisted to JSONB verbatim, so a raw value that happens
    to be a date (data_recency) or Decimal must not fail the write."""
    import json

    result = score_opportunity(
        measurements(mention_count=5, latest_signal_date=TODAY, avg_severity=50), config, TODAY
    )

    encoded = json.dumps(result.to_dict())
    assert "data_recency" in encoded
