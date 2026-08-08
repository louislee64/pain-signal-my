import pytest

from intelligence.trends.base import TrendProviderError
from intelligence.trends.google_trends_bigquery import GoogleTrendsBigQueryProvider
from intelligence.trends.google_trends_csv import GoogleTrendsCsvProvider
from intelligence.trends.registry import TREND_PROVIDER_REGISTRY, get_trend_provider_class


def test_registered_providers_resolve_by_name():
    assert get_trend_provider_class("google_trends_csv") is GoogleTrendsCsvProvider
    assert get_trend_provider_class("google_trends_bigquery") is GoogleTrendsBigQueryProvider


def test_unknown_provider_error_lists_what_is_registered():
    with pytest.raises(ValueError, match="google_trends_csv"):
        get_trend_provider_class("nope")


def test_every_registered_provider_declares_its_own_name():
    for name, provider_class in TREND_PROVIDER_REGISTRY.items():
        assert provider_class.name == name, f"{provider_class.__name__}.name must equal its registry key"


def test_bigquery_provider_reports_missing_credentials_rather_than_failing_silently(monkeypatch):
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)

    with pytest.raises(TrendProviderError) as exc:
        GoogleTrendsBigQueryProvider({}).check_available()

    # Whichever gate trips first, the message must tell the operator what to do.
    assert "docs/trends-data-sources.md" in str(exc.value)


def test_bigquery_provider_does_not_support_keyword_monitoring():
    # Discovery and monitoring are different jobs (§15A vs §15B); the BigQuery
    # top-terms dataset only serves the former.
    with pytest.raises(TrendProviderError, match="does not support keyword monitoring"):
        list(GoogleTrendsBigQueryProvider({}).collect_observations(["anything"]))
