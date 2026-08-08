import json
from pathlib import Path

import pytest

from intelligence.classify import classify_text

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "multilingual_documents.json").read_text())


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f["id"])
def test_classify_text_matches_expected_topics(fixture):
    text = f"{fixture['title']} {fixture['body']}"
    matches = classify_text(text)
    matched_slugs = {m.topic_slug for m in matches}

    assert matched_slugs == set(fixture["expected_topics"])
    assert all(1 <= m.confidence <= 100 for m in matches)


def test_classify_text_returns_nothing_for_empty_text():
    assert classify_text("") == []


def test_classify_text_returns_nothing_when_no_keywords_match():
    assert classify_text("completely unrelated text about the weather today") == []


def test_confidence_increases_with_more_keyword_hits():
    from intelligence.taxonomy import TopicDefinition

    topics = (TopicDefinition(slug="t", keywords=("alpha", "beta", "gamma")),)

    one_hit = classify_text("alpha only", topics=topics)
    two_hits = classify_text("alpha and beta", topics=topics)

    assert one_hit[0].confidence < two_hits[0].confidence
