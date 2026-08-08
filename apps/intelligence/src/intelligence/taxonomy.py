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


@lru_cache(maxsize=1)
def load_taxonomy_hint(path: str | None = None) -> str:
    """The taxonomy rendered for an LLM prompt (PROJECT_SPEC.md §24).

    Every topic and subtopic appears, including the ones with no `keywords` —
    the rule-based classifier cannot reach those, but an LLM reading the text
    can, which is a large part of why §24 exists.

    Generated from config rather than written into the prompt so a topic added
    to topics.yaml is immediately extractable. A hand-maintained copy would
    drift, and the failure mode is silent: the model keeps returning the slugs
    it was told about and the new topic simply never appears.
    """

    path = path or os.environ.get("TOPICS_REGISTRY_PATH", "/config/topics.yaml")

    with open(path) as f:
        raw = yaml.safe_load(f) or {}

    lines: list[str] = []
    for topic in raw.get("topics", []):
        description = topic.get("description", "")
        lines.append(f"- {topic['slug']}: {topic.get('name', '')} — {description}".rstrip(" —"))
        for subtopic in topic.get("subtopics", []):
            lines.append(f"    - {subtopic['slug']}: {subtopic.get('name', '')}")

    return "\n".join(lines)
