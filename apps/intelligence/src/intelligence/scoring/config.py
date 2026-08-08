"""Loader for config/scoring.yaml (PROJECT_SPEC.md §26).

The spec is unambiguous — "All weights must live in config/scoring.yaml. Do not
hard-code them." — so this module is the ONLY place scoring numbers enter the
process, and every accessor raises rather than falling back to a built-in
default. A silent default would be a hard-coded weight wearing a disguise, and
would make a typo'd config key look like a deliberate business decision.
"""

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import yaml


class ScoringConfigError(RuntimeError):
    """Raised when config/scoring.yaml is missing, unreadable, or missing a key
    the scoring engine needs."""


@dataclass(frozen=True)
class ScoringConfig:
    raw: dict[str, Any]

    @property
    def version(self) -> str:
        return str(self._require("version"))

    def _require(self, *path: str) -> Any:
        node: Any = self.raw
        for key in path:
            if not isinstance(node, dict) or key not in node:
                joined = ".".join(path)
                raise ScoringConfigError(f"config/scoring.yaml is missing required key '{joined}'")
            node = node[key]
        return node

    def weights(self, score_name: str) -> dict[str, float]:
        weights = self._require(score_name, "weights")
        return {str(k): float(v) for k, v in weights.items()}

    def normalization(self, key: str) -> float:
        return float(self._require("normalization", key))

    def recurrence_score(self, frequency_hint: str | None) -> float:
        scores = self._require("recurrence_scores")
        if frequency_hint is None:
            return float(scores.get("unknown", 0))
        return float(scores.get(frequency_hint, scores.get("unknown", 0)))

    def implementation_fit(self, topic_slug: str, parent_slug: str | None = None) -> float:
        fit = self._require("implementation_fit")
        by_topic = fit.get("by_topic") or {}

        if topic_slug in by_topic:
            return float(by_topic[topic_slug])
        # Subtopics inherit their parent's fit: "einvoice" is as software-solvable
        # as "billing_invoice" is, and listing every leaf would guarantee drift.
        if parent_slug and parent_slug in by_topic:
            return float(by_topic[parent_slug])
        return float(self._require("implementation_fit", "default"))

    def opportunity_cap_without_commercial_validation(self) -> float:
        return float(self._require("opportunity_score", "uncommercially_validated_cap"))

    def paid_pilot_bonus(self) -> float:
        return float(self._require("opportunity_score", "paid_pilot_bonus"))

    def repeat_customer_bonus(self) -> float:
        return float(self._require("opportunity_score", "repeat_customer_bonus"))

    def recommendation_rule(self, key: str) -> float:
        return float(self._require("recommendation", key))

    def window_days(self) -> int:
        return int(self._require("window", "days"))


def load_scoring_config(path: str | None = None) -> ScoringConfig:
    path = path or os.environ.get("SCORING_CONFIG_PATH", "/config/scoring.yaml")

    try:
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    except FileNotFoundError:
        raise ScoringConfigError(
            f"Scoring config not found at {path}. Set SCORING_CONFIG_PATH or mount config/."
        ) from None

    return ScoringConfig(raw=raw)


@lru_cache(maxsize=1)
def get_scoring_config() -> ScoringConfig:
    return load_scoring_config()
