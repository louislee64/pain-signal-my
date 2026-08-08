"""Trend provider registry (PROJECT_SPEC.md §69 point 3).

Adding a future provider — most importantly the official Google Trends API once
alpha access is granted — means writing a TrendProvider subclass and adding one
line here. Nothing downstream (storage, metrics, CLI, API) needs to change.

No `google_trends_api` entry exists yet on purpose. That API is §69's stated
first preference, but it is still an application-gated alpha with no public
endpoint or auth contract to build against, so any implementation here would be
guesswork that looks functional and is not. docs/trends-data-sources.md records
exactly what to add when access arrives.
"""

from intelligence.trends.base import TrendProvider
from intelligence.trends.google_trends_bigquery import GoogleTrendsBigQueryProvider
from intelligence.trends.google_trends_csv import GoogleTrendsCsvProvider

TREND_PROVIDER_REGISTRY: dict[str, type[TrendProvider]] = {
    GoogleTrendsCsvProvider.name: GoogleTrendsCsvProvider,
    GoogleTrendsBigQueryProvider.name: GoogleTrendsBigQueryProvider,
}


def get_trend_provider_class(name: str) -> type[TrendProvider]:
    try:
        return TREND_PROVIDER_REGISTRY[name]
    except KeyError:
        registered = ", ".join(sorted(TREND_PROVIDER_REGISTRY)) or "(none)"
        raise ValueError(
            f"No trend provider registered for '{name}'. Registered: {registered}"
        ) from None
