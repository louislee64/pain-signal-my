"""Trend collection and metric computation orchestration (PROJECT_SPEC.md §16)."""

from typing import Any

from sqlalchemy.engine import Engine
from ulid import ULID

from intelligence.observability import get_logger, log_event
from intelligence.repositories import keywords, trend_metrics
from intelligence.repositories.trend_metrics import TrendObservationInput
from intelligence.trends.base import TrendProvider, TrendProviderError
from intelligence.trends.metrics import compute_metrics
from intelligence.trends.registry import get_trend_provider_class

logger = get_logger("intelligence.trends")

DISCOVERED_KEYWORD_GROUP = "discovered"


def _build_provider(provider_name: str, config: dict[str, Any] | None) -> TrendProvider:
    return get_trend_provider_class(provider_name)(config or {})


def collect_trends(
    engine: Engine,
    provider_name: str,
    *,
    config: dict[str, Any] | None = None,
    provider: TrendProvider | None = None,
) -> dict[str, Any]:
    """Pull interest-over-time observations and store them (§15B monitoring).

    Every row from one invocation shares a `collection_batch`, because Trends
    values are only comparable within a single collection (§16) — without that
    marker a later analysis could silently compare two differently-scaled runs.
    """

    provider = provider or _build_provider(provider_name, config)
    batch = str(ULID())

    with engine.begin() as conn:
        tracked = keywords.get_enabled_keywords(conn)

    by_name = {k.keyword.casefold(): k for k in tracked}
    counts = {"received": 0, "inserted": 0, "updated": 0, "unknown_keyword": 0}

    observations = list(provider.collect_observations([k.keyword for k in tracked]))

    for observation in observations:
        counts["received"] += 1
        keyword = by_name.get(observation.keyword.casefold())

        if keyword is None:
            # The provider returned a keyword nobody registered. Skipped rather
            # than auto-created: monitoring is a deliberate, curated list (§15B),
            # and silently growing it from a stray CSV column would blur the line
            # with discovery (§15A), which has its own explicit path below.
            counts["unknown_keyword"] += 1
            log_event(logger, "trends.unknown_keyword", keyword=observation.keyword)
            continue

        with engine.begin() as conn:
            outcome = trend_metrics.upsert_observation(
                conn,
                TrendObservationInput(
                    keyword_id=keyword.id,
                    observed_on=observation.observed_on,
                    interest=observation.interest,
                    country=observation.geo,
                    region=observation.region,
                    collection_method=provider.name,
                    collection_batch=batch,
                ),
            )
            counts[outcome] += 1

    log_event(logger, "trends.collect_finished", provider=provider.name, batch=batch, **counts)
    return {"provider": provider.name, "batch": batch, **counts}


def discover_trend_terms(
    engine: Engine,
    provider_name: str,
    *,
    config: dict[str, Any] | None = None,
    provider: TrendProvider | None = None,
) -> dict[str, Any]:
    """Register top/rising terms we were not already tracking (§15A discovery)."""

    provider = provider or _build_provider(provider_name, config)
    counts = {"received": 0, "new_keywords": 0, "already_known": 0}

    for term in provider.discover_terms():
        counts["received"] += 1

        with engine.begin() as conn:
            existing = keywords.find_by_keyword(conn, term.term, term.geo)
            if existing is not None:
                counts["already_known"] += 1
                continue

            keywords.create_discovered_keyword(
                conn, term.term, term.geo, DISCOVERED_KEYWORD_GROUP
            )
            counts["new_keywords"] += 1

    log_event(logger, "trends.discover_finished", provider=provider.name, **counts)
    return {"provider": provider.name, **counts}


def compute_trend_metrics(engine: Engine) -> dict[str, int]:
    """Recompute rolling averages, growth and z-scores for every stored series.

    Each date is computed against only the observations up to that date, so a
    back-filled history produces exactly the values it would have produced had
    it been collected day by day.
    """

    counts = {"series": 0, "rows": 0}

    with engine.begin() as conn:
        series_keys = trend_metrics.distinct_series_keys(conn)

    for keyword_id, region in series_keys:
        with engine.begin() as conn:
            observations = trend_metrics.get_series(conn, keyword_id, region)

        counts["series"] += 1

        for observation in observations:
            metrics = compute_metrics(observations, observation.observed_on)
            with engine.begin() as conn:
                trend_metrics.store_metrics(
                    conn, keyword_id, region, observation.observed_on, metrics
                )
            counts["rows"] += 1

    log_event(logger, "trends.compute_finished", **counts)
    return counts


def check_provider(provider_name: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Report whether a provider can run, with an actionable reason if not."""

    provider = _build_provider(provider_name, config)
    try:
        provider.check_available()
    except TrendProviderError as exc:
        return {"provider": provider_name, "available": False, "reason": str(exc)}
    return {"provider": provider_name, "available": True}
