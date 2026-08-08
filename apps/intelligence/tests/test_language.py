import json
from pathlib import Path

import pytest

from intelligence.language import detect_language

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "multilingual_documents.json").read_text())


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f["id"])
def test_detect_language_matches_expected(fixture):
    text = f"{fixture['title']} {fixture['body']}"
    assert detect_language(text) == fixture["expected_language"]


def test_detect_language_handles_empty_text():
    assert detect_language("") == "unknown"
    assert detect_language("   ") == "unknown"


def test_detect_language_handles_pure_punctuation():
    assert detect_language("!!! 123 ???") == "unknown"
