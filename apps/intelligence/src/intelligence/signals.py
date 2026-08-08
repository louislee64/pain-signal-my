import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import yaml

CLASSIFICATION_METHOD = "rule_based_keyword_v1"


@dataclass(frozen=True)
class SignalRules:
    severity_keywords: list[dict] = field(default_factory=list)
    urgency_keywords: list[dict] = field(default_factory=list)
    economic_impact_keywords: list[dict] = field(default_factory=list)
    payer_keywords: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class ExtractedSignal:
    severity_score: int | None
    urgency_score: int | None
    economic_impact_score: int | None
    frequency_hint: str | None
    payer_type: str | None
    evidence: dict[str, Any]


@lru_cache(maxsize=1)
def load_signal_rules(path: str | None = None) -> SignalRules:
    path = path or os.environ.get("SIGNAL_RULES_PATH", "/config/signal_rules.yaml")

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    return SignalRules(
        severity_keywords=raw.get("severity_keywords", []),
        urgency_keywords=raw.get("urgency_keywords", []),
        economic_impact_keywords=raw.get("economic_impact_keywords", []),
        payer_keywords=raw.get("payer_keywords", []),
    )


def _score_groups(haystack: str, groups: list[dict]) -> tuple[int | None, list[str]]:
    total = 0
    matched: list[str] = []
    for group in groups:
        hits = [kw for kw in group.get("keywords", []) if kw.lower() in haystack]
        if hits:
            total += group["points"]
            matched.extend(hits)

    if not matched:
        return None, []
    return min(100, total), matched


def _frequency_hint(haystack: str, urgency_groups: list[dict]) -> str | None:
    for group in urgency_groups:
        if "frequency_hint" not in group:
            continue
        if any(kw.lower() in haystack for kw in group.get("keywords", [])):
            return group["frequency_hint"]
    return None


def _payer_type(haystack: str, payer_groups: list[dict]) -> tuple[str | None, list[str]]:
    for group in payer_groups:
        hits = [kw for kw in group.get("keywords", []) if kw.lower() in haystack]
        if hits:
            return group["payer_type"], hits
    return None, []


def extract_signal(text: str, rules: SignalRules | None = None) -> ExtractedSignal:
    rules = rules if rules is not None else load_signal_rules()
    haystack = (text or "").lower()

    severity_score, severity_hits = _score_groups(haystack, rules.severity_keywords)
    economic_impact_score, economic_hits = _score_groups(haystack, rules.economic_impact_keywords)
    urgency_score, urgency_hits = _score_groups(haystack, rules.urgency_keywords)
    frequency_hint = _frequency_hint(haystack, rules.urgency_keywords)
    payer_type, payer_hits = _payer_type(haystack, rules.payer_keywords)

    return ExtractedSignal(
        severity_score=severity_score,
        urgency_score=urgency_score,
        economic_impact_score=economic_impact_score,
        frequency_hint=frequency_hint,
        payer_type=payer_type,
        evidence={
            "severity_keywords": severity_hits,
            "urgency_keywords": urgency_hits,
            "economic_impact_keywords": economic_hits,
            "payer_keywords": payer_hits,
        },
    )
