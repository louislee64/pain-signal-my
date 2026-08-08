from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class FetchState:
    """What the source told us about the version of the data we last received.

    §38: "Do not download unchanged official datasets unnecessarily. Store:
    last_modified, etag, dataset_version, last_successful_sync where available."

    Passed into `collect()` so a collector can make a conditional request, and
    returned by `fetch_state()` afterwards so ingestion can store whatever the
    source gave us. `None` everywhere is normal — most sources expose none of
    this, and the ingest pipeline's content-hash dedup already handles that case
    correctly, just less cheaply.
    """

    etag: str | None = None
    last_modified: str | None = None
    dataset_version: str | None = None


class SourceUnchanged(Exception):
    """Raised by a collector when the source says nothing has changed.

    An exception rather than an empty iterator because the two mean different
    things: "the dataset is unchanged since your last successful sync" is a
    successful outcome worth recording as such, while "the dataset is now empty"
    is a problem. Collapsing them would let a source that started returning
    nothing look like a source that simply had no news."""


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
    def collect(
        self, since: datetime | None, fetch_state: FetchState | None = None
    ) -> Iterable[CollectedDocument]:
        """Yield every document available from the source.

        `since` is a hint for incremental collection (e.g. only fetch rows
        published after this timestamp). Collectors that cannot filter
        server-side may ignore it — the ingest pipeline's idempotent upsert
        discards anything already stored unchanged.

        `fetch_state` carries what the source said about the version we last
        received (§38). A collector that can make a conditional request should
        use it and raise `SourceUnchanged` on a 304; one that cannot may ignore
        it entirely.
        """
        raise NotImplementedError

    def fetch_state(self) -> FetchState:
        """Version metadata from the most recent `collect()` call.

        Default is empty: a collector that cannot report a version is the normal
        case, not a broken one. Overriding is how a collector opts into §38's
        conditional fetching.
        """
        return FetchState()
