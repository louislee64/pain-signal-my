"""Replay provider — returns recorded extractions instead of calling an API.

This exists so the §70 evaluation harness, the extraction pipeline, and CI can
all run end-to-end at zero cost and with byte-identical results every time.

Be clear about what a fixture run does and does not prove. It exercises the
plumbing: schema validation, taxonomy mapping, signal persistence, usage
accounting, the eval scorer itself. It proves *nothing* about model quality —
the recorded answers are whatever was recorded. Measuring the model requires a
real provider, which costs money and is therefore always an explicit choice.

Recordings live in `evaluation/recordings/*.json`, keyed by the SHA-256 of the
document text, so a fixture whose text is edited stops matching rather than
silently replaying the answer to the old text.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from intelligence.llm.base import PROMPT_VERSION, LLMProvider, LLMProviderError
from intelligence.llm.schemas import ExtractionResult, ProblemExtraction


def recording_key(text: str) -> str:
    """Key a recording by its exact input text.

    Not `hashing.compute_content_hash` — that one hashes a document payload dict
    for ingestion dedup. Different job, different input, so it gets its own
    function rather than a coincidental reuse that breaks when either changes.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class FixtureProvider(LLMProvider):
    name = "fixture"

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config)
        self.recordings_path = self.config.get("recordings_path")
        self._recordings: dict[str, dict[str, Any]] | None = None

    def check_available(self) -> None:
        if not self.recordings_path:
            raise LLMProviderError(
                "fixture provider needs `recordings_path` in provider_config "
                "(e.g. evaluation/recordings/extract_problem_v1.json)."
            )
        if not Path(self.recordings_path).exists():
            raise LLMProviderError(
                f"fixture recordings not found at {self.recordings_path}. "
                "Record them with: intelligence llm record --provider anthropic"
            )

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._recordings is None:
            self.check_available()
            with open(self.recordings_path) as f:
                payload = json.load(f)

            recorded_version = payload.get("prompt_version")
            if recorded_version and recorded_version != PROMPT_VERSION:
                # Replaying answers produced by a different prompt would make an
                # eval run report on a prompt that is no longer in use.
                raise LLMProviderError(
                    f"recordings were made with prompt {recorded_version!r} but the current "
                    f"prompt is {PROMPT_VERSION!r}. Re-record before evaluating."
                )

            self._recordings = payload.get("extractions", {})
        return self._recordings

    def extract_problem(self, text: str, taxonomy_hint: str) -> ExtractionResult:
        recordings = self._load()
        key = recording_key(text)

        record = recordings.get(key)
        if record is None:
            raise LLMProviderError(
                f"no recorded extraction for this text (hash {key[:12]}). "
                "Either the fixture text changed or it was never recorded."
            )

        return ExtractionResult(
            extraction=ProblemExtraction.model_validate(record["extraction"]),
            provider=self.name,
            model=record.get("model", "recorded"),
            prompt_version=PROMPT_VERSION,
            # Zero tokens, zero cost — nothing was spent, and the ai_usage ledger
            # must not imply otherwise.
            input_tokens=0,
            output_tokens=0,
            estimated_cost=0.0,
        )
