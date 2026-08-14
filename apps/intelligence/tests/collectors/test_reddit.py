"""Tests for the Reddit collector (PROJECT_SPEC.md §13, §17, §21).

No credentials required: every request is served from fixtures. That is
deliberate — a test suite that only passes for whoever holds the API secret is
not a test suite.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import yaml

from intelligence.collectors.registry import get_collector_class
from intelligence.collectors.reddit import (
    API_BASE_URL,
    TOKEN_URL,
    RedditCredentialsMissing,
    RedditSubredditCollector,
)

FIXTURES = Path(__file__).parent.parent / "fixtures"
PAGE1 = json.loads((FIXTURES / "reddit_new_page1.json").read_text())
PAGE2 = json.loads((FIXTURES / "reddit_new_page2.json").read_text())

CREDS = {
    "REDDIT_CLIENT_ID": "test_client_id",
    "REDDIT_CLIENT_SECRET": "test_client_secret",
}
CONFIG = {"subreddit": "malaysia", "min_body_chars": 120}


def _collector(handler, config=None, credentials=None) -> RedditSubredditCollector:
    return RedditSubredditCollector(
        {**CONFIG, **(config or {})},
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        credentials=CREDS if credentials is None else credentials,
        # Rate limiting is real but must not make the suite slow; its behaviour is
        # asserted separately with a recording sleep.
        sleep=lambda _seconds: None,
    )


def _handler(pages=None, *, rate_headers=None):
    """Serve the token endpoint, then the listing pages in order."""
    pages = pages if pages is not None else [PAGE1, PAGE2]
    state = {"page": 0}

    def handle(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(TOKEN_URL):
            return httpx.Response(
                200,
                json={"access_token": "test_token", "token_type": "bearer", "expires_in": 3600},
                request=request,
            )
        index = min(state["page"], len(pages) - 1)
        state["page"] += 1
        return httpx.Response(
            200, json=pages[index], headers=rate_headers or {}, request=request
        )

    return handle


class TestRegistrationAndAvailability:
    def test_the_collector_is_reachable_by_name(self):
        assert get_collector_class("reddit_subreddit") is RedditSubredditCollector

    def test_a_missing_subreddit_fails_with_an_actionable_message(self):
        with pytest.raises(ValueError, match="subreddit"):
            RedditSubredditCollector({}, credentials=CREDS)

    def test_missing_credentials_refuse_with_instructions(self):
        """§41: a run that cannot authenticate must fail loudly, not quietly
        return nothing and let the source look merely quiet."""
        collector = _collector(_handler(), credentials={})

        with pytest.raises(RedditCredentialsMissing) as exc:
            list(collector.collect(since=None))

        message = str(exc.value)
        assert "REDDIT_CLIENT_ID" in message
        assert "reddit.com/prefs/apps" in message
        assert "docs/text-sources.md" in message

    def test_missing_credentials_are_detected_before_any_request(self):
        calls = {"n": 0}

        def handle(request):
            calls["n"] += 1
            return httpx.Response(200, json={}, request=request)

        collector = _collector(handle, credentials={})

        with pytest.raises(RedditCredentialsMissing):
            list(collector.collect(since=None))

        assert calls["n"] == 0

    def test_rejected_credentials_say_so_rather_than_retrying_into_a_wall(self):
        def handle(request):
            return httpx.Response(401, json={"message": "Unauthorized"}, request=request)

        collector = _collector(handle)

        with pytest.raises(RedditCredentialsMissing, match="rejected"):
            list(collector.collect(since=None))

    def test_constructing_the_collector_never_touches_the_network(self):
        """`sources:sync` builds nothing, but `sources:ingest` iterates the whole
        registry; a constructor that authenticated would make an unrelated run
        fail on a disabled source."""
        calls = {"n": 0}

        def handle(request):
            calls["n"] += 1
            return httpx.Response(200, json={}, request=request)

        _collector(handle)

        assert calls["n"] == 0


class TestAuthentication:
    def test_uses_the_client_credentials_grant_with_basic_auth(self):
        captured: dict = {}

        def handle(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(TOKEN_URL):
                captured["auth"] = request.headers.get("authorization")
                captured["body"] = request.content.decode()
                return httpx.Response(200, json={"access_token": "test_token"}, request=request)
            return httpx.Response(200, json=PAGE2, request=request)

        list(_collector(handle).collect(since=None))

        assert captured["auth"].startswith("Basic ")
        assert "grant_type=client_credentials" in captured["body"]

    def test_the_token_is_sent_as_a_bearer_on_api_requests(self):
        captured: dict = {}

        def handle(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(TOKEN_URL):
                return httpx.Response(200, json={"access_token": "test_token"}, request=request)
            captured["auth"] = request.headers.get("authorization")
            captured["url"] = str(request.url)
            return httpx.Response(200, json=PAGE2, request=request)

        list(_collector(handle).collect(since=None))

        assert captured["auth"] == "Bearer test_token"
        assert captured["url"].startswith(f"{API_BASE_URL}/r/malaysia/new")

    def test_the_token_is_fetched_once_per_run(self):
        """Two listing pages, one token. Re-authenticating per page would triple
        the request count against a 100/minute budget for no benefit."""
        tokens = {"n": 0}
        listings = {"n": 0}

        def handle(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(TOKEN_URL):
                tokens["n"] += 1
                return httpx.Response(200, json={"access_token": "test_token"}, request=request)
            listings["n"] += 1
            return httpx.Response(
                200, json=PAGE1 if listings["n"] == 1 else PAGE2, request=request
            )

        list(_collector(handle).collect(since=None))

        assert listings["n"] == 2
        assert tokens["n"] == 1

    def test_it_never_requests_a_reddit_com_web_page(self):
        """robots.txt on www.reddit.com is `Disallow: /`. The licensed API is why
        that does not apply, and only because no page is ever fetched. If this
        test fails, the collector has started crawling."""
        seen: list[str] = []

        def handle(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            if str(request.url).startswith(TOKEN_URL):
                return httpx.Response(200, json={"access_token": "t"}, request=request)
            return httpx.Response(200, json=PAGE2, request=request)

        list(_collector(handle).collect(since=None))

        for url in seen:
            assert url.startswith(API_BASE_URL) or url.startswith(TOKEN_URL), url

    def test_the_user_agent_follows_reddits_required_shape(self):
        collector = _collector(_handler())
        assert collector.user_agent().startswith("python:my.painradar.collector:0.1")

    def test_a_configured_username_is_used_as_reddit_documents(self):
        collector = _collector(
            _handler(), credentials={**CREDS, "REDDIT_USERNAME": "louislee64"}
        )
        assert "by /u/louislee64" in collector.user_agent()

    def test_without_a_username_a_contact_url_is_sent_instead(self):
        collector = _collector(_handler())
        assert "github.com/louislee64/pain-signal-my" in collector.user_agent()


class TestParsing:
    def test_yields_one_document_per_usable_post(self):
        documents = list(_collector(_handler()).collect(since=None))

        # Page 1 has four posts: one good, one too short, one with a removed body,
        # one good. Page 2 has one good.
        ids = [d.external_id for d in documents]
        assert "reddit:aaa111" in ids
        assert "reddit:page1last" in ids
        assert "reddit:ddd444" in ids

    def test_the_title_and_body_are_combined(self):
        documents = list(_collector(_handler()).collect(since=None))
        first = next(d for d in documents if d.external_id == "reddit:aaa111")

        assert "Stock discrepancy" in first.body
        assert "reconcile manual entry" in first.body

    def test_posts_below_the_body_threshold_are_dropped(self):
        """Forums are full of one-liners; §22 cannot classify 'Too short.'"""
        documents = list(_collector(_handler()).collect(since=None))

        assert "reddit:bbb222" not in [d.external_id for d in documents]

    def test_a_removed_body_does_not_become_body_text(self):
        """`[removed]` is a tombstone, not content. Storing it would let a deleted
        post look like a real one that happened to say nothing."""
        documents = list(_collector(_handler(), {"min_body_chars": 0}).collect(since=None))
        removed = next(d for d in documents if d.external_id == "reddit:ccc333")

        assert "[removed]" not in removed.body
        assert "accounting software does not integrate" in removed.body

    def test_the_url_points_at_the_public_permalink(self):
        documents = list(_collector(_handler()).collect(since=None))
        first = next(d for d in documents if d.external_id == "reddit:aaa111")

        assert first.url == (
            "https://www.reddit.com/r/malaysia/comments/aaa111/stock_discrepancy_every_month/"
        )

    def test_created_utc_becomes_an_aware_timestamp(self):
        documents = list(_collector(_handler()).collect(since=None))
        first = next(d for d in documents if d.external_id == "reddit:aaa111")

        assert first.published_at == datetime.fromtimestamp(1786000000.0, tz=timezone.utc)
        assert first.published_at.tzinfo is not None

    def test_region_and_language_come_from_config(self):
        documents = list(_collector(_handler()).collect(since=None))

        assert documents[0].region_raw == "MY"
        assert documents[0].language_raw == "en"

    def test_external_ids_are_stable_across_runs(self):
        first = list(_collector(_handler()).collect(since=None))
        second = list(_collector(_handler()).collect(since=None))

        assert [d.external_id for d in first] == [d.external_id for d in second]
        assert [d.payload for d in first] == [d.payload for d in second]


class TestPersonalData:
    """§21. The rule that most needed enforcing on this source type."""

    def test_the_username_is_never_stored(self):
        """A Reddit handle links every post a person ever made, which makes it a
        stronger identifier than a journalist's byline, not a weaker one."""
        documents = list(_collector(_handler()).collect(since=None))

        for document in documents:
            serialised = json.dumps(document.payload, default=str)
            assert "towkay_kedai" not in serialised
            assert "another_user" not in serialised
            assert "page_two_user" not in serialised
            assert "author" not in document.payload
            assert "author_fullname" not in document.payload
            assert "author_flair_text" not in document.payload

    def test_contact_details_in_a_post_are_redacted(self):
        documents = list(_collector(_handler()).collect(since=None))
        first = next(d for d in documents if d.external_id == "reddit:aaa111")

        assert "kedai@example.test" not in first.body
        assert "012-345 6789" not in first.body
        assert "[email redacted]" in first.body
        assert "[phone redacted]" in first.body

    def test_the_payload_keeps_no_unredacted_copy(self):
        documents = list(_collector(_handler()).collect(since=None))
        first = next(d for d in documents if d.external_id == "reddit:aaa111")

        assert "kedai@example.test" not in json.dumps(first.payload, default=str)

    def test_volatile_engagement_counters_are_not_stored(self):
        """Not squeamishness — churn. score/num_comments change hourly, so
        including them would alter the content hash and mark every recent post
        'updated' on every nightly run, for data nothing consumes."""
        documents = list(_collector(_handler()).collect(since=None))

        for document in documents:
            assert "score" not in document.payload
            assert "ups" not in document.payload
            assert "num_comments" not in document.payload
            assert "upvote_ratio" not in document.payload


class TestPagination:
    def test_it_follows_the_after_cursor(self):
        urls: list[str] = []

        def handle(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(TOKEN_URL):
                return httpx.Response(200, json={"access_token": "t"}, request=request)
            urls.append(str(request.url))
            return httpx.Response(200, json=PAGE1 if len(urls) == 1 else PAGE2, request=request)

        list(_collector(handle).collect(since=None))

        assert len(urls) == 2
        assert "after=t3_page1last" in urls[1]

    def test_it_stops_when_the_listing_reports_no_more_pages(self):
        requests: list[str] = []

        def handle(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(TOKEN_URL):
                return httpx.Response(200, json={"access_token": "t"}, request=request)
            requests.append(str(request.url))
            return httpx.Response(200, json=PAGE2, request=request)

        list(_collector(handle).collect(since=None))

        assert len(requests) == 1  # PAGE2 has after: null

    def test_the_page_cap_bounds_a_run(self):
        never_ending = {
            "kind": "Listing",
            "data": {"after": "t3_more", "children": PAGE1["data"]["children"]},
        }
        requests: list[str] = []

        def handle(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(TOKEN_URL):
                return httpx.Response(200, json={"access_token": "t"}, request=request)
            requests.append(str(request.url))
            return httpx.Response(200, json=never_ending, request=request)

        list(_collector(handle, {"max_pages": 3}).collect(since=None))

        assert len(requests) == 3

    def test_an_empty_listing_ends_the_run(self):
        empty = {"kind": "Listing", "data": {"after": "t3_x", "children": []}}
        documents = list(_collector(_handler([empty])).collect(since=None))

        assert documents == []


class TestIncrementalCollection:
    def test_it_stops_at_the_last_successful_sync(self):
        """`/new` is reverse-chronological, so the first post older than `since`
        means every remaining post is older too. Not stopping would mean
        re-reading the whole subreddit every night."""
        since = datetime.fromtimestamp(1785997500.0, tz=timezone.utc)

        documents = list(_collector(_handler()).collect(since=since))

        ids = [d.external_id for d in documents]
        assert "reddit:aaa111" in ids
        assert "reddit:page1last" not in ids
        # And it never asked for page two.
        assert "reddit:ddd444" not in ids

    def test_a_first_run_takes_everything(self):
        documents = list(_collector(_handler()).collect(since=None))

        assert len(documents) >= 3

    def test_a_naive_since_would_not_crash_the_comparison(self):
        """Guards the bug that only appeared on second runs: Laravel's
        `timestamp(0)` columns return naive datetimes. The repository now labels
        them UTC, and this asserts the collector's own comparison stays sound."""
        since = datetime.fromtimestamp(1785997500.0, tz=timezone.utc)
        documents = list(_collector(_handler()).collect(since=since))

        assert documents  # did not raise


class TestRateLimiting:
    def test_it_waits_between_requests(self):
        slept: list[float] = []
        collector = RedditSubredditCollector(
            {**CONFIG, "requests_per_minute": 60},
            client=httpx.Client(transport=httpx.MockTransport(_handler())),
            credentials=CREDS,
            sleep=slept.append,
        )

        list(collector.collect(since=None))

        assert slept, "expected at least one throttle pause between requests"

    def test_reddits_own_budget_wins_when_it_says_it_is_exhausted(self):
        """`X-Ratelimit-Remaining` is better information than any static guess:
        the real budget is shared by every source using the same credentials."""
        slept: list[float] = []
        handler = _handler(
            [PAGE1, PAGE2],
            rate_headers={"X-Ratelimit-Remaining": "0", "X-Ratelimit-Reset": "42"},
        )
        collector = RedditSubredditCollector(
            CONFIG,
            client=httpx.Client(transport=httpx.MockTransport(handler)),
            credentials=CREDS,
            sleep=slept.append,
        )

        list(collector.collect(since=None))

        assert 42.0 in slept

    def test_a_malformed_rate_limit_header_is_ignored_rather_than_fatal(self):
        handler = _handler(
            [PAGE2], rate_headers={"X-Ratelimit-Remaining": "lots", "X-Ratelimit-Reset": ""}
        )
        documents = list(_collector(handler).collect(since=None))

        assert documents  # did not raise


class TestRetry:
    @patch("intelligence.retry.time.sleep")
    def test_it_retries_a_server_error(self, mock_sleep):
        attempts = {"n": 0}

        def handle(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(TOKEN_URL):
                return httpx.Response(200, json={"access_token": "t"}, request=request)
            attempts["n"] += 1
            if attempts["n"] < 2:
                return httpx.Response(503, request=request)
            return httpx.Response(200, json=PAGE2, request=request)

        documents = list(_collector(handle).collect(since=None))

        assert attempts["n"] == 2
        assert documents
        mock_sleep.assert_called_once()

    @patch("intelligence.retry.time.sleep")
    def test_a_429_is_retried(self, mock_sleep):
        attempts = {"n": 0}

        def handle(request: httpx.Request) -> httpx.Response:
            if str(request.url).startswith(TOKEN_URL):
                return httpx.Response(200, json={"access_token": "t"}, request=request)
            attempts["n"] += 1
            if attempts["n"] < 2:
                return httpx.Response(429, request=request)
            return httpx.Response(200, json=PAGE2, request=request)

        list(_collector(handle).collect(since=None))

        assert attempts["n"] == 2


class TestRegistryPosture:
    """The compliance decisions are config, so they are asserted as config."""

    def _sources(self) -> list[dict]:
        import os

        path = os.environ.get("SOURCES_REGISTRY_PATH", "/config/sources.yaml")
        if not Path(path).exists():
            parents = Path(__file__).resolve().parents
            if len(parents) > 4:
                path = str(parents[4] / "config" / "sources.yaml")
        if not Path(path).exists():
            pytest.skip(f"sources.yaml not reachable at {path}")
        return yaml.safe_load(Path(path).read_text())["sources"]

    def _reddit(self) -> list[dict]:
        return [s for s in self._sources() if s["collector"] == "reddit_subreddit"]

    def test_reddit_sources_are_registered(self):
        assert self._reddit(), "expected the Reddit sources to be in the registry"

    def test_every_reddit_source_ships_disabled(self):
        """Reddit's Data API terms restrict commercial use and §6 gives this
        project commercial intent. Enabling is a licensing decision for a human,
        so no code change should ever flip these on by default."""
        for source in self._reddit():
            assert source["enabled"] is False, source["slug"]

    def test_every_reddit_source_declares_its_terms_unreviewed(self):
        for source in self._reddit():
            assert source["terms_status"] == "needs_review", source["slug"]

    def test_reddit_carries_the_highest_personal_data_risk_in_the_registry(self):
        for source in self._reddit():
            assert source["personal_data_risk"] == "medium", source["slug"]

    def test_declared_rate_limit_matches_the_enforced_one(self):
        for source in self._reddit():
            declared = int(source["rate_limit"].split("/")[0])
            assert declared == source["config"]["requests_per_minute"], source["slug"]

    def test_the_declared_rate_stays_under_reddits_free_tier(self):
        """100/minute per OAuth client, shared across every source using the same
        credentials — so three subreddits must not be able to breach it between
        them."""
        for source in self._reddit():
            assert source["config"]["requests_per_minute"] <= 60, source["slug"]
