from intelligence.llm.pricing import PRICING, estimate_cost, is_priced


def test_cost_is_per_million_tokens():
    # Opus 5: $5/MTok in, $25/MTok out.
    assert estimate_cost("claude-opus-5", 1_000_000, 0) == 5.0
    assert estimate_cost("claude-opus-5", 0, 1_000_000) == 25.0
    assert estimate_cost("claude-opus-5", 1_000_000, 1_000_000) == 30.0


def test_realistic_per_document_call_is_a_fraction_of_a_cent():
    # ~2k in / ~200 out is the shape of one extraction. This is why ai_usage
    # stores 6 decimal places: at 2dp this rounds to $0.01, and a thousand
    # documents would appear to cost either nothing or double.
    cost = estimate_cost("claude-opus-5", 2_000, 200)

    assert 0.001 < cost < 0.02
    assert round(cost, 2) != cost


def test_unpriced_model_costs_zero_and_says_so():
    assert estimate_cost("some-future-model", 10_000, 1_000) == 0.0
    assert is_priced("some-future-model") is False
    assert is_priced("claude-opus-5") is True


def test_every_priced_model_has_output_dearer_than_input():
    # Not a law of nature, but true of every model in the table. A row that
    # breaks it is far more likely a transposed pair than a real price.
    for model, (input_rate, output_rate) in PRICING.items():
        assert output_rate > input_rate, model
