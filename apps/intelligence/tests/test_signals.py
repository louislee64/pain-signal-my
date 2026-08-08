from intelligence.signals import SignalRules, extract_signal

RULES = SignalRules(
    severity_keywords=[{"points": 30, "keywords": ["very frustrating"]}, {"points": 15, "keywords": ["problem"]}],
    urgency_keywords=[
        {"points": 30, "frequency_hint": "daily", "keywords": ["every day", "setiap hari"]},
        {"points": 25, "keywords": ["urgent"]},
    ],
    economic_impact_keywords=[{"points": 15, "keywords": ["staff time"]}],
    payer_keywords=[{"payer_type": "business_owner", "keywords": ["boss", "owner"]}],
)


def test_extract_signal_scores_and_evidence():
    signal = extract_signal(
        "Every day the boss complains it's very frustrating and wastes staff time.", RULES
    )

    assert signal.severity_score == 30
    assert signal.urgency_score == 30
    assert signal.economic_impact_score == 15
    assert signal.frequency_hint == "daily"
    assert signal.payer_type == "business_owner"
    assert "very frustrating" in signal.evidence["severity_keywords"]


def test_extract_signal_sums_multiple_matched_groups():
    signal = extract_signal("This is a real problem and it's also very frustrating and urgent.", RULES)

    assert signal.severity_score == 45  # 30 + 15
    assert signal.urgency_score == 25


def test_extract_signal_caps_at_100():
    rules = SignalRules(
        severity_keywords=[
            {"points": 60, "keywords": ["alpha"]},
            {"points": 60, "keywords": ["beta"]},
        ]
    )
    signal = extract_signal("alpha beta", rules)
    assert signal.severity_score == 100


def test_extract_signal_returns_none_for_unmatched_dimension():
    signal = extract_signal("nothing relevant here", RULES)

    assert signal.severity_score is None
    assert signal.urgency_score is None
    assert signal.economic_impact_score is None
    assert signal.frequency_hint is None
    assert signal.payer_type is None


def test_extract_signal_handles_empty_text():
    signal = extract_signal("", RULES)
    assert signal.severity_score is None
