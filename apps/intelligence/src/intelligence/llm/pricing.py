"""Per-model token pricing for cost estimation (PROJECT_SPEC.md §44).

USD per million tokens, as published by each provider. These are estimates for
budgeting, not billing: the authoritative number is the provider's invoice.
`ai_usage.estimated_cost` is named accordingly.

Prices change. When a rate here drifts from the provider's current pricing the
budget guard drifts with it, so treat this table as something to review rather
than something that stays true on its own.
"""

# {model_id: (input_usd_per_mtok, output_usd_per_mtok)}
PRICING: dict[str, tuple[float, float]] = {
    # Anthropic (platform.claude.com/docs/en/pricing), checked 2026-08-08.
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

TOKENS_PER_MILLION = 1_000_000


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimated USD for one call. Returns 0.0 for an unpriced model.

    Zero rather than a raise: a missing price must never stop an extraction that
    the operator already authorised. The gap is instead made visible by
    `is_priced()`, which the budget guard checks — an unpriced model cannot be
    budget-enforced, and that is worth reporting rather than silently treating
    as free.
    """

    rates = PRICING.get(model)
    if rates is None:
        return 0.0

    input_rate, output_rate = rates
    return (
        input_tokens / TOKENS_PER_MILLION * input_rate
        + output_tokens / TOKENS_PER_MILLION * output_rate
    )


def is_priced(model: str) -> bool:
    return model in PRICING
