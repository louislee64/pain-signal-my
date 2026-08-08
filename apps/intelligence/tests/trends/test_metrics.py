from datetime import date, timedelta

import pytest

from intelligence.trends.metrics import Observation, compute_metrics

BASE = date(2026, 6, 1)


def series(values: list[int], start: date = BASE, step_days: int = 1) -> list[Observation]:
    return [Observation(start + timedelta(days=i * step_days), v) for i, v in enumerate(values)]


def test_empty_series_yields_all_none():
    metrics = compute_metrics([], BASE)

    assert metrics.rolling_7d is None
    assert metrics.rolling_30d is None
    assert metrics.baseline_90d is None
    assert metrics.growth_7d is None
    assert metrics.growth_30d is None
    assert metrics.growth_score is None
    assert metrics.z_score is None


def test_rolling_7d_averages_only_the_last_seven_days():
    # 10 daily points; the 7-day window ending on the last date covers the final 7.
    observations = series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    as_of = BASE + timedelta(days=9)

    metrics = compute_metrics(observations, as_of)

    assert metrics.rolling_7d == pytest.approx((4 + 5 + 6 + 7 + 8 + 9 + 10) / 7)


def test_rolling_window_is_inclusive_of_both_endpoints():
    # Exactly 7 daily points -> the whole series is one full 7-day window.
    observations = series([10] * 7)
    as_of = BASE + timedelta(days=6)

    assert compute_metrics(observations, as_of).rolling_7d == pytest.approx(10.0)


def test_observations_after_as_of_are_ignored():
    observations = series([10, 10, 10, 99, 99])
    as_of = BASE + timedelta(days=2)

    # Only the first three 10s are in scope; the later 99s must not leak in.
    assert compute_metrics(observations, as_of).rolling_7d == pytest.approx(10.0)


def test_growth_7d_compares_against_the_preceding_seven_days():
    # First 7 days average 10, next 7 days average 20 -> +100%.
    observations = series([10] * 7 + [20] * 7)
    as_of = BASE + timedelta(days=13)

    assert compute_metrics(observations, as_of).growth_7d == pytest.approx(100.0)


def test_growth_7d_is_negative_when_interest_falls():
    observations = series([20] * 7 + [10] * 7)
    as_of = BASE + timedelta(days=13)

    assert compute_metrics(observations, as_of).growth_7d == pytest.approx(-50.0)


def test_growth_is_none_when_there_is_no_prior_window():
    observations = series([10] * 7)
    as_of = BASE + timedelta(days=6)

    assert compute_metrics(observations, as_of).growth_7d is None


def test_growth_is_none_rather_than_infinite_when_prior_window_is_zero():
    # Rising from a zero baseline is real, but has no finite percentage —
    # None keeps "undefined" distinct from "no change".
    observations = series([0] * 7 + [50] * 7)
    as_of = BASE + timedelta(days=13)

    assert compute_metrics(observations, as_of).growth_7d is None


def test_growth_score_is_the_ratio_of_recent_interest_to_baseline():
    # 90 days at 10, then 7 days at 20. Baseline covers the 90-day window.
    observations = series([10] * 83 + [20] * 7)
    as_of = BASE + timedelta(days=89)

    metrics = compute_metrics(observations, as_of)

    assert metrics.rolling_7d == pytest.approx(20.0)
    assert metrics.growth_score == pytest.approx(20.0 / metrics.baseline_90d)
    assert metrics.growth_score > 1.0  # running hotter than baseline


def test_z_score_flags_an_unusual_spike():
    observations = series([10] * 30 + [90])
    as_of = BASE + timedelta(days=30)

    z = compute_metrics(observations, as_of).z_score

    assert z is not None
    assert z > 3.0


def test_z_score_is_none_for_a_perfectly_flat_series():
    # No variance means no scale to measure deviation against; 0.0 would
    # misleadingly read as "exactly average".
    observations = series([10] * 30)
    as_of = BASE + timedelta(days=29)

    assert compute_metrics(observations, as_of).z_score is None


def test_z_score_is_none_with_a_single_observation():
    assert compute_metrics(series([10]), BASE).z_score is None


def test_z_score_is_negative_when_latest_is_below_baseline():
    observations = series([50] * 20 + [40] * 9 + [1])
    as_of = BASE + timedelta(days=29)

    assert compute_metrics(observations, as_of).z_score < 0


def test_weekly_series_uses_the_same_calendar_windows_as_daily():
    # Weekly granularity (the BigQuery discovery dataset's shape): a 30-day
    # window holds ~4-5 points rather than 30, but still spans 30 days.
    observations = series([10, 20, 30, 40, 50], step_days=7)
    as_of = BASE + timedelta(days=28)

    metrics = compute_metrics(observations, as_of)

    # 7-day window ending on the last point contains only that point.
    assert metrics.rolling_7d == pytest.approx(50.0)
    # 30-day window reaches back across all 5 weekly points.
    assert metrics.rolling_30d == pytest.approx((10 + 20 + 30 + 40 + 50) / 5)


def test_gaps_in_the_series_do_not_extend_the_window():
    # A 40-day gap then two recent points: the 7-day window must not reach back
    # to the old observations just because there are few recent ones.
    old = [Observation(BASE, 100), Observation(BASE + timedelta(days=1), 100)]
    recent = [
        Observation(BASE + timedelta(days=41), 10),
        Observation(BASE + timedelta(days=42), 10),
    ]
    as_of = BASE + timedelta(days=42)

    assert compute_metrics(old + recent, as_of).rolling_7d == pytest.approx(10.0)


def test_unsorted_input_is_handled():
    observations = list(reversed(series([1, 2, 3, 4, 5, 6, 7])))
    as_of = BASE + timedelta(days=6)

    metrics = compute_metrics(observations, as_of)

    assert metrics.rolling_7d == pytest.approx(4.0)
    # z-score uses the latest value by date, not by list position.
    assert metrics.z_score is not None
