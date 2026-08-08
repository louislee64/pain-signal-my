import json
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

import httpx

from intelligence.collectors.base import (
    CollectedDocument,
    Collector,
    FetchState,
    SourceUnchanged,
)
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
        self._fetch_state = FetchState()

    def collect(
        self, since: datetime | None, fetch_state: FetchState | None = None
    ) -> Iterable[CollectedDocument]:
        params: dict[str, str] = {"id": self.dataset_id, "sort": self.date_column}
        if since is not None:
            params["date_start"] = f"{since.date().isoformat()}@{self.date_column}"

        # §38: "Do not download unchanged official datasets unnecessarily."
        # data.gov.my is a public service used under its terms (§11), and once
        # ingestion runs nightly a conditional request is the difference between
        # asking politely and re-downloading a file that has not changed.
        headers: dict[str, str] = {}
        if fetch_state is not None:
            if fetch_state.etag:
                headers["If-None-Match"] = fetch_state.etag
            if fetch_state.last_modified:
                headers["If-Modified-Since"] = fetch_state.last_modified

        def fetch() -> httpx.Response:
            response = self._client.get("", params=params, headers=headers)
            # 304 is a successful conditional response, not an error, so it must
            # be let through before raise_for_status().
            if response.status_code == 304:
                return response
            response.raise_for_status()
            return response

        response = call_with_retry(fetch, is_retryable=_is_retryable)

        # Recorded even on 304: the server may rotate a weak validator without
        # the body changing, and storing the newest one keeps the next request
        # conditional.
        self._fetch_state = FetchState(
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
            dataset_version=response.headers.get("X-Dataset-Version"),
        )

        if response.status_code == 304:
            raise SourceUnchanged(
                f"data.gov.my reports dataset '{self.dataset_id}' unchanged since the last sync"
            )

        rows: list[dict[str, Any]] = response.json()

        for index, row in enumerate(rows):
            yield self._to_document(row, index)

    def fetch_state(self) -> FetchState:
        return self._fetch_state

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
