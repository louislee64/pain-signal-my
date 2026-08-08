from dataclasses import dataclass

from intelligence.taxonomy import TopicDefinition, load_classifiable_topics

CLASSIFICATION_METHOD = "rule_based_keyword_v1"


@dataclass(frozen=True)
class ClassificationMatch:
    topic_slug: str
    confidence: int
    matched_keywords: tuple[str, ...]


def _score(matched_count: int) -> int:
    return min(100, 50 + 25 * (matched_count - 1))


def classify_text(text: str, topics: tuple[TopicDefinition, ...] | None = None) -> list[ClassificationMatch]:
    if not text:
        return []

    topics = topics if topics is not None else load_classifiable_topics()
    haystack = text.lower()

    matches: list[ClassificationMatch] = []
    for topic in topics:
        hits = tuple(kw for kw in topic.keywords if kw in haystack)
        if hits:
            matches.append(
                ClassificationMatch(
                    topic_slug=topic.slug,
                    confidence=_score(len(hits)),
                    matched_keywords=hits,
                )
            )

    return matches
