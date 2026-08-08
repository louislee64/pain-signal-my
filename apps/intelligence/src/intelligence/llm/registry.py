"""LLM provider registry (PROJECT_SPEC.md §25).

Adding a provider — OpenAI, Gemini, a local model — means writing an
`LLMProvider` subclass and adding one line here. Nothing in the extraction
pipeline, the eval harness, or the CLI changes.
"""

from intelligence.llm.base import LLMProvider
from intelligence.llm.fixture_provider import FixtureProvider

LLM_PROVIDER_REGISTRY: dict[str, type[LLMProvider]] = {
    FixtureProvider.name: FixtureProvider,
}

try:  # pragma: no cover - import guard, not logic
    from intelligence.llm.anthropic_provider import AnthropicProvider

    LLM_PROVIDER_REGISTRY[AnthropicProvider.name] = AnthropicProvider
except ImportError:  # pragma: no cover
    # The adapter module itself imports nothing vendor-specific at module level,
    # so this should not trigger. Guarded anyway: a registry that fails to import
    # would take down the fixture provider too, and with it the whole test suite.
    pass


def get_llm_provider_class(name: str) -> type[LLMProvider]:
    try:
        return LLM_PROVIDER_REGISTRY[name]
    except KeyError:
        registered = ", ".join(sorted(LLM_PROVIDER_REGISTRY)) or "(none)"
        raise ValueError(
            f"No LLM provider registered for '{name}'. Registered: {registered}"
        ) from None


def build_llm_provider(name: str, config: dict | None = None) -> LLMProvider:
    return get_llm_provider_class(name)(config or {})
