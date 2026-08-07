import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx

from intelligence.collectors.data_gov_my import DataGovMyDatasetCollector

FIXTURE = Path(__file__).parent.parent / "fixtures" / "fuelprice_sample.json"
CONFIG = {"dataset_id": "fuelprice", "date_column": "date"}


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler, base_url="https://api.data.gov.my/data-catalogue/")


def test_collect_yields_one_document_per_row():
    rows = json.loads(FIXTURE.read_text())
    client = _client(httpx.MockTransport(lambda request: httpx.Response(200, json=rows, request=request)))
    collector = DataGovMyDatasetCollector(CONFIG, client=client)

    documents = list(collector.collect(since=None))

    assert len(documents) == 3
    assert documents[0].external_id == "fuelprice:2017-03-30:level"
    assert documents[2].external_id == "fuelprice:2026-08-06:change_weekly"
    assert documents[0].payload["ron95"] == 2.13
    assert documents[0].region_raw == "MY"
    assert documents[0].published_at == datetime(2017, 3, 30, tzinfo=timezone.utc)


def test_collect_sends_incremental_date_filter():
    rows = json.loads(FIXTURE.read_text())
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json=rows, request=request)

    collector = DataGovMyDatasetCollector(CONFIG, client=_client(httpx.MockTransport(handler)))

    list(collector.collect(since=datetime(2026, 8, 1, tzinfo=timezone.utc)))

    assert captured["params"]["date_start"] == "2026-08-01@date"
    assert captured["params"]["id"] == "fuelprice"


@patch("intelligence.retry.time.sleep")
def test_collect_retries_on_server_error_then_succeeds(mock_sleep):
    rows = json.loads(FIXTURE.read_text())
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 2:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json=rows, request=request)

    collector = DataGovMyDatasetCollector(CONFIG, client=_client(httpx.MockTransport(handler)))

    documents = list(collector.collect(since=None))

    assert attempts["count"] == 2
    assert len(documents) == 3
    mock_sleep.assert_called_once()


@patch("intelligence.retry.time.sleep")
def test_collect_gives_up_on_non_retryable_error(mock_sleep):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, request=request)

    collector = DataGovMyDatasetCollector(CONFIG, client=_client(httpx.MockTransport(handler)))

    try:
        list(collector.collect(since=None))
        raised = False
    except httpx.HTTPStatusError:
        raised = True

    assert raised
    mock_sleep.assert_not_called()
