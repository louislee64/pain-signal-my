"""§24: "Validate all LLM output with JSON Schema/Pydantic. Reject malformed
results." These tests are that rejection, stated as behaviour."""

import pytest
from pydantic import ValidationError

from intelligence.llm.schemas import BuyerType, Frequency, ProblemExtraction


def test_minimal_extraction_defaults_to_nothing_claimed():
    extraction = ProblemExtraction(problem_present=False)

    assert extraction.topic is None
    assert extraction.buyer_type is BuyerType.UNKNOWN
    assert extraction.frequency is Frequency.UNKNOWN
    # The safe default for every score is 0, not a midpoint. An unstated
    # severity must not read as "moderately severe" once it reaches scoring.
    assert extraction.severity == 0
    assert extraction.confidence == 0.0


def test_scores_outside_0_100_are_rejected():
    for field, value in [("severity", 101), ("economic_impact", -1), ("urgency", 1000)]:
        with pytest.raises(ValidationError):
            ProblemExtraction(problem_present=True, **{field: value})


def test_confidence_outside_0_1_is_rejected():
    with pytest.raises(ValidationError):
        ProblemExtraction(problem_present=True, confidence=1.5)


def test_invented_buyer_type_is_rejected():
    # A model that returns a plausible-but-unlisted buyer ("procurement_head")
    # must fail here rather than produce a payer_type no scoring rule handles.
    with pytest.raises(ValidationError):
        ProblemExtraction(problem_present=True, buyer_type="procurement_head")


def test_invented_frequency_is_rejected():
    with pytest.raises(ValidationError):
        ProblemExtraction(problem_present=True, frequency="hourly")


def test_extra_fields_are_rejected():
    # The signature of a drifting model version or a successful prompt
    # injection: output that carries fields nobody asked for.
    with pytest.raises(ValidationError):
        ProblemExtraction(
            problem_present=True,
            is_good_business_opportunity=True,
            market_size_usd=1_000_000,
        )


def test_summary_length_is_bounded():
    with pytest.raises(ValidationError):
        ProblemExtraction(problem_present=True, problem_summary="x" * 501)


def test_schema_does_not_ask_the_model_to_judge_opportunity():
    """§24 is explicit that the LLM must NOT be asked "is this a good business
    opportunity?" — that belongs to the deterministic engine. This asserts the
    schema itself never grows such a field."""

    forbidden = {"opportunity", "market_size", "revenue", "should_build", "recommendation", "score"}
    fields = set(ProblemExtraction.model_fields)

    assert not {f for f in fields if any(word in f for word in forbidden)}
