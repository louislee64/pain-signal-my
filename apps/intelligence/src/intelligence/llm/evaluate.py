"""Extraction evaluation harness (PROJECT_SPEC.md §70).

Runs every case in evaluation/cases.yaml through a provider and reports which
assertions held. §70's point is that prompt and model changes must be
*measurable*: without this, "the extraction got better" is an opinion.

The harness reports, it does not gate. A failing case is information — some
cases are genuinely hard, and a run at 10/12 with the two known-hard cases
failing is a different situation from 10/12 with the injection case failing.
Which cases fail matters more than how many, so the report always names them.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from intelligence.llm.base import PROMPT_VERSION, LLMProvider, LLMProviderError
from intelligence.llm.registry import build_llm_provider
from intelligence.llm.schemas import ProblemExtraction
from intelligence.taxonomy import load_taxonomy_hint

DEFAULT_CASES_PATH = "/app/evaluation/cases.yaml"


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    failures: list[str] = field(default_factory=list)
    error: str | None = None
    extraction: dict[str, Any] | None = None
    estimated_cost: float = 0.0


@dataclass
class EvaluationReport:
    provider: str
    model: str
    prompt_version: str
    results: list[CaseResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def estimated_cost(self) -> float:
        return sum(r.estimated_cost for r in self.results)

    @property
    def failed_case_ids(self) -> list[str]:
        return [r.case_id for r in self.results if not r.passed]


def load_cases(path: str | None = None) -> list[dict[str, Any]]:
    path = path or os.environ.get("EVAL_CASES_PATH", DEFAULT_CASES_PATH)
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    return raw.get("cases", [])


def _check(extraction: ProblemExtraction, expect: dict[str, Any]) -> list[str]:
    """Assert only what the case states. See cases.yaml on why the assertions
    are deliberately partial."""

    failures: list[str] = []

    def fail(field_name: str, expected: Any, actual: Any) -> None:
        failures.append(f"{field_name}: expected {expected!r}, got {actual!r}")

    if "problem_present" in expect and extraction.problem_present != expect["problem_present"]:
        fail("problem_present", expect["problem_present"], extraction.problem_present)

    # A case may name one acceptable topic or a set of them. Either form matches
    # against the topic OR the subtopic, since "billing_invoice" and its child
    # "reconciliation" are both correct answers to a reconciliation problem.
    if "topic" in expect or "topic_in" in expect:
        acceptable = expect.get("topic_in") or [expect["topic"]]
        got = {extraction.topic, extraction.subtopic} - {None}
        if not got & set(acceptable):
            fail("topic", acceptable, sorted(got) or None)

    if "buyer_type" in expect and extraction.buyer_type.value != expect["buyer_type"]:
        fail("buyer_type", expect["buyer_type"], extraction.buyer_type.value)

    if "frequency" in expect and extraction.frequency.value != expect["frequency"]:
        fail("frequency", expect["frequency"], extraction.frequency.value)

    if "affected_role_contains" in expect:
        needle = expect["affected_role_contains"].lower()
        role = (extraction.affected_role or "").lower()
        if needle not in role:
            fail("affected_role", f"contains {needle!r}", extraction.affected_role)

    for numeric in ("severity", "economic_impact", "urgency", "confidence"):
        if numeric not in expect:
            continue
        low, high = expect[numeric]
        actual = getattr(extraction, numeric)
        if not (low <= actual <= high):
            fail(numeric, f"between {low} and {high}", actual)

    return failures


def evaluate(
    provider: LLMProvider | None = None,
    provider_name: str = "fixture",
    provider_config: dict[str, Any] | None = None,
    cases_path: str | None = None,
) -> EvaluationReport:
    provider = provider if provider is not None else build_llm_provider(
        provider_name, provider_config or {}
    )
    provider.check_available()

    cases = load_cases(cases_path)
    taxonomy_hint = load_taxonomy_hint()

    report = EvaluationReport(
        provider=provider.name,
        model=str(getattr(provider, "model", "recorded")),
        prompt_version=PROMPT_VERSION,
    )

    for case in cases:
        text = case["text"].strip()
        try:
            result = provider.extract_problem(text, taxonomy_hint)
        except LLMProviderError as exc:
            # An error is a failed case, not a crashed run — one unrecorded
            # fixture or one API hiccup must not discard the other 11 results.
            report.results.append(CaseResult(case_id=case["id"], passed=False, error=str(exc)))
            continue

        failures = _check(result.extraction, case.get("expect", {}))
        report.results.append(
            CaseResult(
                case_id=case["id"],
                passed=not failures,
                failures=failures,
                extraction=result.extraction.model_dump(mode="json"),
                estimated_cost=result.estimated_cost,
            )
        )

    return report


def record(
    provider: LLMProvider,
    output_path: str,
    cases_path: str | None = None,
) -> dict[str, Any]:
    """Run the cases against a real provider and save the answers as fixtures.

    This is the only way recordings are created — deliberately, so a recording
    always reflects a real model response to the exact case text. Hand-written
    recordings would let the eval suite pass against answers nobody's model ever
    produced.
    """

    provider.check_available()
    cases = load_cases(cases_path)
    taxonomy_hint = load_taxonomy_hint()

    from intelligence.llm.fixture_provider import recording_key

    extractions: dict[str, Any] = {}
    for case in cases:
        text = case["text"].strip()
        result = provider.extract_problem(text, taxonomy_hint)
        extractions[recording_key(text)] = {
            "case_id": case["id"],
            "model": result.model,
            "extraction": result.extraction.model_dump(mode="json"),
        }

    payload = {
        "prompt_version": PROMPT_VERSION,
        "provider": provider.name,
        "extractions": extractions,
    }

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        import json

        json.dump(payload, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return payload
