"""Derived trend metrics (PROJECT_SPEC.md §16).

Every function here is pure: a series of (date, interest) observations in,
computed metrics out. No database, no I/O — this is the part of the trend
pipeline that most needs to be exhaustively testable, because a subtly wrong
z-score or growth figure would silently mislead every downstream judgement.

Window sizes are calendar-day ranges, NOT counts of observations. That matters
because the two providers deliver different granularities — the CSV export is
daily/weekly depending on the requested range, and the BigQuery discovery
dataset is weekly. A count-based window would silently mean "7 weeks" for one
provider and "7 days" for another; a date-based window means the same span for
both, just with fewer points inside it. It also degrades gracefully across gaps
in a series rather than reaching further back than intended.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import fmean, pstdev

ROLLING_SHORT_DAYS = 7
ROLLING_LONG_DAYS = 30
BASELINE_DAYS = 90


@dataclass(frozen=True)
class Observation:
    observed_on: date
    interest: int


@dataclass(frozen=True)
class TrendMetrics:
    rolling_7d: float | None
    rolling_30d: float | None
    baseline_90d: float | None
    growth_7d: float | None
    growth_30d: float | None
    growth_score: float | None
    z_score: float | None


def _window(
    observations: list[Observation], end: date, days: int, offset_days: int = 0
) -> list[Observation]:
    """Observations inside the `days`-long window ending `offset_days` before
    `end`, inclusive of both endpoints."""

    window_end = end - timedelta(days=offset_days)
    window_start = window_end - timedelta(days=days - 1)
    return [o for o in observations if window_start <= o.observed_on <= window_end]


def _mean(observations: list[Observation]) -> float | None:
    if not observations:
        return None
    return fmean(o.interest for o in observations)


def _percent_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    if previous == 0:
        # A jump up from a zero baseline is a real signal but has no finite
        # percentage. Returning None (rather than 0 or infinity) keeps
        # "undefined" distinguishable from "no change" downstream.
        return None
    return (current - previous) / previous * 100.0


def compute_metrics(observations: list[Observation], as_of: date) -> TrendMetrics:
    """Metrics for the series as of `as_of`. Observations after `as_of` are
    ignored, so back-filling history recomputes each day exactly as it would
    have been computed on that day."""

    history = sorted(
        (o for o in observations if o.observed_on <= as_of), key=lambda o: o.observed_on
    )

    if not history:
        return TrendMetrics(None, None, None, None, None, None, None)

    rolling_7d = _mean(_window(history, as_of, ROLLING_SHORT_DAYS))
    rolling_30d = _mean(_window(history, as_of, ROLLING_LONG_DAYS))
    baseline_90d = _mean(_window(history, as_of, BASELINE_DAYS))

    previous_7d = _mean(_window(history, as_of, ROLLING_SHORT_DAYS, offset_days=ROLLING_SHORT_DAYS))
    previous_30d = _mean(_window(history, as_of, ROLLING_LONG_DAYS, offset_days=ROLLING_LONG_DAYS))

    growth_7d = _percent_change(rolling_7d, previous_7d)
    growth_30d = _percent_change(rolling_30d, previous_30d)

    # §16's "trend_signal = current_interest / baseline_interest", expressed as
    # the short rolling average over the 90-day baseline so a single spiky day
    # cannot dominate it. >1 means currently running hotter than baseline.
    growth_score = None
    if rolling_7d is not None and baseline_90d not in (None, 0):
        growth_score = rolling_7d / baseline_90d

    z_score = _z_score(history, as_of, baseline_90d)

    return TrendMetrics(
        rolling_7d=rolling_7d,
        rolling_30d=rolling_30d,
        baseline_90d=baseline_90d,
        growth_7d=growth_7d,
        growth_30d=growth_30d,
        growth_score=growth_score,
        z_score=z_score,
    )


def _z_score(history: list[Observation], as_of: date, baseline_90d: float | None) -> float | None:
    """How unusual the latest value is against the 90-day baseline, in standard
    deviations. Population stdev (not sample) because the baseline window is the
    whole population being described, not a sample drawn from a larger one."""

    if baseline_90d is None:
        return None

    baseline = _window(history, as_of, BASELINE_DAYS)
    if len(baseline) < 2:
        return None

    spread = pstdev(o.interest for o in baseline)
    if spread == 0:
        # A perfectly flat series has no scale to measure deviation against.
        # Reporting 0.0 would read as "exactly average" — true but misleading,
        # since any change at all is undefined rather than unremarkable.
        return None

    latest = history[-1].interest
    return (latest - baseline_90d) / spread
