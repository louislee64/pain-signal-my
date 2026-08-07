from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class CollectedDocument:
    external_id: str
    payload: dict[str, Any]
    title: str | None = None
    body: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    language_raw: str = "en"
    region_raw: str | None = None


class Collector(ABC):
    def __init__(self, config: dict[str, Any]):
        self.config = config

    @abstractmethod
    def collect(self, since: datetime | None) -> Iterable[CollectedDocument]:
        """Yield every document available from the source.

        `since` is a hint for incremental collection (e.g. only fetch rows
        published after this timestamp). Collectors that cannot filter
        server-side may ignore it — the ingest pipeline's idempotent upsert
        discards anything already stored unchanged.
        """
        raise NotImplementedError
