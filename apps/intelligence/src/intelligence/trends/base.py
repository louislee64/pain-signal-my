"""Trend provider abstraction (PROJECT_SPEC.md §69).

Two genuinely different shapes of Trends data exist, and conflating them would
be a mistake:

  MONITORING (§15B) — interest-over-time for keywords we already chose to watch.
  Produces a dated series per keyword. This is what feeds `trend_metrics`.

  DISCOVERY (§15A) — top / rising queries we did NOT already know about.
  Produces ranked terms, and its whole purpose is to surface keywords absent
  from config/keywords.yaml.

A provider implements whichever it can serve. `collect_observations` covers
monitoring; `discover_terms` covers discovery. A provider that cannot do one
simply does not override it.
"""

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class TrendObservation:
    """One relative-interest reading for one keyword on one date.

    `interest` is Google Trends' 0-100 relative scale, never absolute search
    volume (§16). Values are only comparable to other observations collected in
    the same batch for the same keyword set.
    """

    keyword: str
    observed_on: date
    interest: int
    geo: str = "MY"
    region: str = ""


@dataclass(frozen=True)
class DiscoveredTerm:
    """A term surfaced by a discovery provider that we were not already tracking."""

    term: str
    observed_on: date
    rank: int
    score: int | None = None
    geo: str = "MY"
    region: str = ""
    is_rising: bool = False


class TrendProviderError(RuntimeError):
    """Raised when a provider cannot run — missing credentials, an optional
    dependency that isn't installed, or an unusable input file."""


class TrendProvider(ABC):
    """Base class for all trend adapters.

    PROJECT_SPEC.md §69 sets the acquisition order: official Google Trends API
    first, BigQuery public dataset second, adapter interface for future
    providers third — and explicitly rules out brittle scraping as the core
    implementation. Subclasses must honour that: no HTML scraping of
    trends.google.com belongs here.
    """

    name: str = "unnamed"

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}

    def collect_observations(self, keywords: list[str]) -> Iterable[TrendObservation]:
        """Interest-over-time for the given keywords (§15B monitoring)."""
        raise TrendProviderError(f"Provider '{self.name}' does not support keyword monitoring")

    def discover_terms(self) -> Iterable[DiscoveredTerm]:
        """Top / rising terms we may not already track (§15A discovery)."""
        raise TrendProviderError(f"Provider '{self.name}' does not support term discovery")

    @abstractmethod
    def check_available(self) -> None:
        """Raise TrendProviderError with an actionable message if this provider
        cannot run right now (missing credentials, uninstalled extra, etc.).

        Every provider must implement this: a provider that fails loudly and
        early with "here is what to configure" is far more useful than one that
        returns an empty series and lets the caller assume there was no data.
        """
        raise NotImplementedError
