"""The §70 harness, tested on its own terms.

These test the *scorer* — whether an assertion in cases.yaml is checked
correctly — not the model. Model quality is what a real `llm evaluate --provider
anthropic` run measures, and it costs money, so it is never part of CI.
"""

import json

import pytest

from intelligence.llm.base import PROMPT_VERSION, LLMProviderError
from intelligence.llm.evaluate import _check, evaluate, load_cases
from intelligence.llm.fixture_provider import FixtureProvider, recording_key
from intelligence.llm.schemas import BuyerType, Frequency, ProblemExtraction

from conftest import EVAL_CASES_PATH as CASES_PATH, TOPICS_REGISTRY_PATH


def extraction(**overrides) -> ProblemExtraction:
    defaults = {"problem_present": True, "topic": "billing_invoice", "confidence": 0.9}
    return ProblemExtraction(**{**defaults, **overrides})


def test_omitted_expectations_are_not_checked():
    # cases.yaml deliberately under-specifies. A case asserting only
    # problem_present must not fail because severity happened to be 3.
    assert _check(extraction(severity=3), {"problem_present": True}) == []


def test_wrong_problem_present_fails():
    failures = _check(extraction(problem_present=False), {"problem_present": True})

    assert len(failures) == 1
    assert "problem_present" in failures[0]


def test_subtopic_satisfies_a_parent_topic_expectation():
    # A reconciliation problem answered as the child slug is correct, not a miss.
    result = _check(
        extraction(topic=None, subtopic="reconciliation"),
        {"topic": "reconciliation"},
    )
    assert result == []


def test_topic_in_accepts_any_listed_topic():
    assert _check(extraction(topic="staff_operations"), {"topic_in": ["staff_operations", "x"]}) == []
    assert _check(extraction(topic="unrelated"), {"topic_in": ["staff_operations", "x"]})


def test_numeric_expectations_are_ranges():
    assert _check(extraction(severity=60), {"severity": [50, 100]}) == []
    assert _check(extraction(severity=49), {"severity": [50, 100]})
    # Inclusive at both ends — a case asserting [0, 45] means 45 passes.
    assert _check(extraction(severity=45), {"severity": [0, 45]}) == []


def test_affected_role_is_matched_case_insensitively_by_substring():
    assert _check(extraction(affected_role="Retail Cashier"), {"affected_role_contains": "cashier"}) == []
    assert _check(extraction(affected_role=None), {"affected_role_contains": "cashier"})


def test_buyer_and_frequency_are_compared_by_value():
    assert _check(
        extraction(buyer_type=BuyerType.BUSINESS_OWNER, frequency=Frequency.DAILY),
        {"buyer_type": "business_owner", "frequency": "daily"},
    ) == []


def test_all_failures_are_reported_not_just_the_first():
    failures = _check(
        extraction(problem_present=False, topic="wrong", severity=0),
        {"problem_present": True, "topic": "billing_invoice", "severity": [50, 100]},
    )

    assert len(failures) == 3


class TestShippedCases:
    """The committed case set is itself an artifact worth guarding."""

    def test_cases_load_and_cover_the_failure_modes_spec_70_names(self):
        cases = load_cases(CASES_PATH)
        ids = {case["id"] for case in cases}

        assert {
            "obvious_problem_billing",
            "no_problem_statistic",
            "spam",
            "sarcasm",
            "mixed_language_malay_english",
            "mixed_language_chinese",
            "buyer_differs_from_sufferer",
            "ambiguous_buyer",
            "multiple_problems_one_document",
            "prompt_injection",
        } <= ids

    def test_every_case_has_text_expectations_and_a_stated_reason(self):
        for case in load_cases(CASES_PATH):
            assert case.get("text", "").strip(), case["id"]
            assert case.get("expect"), case["id"]
            # A case whose purpose is not written down decays into a magic
            # assertion nobody dares change.
            assert case.get("why", "").strip(), case["id"]

    def test_case_ids_are_unique(self):
        cases = load_cases(CASES_PATH)
        assert len({c["id"] for c in cases}) == len(cases)

    def test_expected_topics_all_exist_in_the_taxonomy(self):
        import yaml

        with open(TOPICS_REGISTRY_PATH) as f:
            raw = yaml.safe_load(f)

        known = set()
        for topic in raw["topics"]:
            known.add(topic["slug"])
            known.update(sub["slug"] for sub in topic.get("subtopics", []))

        for case in load_cases(CASES_PATH):
            expect = case["expect"]
            for slug in expect.get("topic_in", []) + ([expect["topic"]] if "topic" in expect else []):
                assert slug in known, f"{case['id']} expects unknown topic {slug!r}"


class TestFixtureProvider:
    def _ideal(self, expect: dict) -> ProblemExtraction:
        """Synthesise the extraction a case is asking for.

        Only used to test the harness. A recording built this way passes by
        construction, which is the point: it isolates plumbing failures from
        model failures. Real recordings come from `llm record` against a real
        provider and pass or fail on their own merits.
        """

        fields: dict = {"problem_present": expect.get("problem_present", True)}

        topics = expect.get("topic_in") or ([expect["topic"]] if "topic" in expect else [])
        if topics:
            fields["topic"] = topics[0]
        if "buyer_type" in expect:
            fields["buyer_type"] = expect["buyer_type"]
        if "frequency" in expect:
            fields["frequency"] = expect["frequency"]
        if "affected_role_contains" in expect:
            fields["affected_role"] = expect["affected_role_contains"]
        for numeric in ("severity", "economic_impact", "urgency", "confidence"):
            if numeric in expect:
                low, high = expect[numeric]
                fields[numeric] = (low + high) / 2 if numeric == "confidence" else (low + high) // 2

        return ProblemExtraction(**fields)

    def _write_recordings(self, tmp_path, cases, prompt_version=PROMPT_VERSION):
        payload = {
            "prompt_version": prompt_version,
            "provider": "anthropic",
            "extractions": {
                recording_key(case["text"].strip()): {
                    "case_id": case["id"],
                    "model": "claude-opus-5",
                    "extraction": self._ideal(case["expect"]).model_dump(mode="json"),
                }
                for case in cases
            },
        }
        path = tmp_path / "recordings.json"
        path.write_text(json.dumps(payload))
        return str(path)

    def test_a_recording_that_matches_every_expectation_passes_every_case(self, tmp_path):
        """The harness's own correctness check: given perfect answers it must
        report a clean sweep. If this fails, a red eval run means the scorer is
        broken, not the model."""

        cases = load_cases(CASES_PATH)
        path = self._write_recordings(tmp_path, cases)

        report = evaluate(provider=FixtureProvider({"recordings_path": path}), cases_path=CASES_PATH)

        assert report.failed_case_ids == []
        assert report.passed == report.total == len(cases)

    def test_missing_recordings_file_names_the_command_that_creates_it(self, tmp_path):
        provider = FixtureProvider({"recordings_path": str(tmp_path / "nope.json")})

        with pytest.raises(LLMProviderError, match="llm record"):
            provider.check_available()

    def test_missing_path_is_an_actionable_error(self):
        with pytest.raises(LLMProviderError, match="recordings_path"):
            FixtureProvider().check_available()

    def test_recordings_from_a_different_prompt_are_refused(self, tmp_path):
        cases = load_cases(CASES_PATH)[:1]
        path = self._write_recordings(tmp_path, cases, prompt_version="extract_problem_v0")
        provider = FixtureProvider({"recordings_path": path})

        # Replaying v0 answers would report on a prompt that is no longer in use.
        with pytest.raises(LLMProviderError, match="Re-record"):
            provider.extract_problem(cases[0]["text"].strip(), "")

    def test_edited_case_text_stops_matching_its_recording(self, tmp_path):
        cases = load_cases(CASES_PATH)[:1]
        path = self._write_recordings(tmp_path, cases)
        provider = FixtureProvider({"recordings_path": path})

        with pytest.raises(LLMProviderError, match="no recorded extraction"):
            provider.extract_problem(cases[0]["text"].strip() + " edited", "")

    def test_replay_costs_nothing(self, tmp_path):
        cases = load_cases(CASES_PATH)[:1]
        path = self._write_recordings(tmp_path, cases)
        provider = FixtureProvider({"recordings_path": path})

        result = provider.extract_problem(cases[0]["text"].strip(), "")

        assert result.estimated_cost == 0.0
        assert result.input_tokens == 0
        assert result.provider == "fixture"

    def test_evaluate_reports_per_case_and_never_dies_on_one_bad_case(self, tmp_path):
        cases = load_cases(CASES_PATH)
        # Record only the first case; every other case has no recording.
        path = self._write_recordings(tmp_path, cases[:1])

        report = evaluate(provider=FixtureProvider({"recordings_path": path}), cases_path=CASES_PATH)

        assert report.total == len(cases)
        assert report.passed >= 1
        # The unrecorded cases fail with an error rather than aborting the run.
        errored = [r for r in report.results if r.error]
        assert len(errored) == len(cases) - 1
        assert report.estimated_cost == 0.0
