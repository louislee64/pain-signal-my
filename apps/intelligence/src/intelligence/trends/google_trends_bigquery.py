"""Google Trends BigQuery public-dataset provider (PROJECT_SPEC.md §15A discovery).

Queries `bigquery-public-data.google_trends.international_top_terms` (and its
`international_top_rising_terms` sibling) for Malaysian top/rising queries. This
is §15A's job: surfacing terms the system did not already know to look for,
rather than monitoring a keyword list we chose in advance.

Requires a Google Cloud project with billing enabled — the dataset itself is
free to read but BigQuery charges for bytes scanned beyond the monthly free
tier. The `google-cloud-bigquery` client is therefore an OPTIONAL extra rather
than a default dependency:

    pip install -e ".[bigquery]"

Deliberately not installed in the default image. It is a heavy dependency that
cannot be exercised at all without credentials, and this project's standing rule
is to add dependencies when a milestone actually needs them rather than
preemptively (see docs/architecture.md).

The dataset is weekly, covers a rolling 5-year window, and its rows expire from
`refresh_date` after 30 days.
"""

import os
from collections.abc import Iterable

from intelligence.observability import get_logger, log_event
from intelligence.trends.base import DiscoveredTerm, TrendProvider, TrendProviderError

logger = get_logger("intelligence.trends.bigquery")

DEFAULT_COUNTRY_CODE = "MY"
TOP_TERMS_TABLE = "bigquery-public-data.google_trends.international_top_terms"
TOP_RISING_TERMS_TABLE = "bigquery-public-data.google_trends.international_top_rising_terms"

# `week` is the partition/clustering-friendly filter and `country_code` narrows
# to Malaysia; both keep the bytes scanned (and therefore the bill) small.
QUERY_TEMPLATE = """
SELECT term, week, rank, score, country_code, region_name
FROM `{table}`
WHERE country_code = @country_code
  AND week >= DATE_SUB(CURRENT_DATE(), INTERVAL @lookback_days DAY)
ORDER BY week DESC, rank ASC
LIMIT @row_limit
"""


class GoogleTrendsBigQueryProvider(TrendProvider):
    name = "google_trends_bigquery"

    def __init__(self, config=None):
        super().__init__(config)
        self.country_code = self.config.get("country_code", DEFAULT_COUNTRY_CODE)
        self.lookback_days = int(self.config.get("lookback_days", 90))
        self.row_limit = int(self.config.get("row_limit", 500))
        self.project = self.config.get("project") or os.environ.get("GOOGLE_CLOUD_PROJECT")

    def check_available(self) -> None:
        try:
            import google.cloud.bigquery  # noqa: F401
        except ImportError:
            raise TrendProviderError(
                "google_trends_bigquery needs the optional BigQuery extra: "
                "pip install -e '.[bigquery]' (see docs/trends-data-sources.md)."
            ) from None

        if not self.project:
            raise TrendProviderError(
                "google_trends_bigquery needs a GCP project: set GOOGLE_CLOUD_PROJECT "
                "(and GOOGLE_APPLICATION_CREDENTIALS to a service-account key with "
                "BigQuery Job User). See docs/trends-data-sources.md."
            )

        if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            raise TrendProviderError(
                "google_trends_bigquery needs GOOGLE_APPLICATION_CREDENTIALS pointing at a "
                "service-account key file. See docs/trends-data-sources.md."
            )

    def discover_terms(self) -> Iterable[DiscoveredTerm]:
        self.check_available()

        from google.cloud import bigquery

        client = bigquery.Client(project=self.project)

        for table, is_rising in ((TOP_TERMS_TABLE, False), (TOP_RISING_TERMS_TABLE, True)):
            job_config = bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("country_code", "STRING", self.country_code),
                    bigquery.ScalarQueryParameter("lookback_days", "INT64", self.lookback_days),
                    bigquery.ScalarQueryParameter("row_limit", "INT64", self.row_limit),
                ]
            )

            log_event(logger, "trends.bigquery.query", table=table, country=self.country_code)

            for row in client.query(QUERY_TEMPLATE.format(table=table), job_config=job_config):
                yield DiscoveredTerm(
                    term=row["term"],
                    observed_on=row["week"],
                    rank=row["rank"],
                    score=row.get("score"),
                    geo=row["country_code"],
                    region=row.get("region_name") or "",
                    is_rising=is_rising,
                )
