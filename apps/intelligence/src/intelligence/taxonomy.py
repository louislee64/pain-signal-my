import os
from dataclasses import dataclass
from functools import lru_cache

import yaml


@dataclass(frozen=True)
class TopicDefinition:
    slug: str
    keywords: tuple[str, ...]


def _flatten(definitions: list[dict], out: list[TopicDefinition]) -> None:
    for definition in definitions:
        keywords = tuple(k.lower() for k in definition.get("keywords", []))
        if keywords:
            out.append(TopicDefinition(slug=definition["slug"], keywords=keywords))
        _flatten(definition.get("subtopics", []), out)


@lru_cache(maxsize=1)
def load_classifiable_topics(path: str | None = None) -> tuple[TopicDefinition, ...]:
    """Topics/subtopics from config/topics.yaml that declare `keywords` —
    the only ones the rule-based classifier can ever match. Topics without
    keywords still exist in the `topics` table (via `php artisan
    topics:sync`) but require a future classification method to populate."""

    path = path or os.environ.get("TOPICS_REGISTRY_PATH", "/config/topics.yaml")

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    flattened: list[TopicDefinition] = []
    _flatten(raw.get("topics", []), flattened)
    return tuple(flattened)
