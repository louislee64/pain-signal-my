"""Anthropic Claude adapter (PROJECT_SPEC.md §25).

The only file in this project that imports the `anthropic` SDK. Domain code
calls `LLMProvider.extract_problem()` and stays vendor-agnostic.

Installed as an optional extra (`pip install -e ".[anthropic]"`) for the same
reason as the BigQuery provider in Milestone 3: it is unusable without an API
key, and the default image should not carry a dependency that cannot run.
"""

import os
from typing import Any

from intelligence.llm.base import (
    EXTRACTION_SYSTEM_PROMPT,
    PROMPT_VERSION,
    LLMProvider,
    LLMProviderError,
)
from intelligence.llm.pricing import estimate_cost
from intelligence.llm.schemas import ExtractionResult, ProblemExtraction

# Claude Opus 5. Deliberately NOT downgraded to a cheaper tier by default:
# picking a model is a cost/quality decision that belongs to the operator, and
# config/llm.yaml is where they make it. §44's budget guard is the cost control,
# not a silently weaker model.
DEFAULT_MODEL = "claude-opus-5"

# Extraction is a short, bounded task with a fixed output schema — it does not
# need deep reasoning, and effort is the documented lever for spend. Adaptive
# thinking is left ON (the default on this model): disabling it is the more
# expensive lever in every sense and risks internal tags leaking into output.
DEFAULT_EFFORT = "low"

MAX_TOKENS = 2048


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.model = self.config.get("model", DEFAULT_MODEL)
        self.effort = self.config.get("effort", DEFAULT_EFFORT)
        self.api_key = self.config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")

    def check_available(self) -> None:
        try:
            import anthropic  # noqa: F401
        except ImportError:
            raise LLMProviderError(
                "anthropic provider needs the optional extra: "
                "pip install -e '.[anthropic]' (see docs/llm-providers.md)."
            ) from None

        if not self.api_key:
            raise LLMProviderError(
                "anthropic provider needs ANTHROPIC_API_KEY. See docs/llm-providers.md."
            )

    def extract_problem(self, text: str, taxonomy_hint: str) -> ExtractionResult:
        self.check_available()

        import anthropic

        client = anthropic.Anthropic(api_key=self.api_key)

        try:
            # messages.parse() validates the response against the Pydantic model
            # server-side via structured outputs, so a malformed extraction fails
            # here rather than downstream (§24: "Reject malformed results").
            response = client.messages.parse(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=f"{EXTRACTION_SYSTEM_PROMPT}\n\nTaxonomy:\n{taxonomy_hint}",
                output_config={"effort": self.effort},
                messages=[
                    {
                        "role": "user",
                        # Delimited so the boundary between instruction and
                        # untrusted document text is explicit — the system
                        # prompt already tells the model this block is data.
                        "content": f"<document>\n{text}\n</document>",
                    }
                ],
                output_format=ProblemExtraction,
            )
        except anthropic.APIStatusError as exc:
            raise LLMProviderError(f"anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMProviderError(f"anthropic connection error: {exc}") from exc

        # A safety decline is a content outcome, not an exception — check it
        # before reading the parsed output, which will be absent.
        if response.stop_reason == "refusal":
            raise LLMProviderError(
                "anthropic declined this document "
                f"(category: {getattr(response.stop_details, 'category', None)})"
            )

        extraction = response.parsed_output
        if extraction is None:
            raise LLMProviderError("anthropic returned no parseable extraction")

        usage = response.usage
        input_tokens = usage.input_tokens + getattr(usage, "cache_read_input_tokens", 0) or 0

        return ExtractionResult(
            extraction=extraction,
            provider=self.name,
            model=self.model,
            prompt_version=PROMPT_VERSION,
            input_tokens=input_tokens,
            output_tokens=usage.output_tokens,
            estimated_cost=estimate_cost(self.model, input_tokens, usage.output_tokens),
        )
