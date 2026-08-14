"""Tests for the RSS/Atom collector (PROJECT_SPEC.md §13, §17, §21, §38)."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import yaml

from intelligence.collectors.base import FetchState, SourceUnchanged
from intelligence.collectors.fetching import ArticleFetcher, HostRateLimiter, RobotsCache
from intelligence.collectors.registry import get_collector_class
from intelligence.collectors.rss import RssFeedCollector

FIXTURES = Path(__file__).parent.parent / "fixtures"
FULL_FEED = (FIXTURES / "rss_full_content.xml").read_bytes()
HEADLINES_FEED = (FIXTURES / "rss_headlines_only.xml").read_bytes()
ATOM_FEED = (FIXTURES / "atom_feed.xml").read_bytes()

FEED_URL = "https://example.test/business/feed/"

ROBOTS_ALLOW_ALL = "User-agent: *\nDisallow:\n"

ARTICLE_HTML = """
<html><body><article>
<h1>Retailers say labour shortage is worsening</h1>
<p>Retail operators said this week that a labour shortage has worsened through the
quarter, with several outlets reducing opening hours because they cannot fill
positions. Owners described staff turnover as the highest they have seen.</p>
<p>Industry representatives said the manual process of rostering across several
outlets compounds the problem, and asked for clearer guidance on hiring rules.</p>
</article></body></html>
"""


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _feed_client(body: bytes, *, headers: dict | None = None, status: int = 200) -> httpx.Client:
    return _client(lambda r: httpx.Response(status, content=body, headers=headers or {}, request=r))


def _article_fetcher(handler=None) -> ArticleFetcher:
    handler = handler or (lambda r: httpx.Response(200, text=ARTICLE_HTML, request=r))
    return ArticleFetcher(
        client=_client(handler),
        robots=RobotsCache(
            client=_client(lambda r: httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=r))
        ),
        rate_limiter=HostRateLimiter(sleep=lambda _: None),
    )


class TestRegistration:
    def test_the_collector_is_reachable_by_name(self):
        """Config names a collector; a class nothing can resolve is unusable."""
        assert get_collector_class("rss_feed") is RssFeedCollector

    def test_a_missing_feed_url_fails_with_an_actionable_message(self):
        with pytest.raises(ValueError, match="feed_url"):
            RssFeedCollector({})


class TestParsing:
    def test_yields_one_document_per_entry(self):
        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": False}, client=_feed_client(FULL_FEED)
        )

        documents = list(collector.collect(since=None))

        assert len(documents) == 3
        assert documents[0].title == "SME owners report rising operating cost pressure"
        assert documents[0].url == "https://example.test/business/2026/08/14/sme-cost-pressure"
        assert documents[0].published_at == datetime(2026, 8, 14, 4, 30, tzinfo=timezone.utc)

    def test_prefers_the_longest_body_the_feed_offers(self):
        """The fixture's `description` is a teaser and `content:encoded` is the
        article. Taking the nominally-richer field blindly would be right here
        but wrong on feeds that invert them, so the rule is longest-wins."""
        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": False}, client=_feed_client(FULL_FEED)
        )

        documents = list(collector.collect(since=None))

        assert "Klang Valley" in documents[0].body
        assert "should lose to the longer" not in documents[0].body

    def test_html_is_stripped_from_the_stored_body(self):
        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": False}, client=_feed_client(FULL_FEED)
        )

        documents = list(collector.collect(since=None))

        assert "<p>" not in documents[0].body

    def test_parses_atom_as_well_as_rss(self):
        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": False}, client=_feed_client(ATOM_FEED)
        )

        documents = list(collector.collect(since=None))

        assert len(documents) == 1
        assert "manual reporting" in documents[0].body
        assert documents[0].external_id == "urn:uuid:atom-entry-0001"

    def test_language_and_region_come_from_config(self):
        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": False, "language": "ms", "region": "MY"},
            client=_feed_client(FULL_FEED),
        )

        documents = list(collector.collect(since=None))

        assert documents[0].language_raw == "ms"
        assert documents[0].region_raw == "MY"

    def test_a_source_may_decline_to_claim_a_region(self):
        """vulcanpost_my is configured this way: mostly non-Malaysian content, so
        asserting `MY` would be a claim the text does not support (§41)."""
        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": False, "region": None},
            client=_feed_client(FULL_FEED),
        )

        documents = list(collector.collect(since=None))

        assert documents[0].region_raw is None

    def test_an_unparseable_feed_fails_the_run_rather_than_reporting_success(self):
        """§41: a broken collector must not look like a source with no news."""
        collector = RssFeedCollector(
            {"feed_url": FEED_URL}, client=_feed_client(b"this is not xml at all")
        )

        with pytest.raises(RuntimeError, match="Could not parse feed"):
            list(collector.collect(since=None))


class TestExternalIds:
    def test_uses_the_feeds_own_guid(self):
        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": False}, client=_feed_client(FULL_FEED)
        )

        documents = list(collector.collect(since=None))

        assert documents[0].external_id == "https://example.test/business/2026/08/14/sme-cost-pressure"

    def test_an_over_long_guid_is_hashed_not_truncated(self):
        """raw_documents.external_id is varchar(255) with a unique index. Two long
        URLs sharing a 255-character prefix would collapse into one document if
        this truncated instead of hashing."""
        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": False}, client=_feed_client(FULL_FEED)
        )

        documents = list(collector.collect(since=None))

        assert documents[1].external_id.startswith("sha256:")
        assert len(documents[1].external_id) <= 255

    def test_an_entry_with_no_guid_falls_back_to_its_link(self):
        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": False}, client=_feed_client(FULL_FEED)
        )

        documents = list(collector.collect(since=None))

        assert documents[2].external_id == "https://example.test/business/2026/08/12/no-guid-story"

    def test_ids_are_stable_across_runs(self):
        """Idempotency (§13) is only as good as the natural key."""
        first = list(
            RssFeedCollector(
                {"feed_url": FEED_URL, "fetch_articles": False}, client=_feed_client(FULL_FEED)
            ).collect(since=None)
        )
        second = list(
            RssFeedCollector(
                {"feed_url": FEED_URL, "fetch_articles": False}, client=_feed_client(FULL_FEED)
            ).collect(since=None)
        )

        assert [d.external_id for d in first] == [d.external_id for d in second]
        assert [d.payload for d in first] == [d.payload for d in second]


class TestPersonalData:
    """§21, and the reason the raw/redacted trade-off is documented."""

    def test_the_byline_is_never_stored(self):
        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": False}, client=_feed_client(FULL_FEED)
        )

        documents = list(collector.collect(since=None))
        serialised = str(documents[0].payload)

        assert "Jane Reporter" not in serialised
        assert "author" not in documents[0].payload
        assert "creator" not in documents[0].payload

    def test_atom_author_names_are_dropped_too(self):
        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": False}, client=_feed_client(ATOM_FEED)
        )

        documents = list(collector.collect(since=None))

        assert "Atom Byline" not in str(documents[0].payload)

    def test_contact_details_in_the_feed_body_are_redacted(self):
        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": False}, client=_feed_client(FULL_FEED)
        )

        documents = list(collector.collect(since=None))

        assert "tips@example.test" not in documents[0].body
        assert "012-345 6789" not in documents[0].body
        assert "03-1234 5678" not in documents[0].body
        assert "[email redacted]" in documents[0].body

    def test_the_payload_keeps_no_unredacted_copy(self):
        """Storing the raw summary beside the redacted body would defeat the point."""
        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": False}, client=_feed_client(FULL_FEED)
        )

        documents = list(collector.collect(since=None))

        assert "tips@example.test" not in str(documents[0].payload)


class TestArticleFallback:
    def test_a_thin_entry_is_completed_from_the_article_page(self):
        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": True},
            client=_feed_client(HEADLINES_FEED),
            article_fetcher=_article_fetcher(),
        )

        documents = list(collector.collect(since=None))

        assert "labour shortage has worsened" in documents[0].body
        assert documents[0].payload["body_source"] == "article"

    def test_a_full_entry_is_never_fetched(self):
        """Politeness and cost: the body is already here."""
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, text=ARTICLE_HTML, request=request)

        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": True},
            client=_feed_client(FULL_FEED),
            article_fetcher=_article_fetcher(handler),
        )

        documents = list(collector.collect(since=None))

        # Entry 0 is long enough to stand alone; entries 1 and 2 are short.
        assert documents[0].payload["body_source"] == "feed"
        assert calls["n"] == 2

    def test_fetching_can_be_switched_off_entirely(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, text=ARTICLE_HTML, request=request)

        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": False},
            client=_feed_client(HEADLINES_FEED),
            article_fetcher=_article_fetcher(handler),
        )

        documents = list(collector.collect(since=None))

        assert calls["n"] == 0
        assert all(d.payload["body_source"] == "feed" for d in documents)

    def test_the_per_run_cap_is_honoured_and_recorded(self):
        """A silently truncated run would look like a source with less to say."""
        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": True, "max_article_fetches": 1},
            client=_feed_client(HEADLINES_FEED),
            article_fetcher=_article_fetcher(),
        )

        documents = list(collector.collect(since=None))

        assert documents[0].payload["body_source"] == "article"
        assert documents[1].payload["body_source"] == "feed"
        assert documents[1].payload["body_fetch_note"] == "per_run_cap_reached"

    def test_a_blocked_page_keeps_the_headline_and_says_why(self):
        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": True},
            client=_feed_client(HEADLINES_FEED),
            article_fetcher=ArticleFetcher(
                client=_client(lambda r: httpx.Response(200, text=ARTICLE_HTML, request=r)),
                robots=RobotsCache(
                    client=_client(
                        lambda r: httpx.Response(
                            200, text="User-agent: *\nDisallow: /articles/\n", request=r
                        )
                    )
                ),
                rate_limiter=HostRateLimiter(sleep=lambda _: None),
            ),
        )

        documents = list(collector.collect(since=None))

        assert documents[0].title == "Retailers say labour shortage is worsening"
        assert documents[0].payload["body_source"] == "feed"
        assert documents[0].payload["body_fetch_note"] == "robots_disallowed"

    def test_contact_details_in_a_fetched_article_are_redacted(self):
        html = (
            "<html><body><article><p>"
            + ("Owners described a manual process for rostering staff. " * 12)
            + "Contact desk@example.test or 019-888 7777.</p></article></body></html>"
        )
        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": True},
            client=_feed_client(HEADLINES_FEED),
            article_fetcher=_article_fetcher(lambda r: httpx.Response(200, text=html, request=r)),
        )

        documents = list(collector.collect(since=None))

        assert "desk@example.test" not in documents[0].body
        assert "019-888 7777" not in documents[0].body


class TestConditionalFetch:
    """§38. This path was written for data.gov.my, which sends neither validator,
    so until RSS arrived it had never actually engaged against a live source."""

    def test_sends_the_stored_validators(self):
        captured: dict = {}

        def handler(request):
            captured.update(request.headers)
            return httpx.Response(200, content=FULL_FEED, request=request)

        collector = RssFeedCollector({"feed_url": FEED_URL}, client=_client(handler))

        list(
            collector.collect(
                since=None,
                fetch_state=FetchState(etag='"abc123"', last_modified="Wed, 13 Aug 2026 02:00:00 GMT"),
            )
        )

        assert captured["if-none-match"] == '"abc123"'
        assert captured["if-modified-since"] == "Wed, 13 Aug 2026 02:00:00 GMT"

    def test_a_304_is_reported_as_unchanged_not_as_an_error(self):
        collector = RssFeedCollector(
            {"feed_url": FEED_URL}, client=_feed_client(b"", status=304)
        )

        with pytest.raises(SourceUnchanged):
            list(collector.collect(since=None, fetch_state=FetchState(etag='"abc123"')))

    def test_records_the_validators_the_feed_returned(self):
        collector = RssFeedCollector(
            {"feed_url": FEED_URL},
            client=_feed_client(
                FULL_FEED,
                headers={"ETag": '"v2"', "Last-Modified": "Thu, 14 Aug 2026 06:00:00 GMT"},
            ),
        )

        list(collector.collect(since=None))

        assert collector.fetch_state().etag == '"v2"'
        assert collector.fetch_state().last_modified == "Thu, 14 Aug 2026 06:00:00 GMT"


class TestIncrementalCollection:
    def test_entries_already_seen_are_skipped(self):
        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": False}, client=_feed_client(FULL_FEED)
        )

        documents = list(collector.collect(since=datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)))

        assert len(documents) == 1
        assert documents[0].published_at == datetime(2026, 8, 14, 4, 30, tzinfo=timezone.utc)

    def test_skipping_old_entries_saves_the_article_fetch(self):
        """The upsert is idempotent anyway; the point is not re-fetching pages."""
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, text=ARTICLE_HTML, request=request)

        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": True},
            client=_feed_client(HEADLINES_FEED),
            article_fetcher=_article_fetcher(handler),
        )

        list(collector.collect(since=datetime(2026, 8, 14, 7, 0, tzinfo=timezone.utc)))

        assert calls["n"] == 0


class TestRetry:
    @patch("intelligence.retry.time.sleep")
    def test_retries_a_server_error(self, mock_sleep):
        attempts = {"n": 0}

        def handler(request):
            attempts["n"] += 1
            if attempts["n"] < 2:
                return httpx.Response(503, request=request)
            return httpx.Response(200, content=FULL_FEED, request=request)

        collector = RssFeedCollector(
            {"feed_url": FEED_URL, "fetch_articles": False}, client=_client(handler)
        )

        documents = list(collector.collect(since=None))

        assert attempts["n"] == 2
        assert len(documents) == 3
        mock_sleep.assert_called_once()


class TestRegistryConsistency:
    """The declared rate limit and the enforced one must agree.

    `rate_limit` is the human-facing declaration shown on the /sources page;
    `config.requests_per_minute` is what the collector actually enforces. Nothing
    links them at runtime, so a mismatch would make the compliance posture on
    that page a fiction. Cheap to assert, and the kind of drift nobody notices.
    """

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

    def test_declared_rate_limit_matches_the_enforced_one(self):
        for source in self._sources():
            if source["collector"] != "rss_feed":
                continue
            declared = source.get("rate_limit")
            enforced = source.get("config", {}).get("requests_per_minute")
            assert declared is not None, f"{source['slug']} declares no rate_limit"
            assert enforced is not None, f"{source['slug']} sets no requests_per_minute"
            per_minute = int(declared.split("/")[0])
            assert per_minute == enforced, (
                f"{source['slug']} declares {declared} on the sources page but enforces "
                f"{enforced}/minute"
            )

    def test_every_rss_source_declares_a_feed_url(self):
        for source in self._sources():
            if source["collector"] != "rss_feed":
                continue
            assert source.get("config", {}).get("feed_url"), source["slug"]

    def test_only_feeds_that_need_it_fetch_article_pages(self):
        """Full-text extraction is the part with an unresolved terms question, so
        it must stay confined to the feeds that publish nothing else.

        Exactly one feed qualifies. businesstoday_my is also headline-thin but
        returns 403 to our declared User-Agent, so it is off by measurement
        rather than by policy — see the note in sources.yaml.
        """
        fetching = [
            s["slug"]
            for s in self._sources()
            if s["collector"] == "rss_feed" and s.get("config", {}).get("fetch_articles")
        ]
        assert sorted(fetching) == ["thevibes_business"]
