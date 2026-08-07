import json
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

import httpx

from intelligence.collectors.base import CollectedDocument, Collector
from intelligence.retry import call_with_retry

API_BASE_URL = "https://api.data.gov.my/data-catalogue/"

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class DataGovMyDatasetCollector(Collector):
    """Generic collector for any dataset exposed by the data.gov.my /
    OpenDOSM Open API (https://developer.data.gov.my).

    Adding a new dataset from this same API is a config-only change: add a
    `config/sources.yaml` entry with `collector: data_gov_my_dataset` and
    the dataset's own `dataset_id` / `date_column` — no new Python code.
    Required `config` keys: `dataset_id`, `date_column`.
    """

    def __init__(self, config: dict[str, Any], *, client: httpx.Client | None = None):
        super().__init__(config)
        self.dataset_id = config["dataset_id"]
        self.date_column = config["date_column"]
        self._client = client or httpx.Client(
            base_url=API_BASE_URL, timeout=30.0, follow_redirects=True
        )

    def collect(self, since: datetime | None) -> Iterable[CollectedDocument]:
        params: dict[str, str] = {"id": self.dataset_id, "sort": self.date_column}
        if since is not None:
            params["date_start"] = f"{since.date().isoformat()}@{self.date_column}"

        def fetch() -> httpx.Response:
            response = self._client.get("", params=params)
            response.raise_for_status()
            return response

        response = call_with_retry(fetch, is_retryable=_is_retryable)
        rows: list[dict[str, Any]] = response.json()

        for index, row in enumerate(rows):
            yield self._to_document(row, index)

    def _to_document(self, row: dict[str, Any], index: int) -> CollectedDocument:
        row_date = row.get(self.date_column)
        series_type = row.get("series_type")
        key_parts = [self.dataset_id, str(row_date), str(series_type) if series_type else str(index)]

        return CollectedDocument(
            external_id=":".join(key_parts),
            payload=row,
            title=f"{self.dataset_id} — {row_date}" + (f" ({series_type})" if series_type else ""),
            body=json.dumps(row, sort_keys=True, default=str),
            url=f"https://data.gov.my/data-catalogue/{self.dataset_id}",
            published_at=_parse_date(row_date),
            language_raw="en",
            region_raw="MY",
        )


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS_CODES
    return isinstance(exc, httpx.TransportError)


def _parse_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
