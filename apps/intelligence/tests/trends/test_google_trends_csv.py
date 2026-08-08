from datetime import date
from pathlib import Path

import pytest

from intelligence.trends.base import TrendProviderError
from intelligence.trends.google_trends_csv import GoogleTrendsCsvProvider, parse_trends_csv

FIXTURE = Path(__file__).parent.parent / "fixtures" / "google_trends_interest_over_time.csv"


def test_parses_the_real_export_shape():
    observations = parse_trends_csv(FIXTURE.read_text())

    # 10 dates x 2 keywords
    assert len(observations) == 20

    first = observations[0]
    assert first.keyword == "invoice software"
    assert first.observed_on == date(2026, 3, 1)
    assert first.interest == 40
    assert first.geo == "MY"


def test_strips_the_geo_suffix_from_keyword_headers():
    keywords = {o.keyword for o in parse_trends_csv(FIXTURE.read_text())}
    assert keywords == {"invoice software", "stock count"}


def test_less_than_one_token_floors_to_zero():
    # "<1" is Google's own marker for a real but very low reading, not a gap.
    observations = parse_trends_csv(FIXTURE.read_text())
    match = next(o for o in observations if o.keyword == "stock count" and o.observed_on == date(2026, 3, 22))
    assert match.interest == 0


def test_skips_the_category_preamble_and_blank_lines():
    text = "Category: All categories\n\n\nWeek,alpha: (Malaysia)\n2026-03-01,10\n"
    observations = parse_trends_csv(text)
    assert len(observations) == 1
    assert observations[0].keyword == "alpha"


def test_accepts_daily_granularity_header():
    observations = parse_trends_csv("Day,alpha: (Malaysia)\n2026-03-01,10\n")
    assert observations[0].observed_on == date(2026, 3, 1)


def test_accepts_monthly_granularity_header():
    # Monthly exports carry YYYY-MM; it anchors to the first of the month.
    observations = parse_trends_csv("Month,alpha: (Malaysia)\n2026-03,10\n")
    assert observations[0].observed_on == date(2026, 3, 1)


def test_accepts_a_bare_keyword_header_without_geo_suffix():
    observations = parse_trends_csv("Week,invoice software\n2026-03-01,10\n")
    assert observations[0].keyword == "invoice software"


def test_empty_cells_are_skipped_not_treated_as_zero():
    observations = parse_trends_csv("Week,alpha: (MY),beta: (MY)\n2026-03-01,10,\n")
    assert len(observations) == 1
    assert observations[0].keyword == "alpha"


def test_rejects_a_file_that_is_not_an_interest_over_time_export():
    with pytest.raises(TrendProviderError, match="first column"):
        parse_trends_csv("Rank,Term\n1,something\n")


def test_rejects_an_unparseable_interest_value():
    with pytest.raises(TrendProviderError, match="interest value"):
        parse_trends_csv("Week,alpha: (MY)\n2026-03-01,abc\n")


def test_rejects_an_unparseable_date():
    with pytest.raises(TrendProviderError, match="date"):
        parse_trends_csv("Week,alpha: (MY)\n01/03/2026,10\n")


def test_rejects_an_empty_file():
    with pytest.raises(TrendProviderError):
        parse_trends_csv("")


def test_provider_check_available_explains_how_to_get_a_csv():
    with pytest.raises(TrendProviderError, match="trends.google.com"):
        GoogleTrendsCsvProvider({}).check_available()


def test_provider_check_available_reports_a_missing_file():
    with pytest.raises(TrendProviderError, match="not found"):
        GoogleTrendsCsvProvider({"path": "/nope/missing.csv"}).check_available()


def test_provider_filters_to_the_requested_keywords():
    provider = GoogleTrendsCsvProvider({"path": str(FIXTURE)})

    observations = list(provider.collect_observations(["invoice software"]))

    assert {o.keyword for o in observations} == {"invoice software"}


def test_provider_returns_everything_when_no_keyword_filter_given():
    provider = GoogleTrendsCsvProvider({"path": str(FIXTURE)})
    assert len(list(provider.collect_observations([]))) == 20


def test_provider_keyword_filter_is_case_insensitive():
    provider = GoogleTrendsCsvProvider({"path": str(FIXTURE)})
    observations = list(provider.collect_observations(["INVOICE SOFTWARE"]))
    assert len(observations) == 10


def test_provider_does_not_support_discovery():
    with pytest.raises(TrendProviderError, match="does not support term discovery"):
        list(GoogleTrendsCsvProvider({"path": str(FIXTURE)}).discover_terms())
