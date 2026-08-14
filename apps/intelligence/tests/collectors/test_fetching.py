"""Tests for the polite-fetch layer (PROJECT_SPEC.md §13, §17, §21)."""

from unittest.mock import patch

import httpx

from intelligence.collectors.fetching import (
    ArticleFetcher,
    HostRateLimiter,
    RobotsCache,
    scrub_contact_details,
)

ROBOTS_ALLOW_ALL = "User-agent: *\nDisallow:\n"
ROBOTS_BLOCK_ARTICLES = "User-agent: *\nDisallow: /articles/\n"
ROBOTS_WITH_DELAY = "User-agent: *\nDisallow:\nCrawl-delay: 10\n"

ARTICLE_HTML = """
<html><head><title>Cost pressure story</title></head><body>
<nav><a href="/business">Business</a><a href="/sport">Sport</a></nav>
<article>
<h1>Retailers report a margin squeeze</h1>
<p>Retail operators in the Klang Valley said this week that operating cost pressure
has continued to build, with several describing a margin squeeze that has forced
them to revisit supplier arrangements for the second time this year.</p>
<p>Owners also described a manual process for reconciling supplier invoices, which
they said consumes several hours each week and makes price changes hard to spot.</p>
</article>
<footer>Contact us at newsroom@example.test or 012-999 8888</footer>
</body></html>
"""


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class TestScrubContactDetails:
    """§21: the unredacted string must never reach the database."""

    def test_removes_email_addresses(self):
        result = scrub_contact_details("Write to tips@example.test for more.")
        assert "tips@example.test" not in result
        assert "[email redacted]" in result

    def test_removes_malaysian_mobile_and_landline_numbers(self):
        for number in ("012-345 6789", "03-1234 5678", "+6012-3456789", "0123456789"):
            result = scrub_contact_details(f"Call {number} today.")
            assert number not in result, number
            assert "[phone redacted]" in result, number

    def test_leaves_prices_years_and_percentages_alone(self):
        """The redaction must not eat the numbers the analysis depends on.

        A phone pattern loose enough to clip 'RM54 billion' or '2026' would
        quietly corrupt every economic signal in the corpus.
        """
        text = "In 2026 the group reported RM54 billion, up 7.4% from 1.9% in 2025."
        assert scrub_contact_details(text) == text

    def test_none_and_empty_pass_through(self):
        assert scrub_contact_details(None) is None
        assert scrub_contact_details("") == ""


class TestRobotsCache:
    def test_allows_a_path_robots_permits(self):
        robots = RobotsCache(
            client=_client(lambda r: httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=r))
        )
        assert robots.can_fetch("https://example.test/articles/1") is True

    def test_refuses_a_disallowed_path(self):
        robots = RobotsCache(
            client=_client(lambda r: httpx.Response(200, text=ROBOTS_BLOCK_ARTICLES, request=r))
        )
        assert robots.can_fetch("https://example.test/articles/1") is False
        assert robots.can_fetch("https://example.test/other/1") is True

    def test_a_missing_robots_file_permits_everything(self):
        """RFC 9309: 4xx means no restrictions exist."""
        robots = RobotsCache(client=_client(lambda r: httpx.Response(404, request=r)))
        assert robots.can_fetch("https://example.test/articles/1") is True

    def test_an_unreachable_robots_file_refuses_everything(self):
        """RFC 9309 draws the opposite conclusion from 5xx, and so must we.

        Treating "we could not read the rules" as "there are no rules" is how a
        crawler ends up ignoring a robots.txt that was merely behind a flaky
        proxy — the failure is invisible and the behaviour is wrong.
        """
        robots = RobotsCache(client=_client(lambda r: httpx.Response(503, request=r)))
        assert robots.can_fetch("https://example.test/articles/1") is False

    def test_a_network_error_also_refuses(self):
        def boom(request):
            raise httpx.ConnectError("no route to host", request=request)

        robots = RobotsCache(client=_client(boom))
        assert robots.can_fetch("https://example.test/articles/1") is False

    def test_robots_is_fetched_once_per_host(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=request)

        robots = RobotsCache(client=_client(handler))
        for i in range(5):
            robots.can_fetch(f"https://example.test/articles/{i}")

        assert calls["n"] == 1

    def test_reports_crawl_delay_when_declared(self):
        robots = RobotsCache(
            client=_client(lambda r: httpx.Response(200, text=ROBOTS_WITH_DELAY, request=r))
        )
        assert robots.crawl_delay("https://example.test/articles/1") == 10.0


class TestHostRateLimiter:
    def test_first_request_to_a_host_does_not_wait(self):
        limiter = HostRateLimiter(requests_per_minute=20)
        assert limiter.delay_for("example.test") == 0.0

    def test_second_request_waits_the_configured_interval(self):
        clock = {"t": 100.0}
        slept: list[float] = []
        limiter = HostRateLimiter(
            requests_per_minute=20, sleep=slept.append, clock=lambda: clock["t"]
        )

        limiter.wait("https://example.test/a")
        limiter.wait("https://example.test/b")

        assert slept == [3.0]  # 60 / 20

    def test_hosts_are_tracked_independently(self):
        clock = {"t": 100.0}
        slept: list[float] = []
        limiter = HostRateLimiter(
            requests_per_minute=20, sleep=slept.append, clock=lambda: clock["t"]
        )

        limiter.wait("https://one.test/a")
        limiter.wait("https://two.test/a")

        # Talking to one publisher is not a reason to keep another waiting.
        assert slept == []

    def test_a_publishers_crawl_delay_wins_when_it_asks_for_more_patience(self):
        clock = {"t": 100.0}
        slept: list[float] = []
        limiter = HostRateLimiter(
            requests_per_minute=20, sleep=slept.append, clock=lambda: clock["t"]
        )

        limiter.wait("https://example.test/a", crawl_delay=10.0)
        limiter.wait("https://example.test/b", crawl_delay=10.0)

        assert slept == [10.0]

    def test_a_zero_crawl_delay_is_not_an_invitation_to_go_faster(self):
        clock = {"t": 100.0}
        slept: list[float] = []
        limiter = HostRateLimiter(
            requests_per_minute=20, sleep=slept.append, clock=lambda: clock["t"]
        )

        limiter.wait("https://example.test/a", crawl_delay=0.0)
        limiter.wait("https://example.test/b", crawl_delay=0.0)

        assert slept == [3.0]


class TestArticleFetcher:
    def _fetcher(self, handler, **kwargs) -> ArticleFetcher:
        client = _client(handler)
        return ArticleFetcher(
            client=client,
            robots=RobotsCache(
                client=_client(lambda r: httpx.Response(200, text=ROBOTS_ALLOW_ALL, request=r))
            ),
            rate_limiter=HostRateLimiter(requests_per_minute=20, sleep=lambda _: None),
            **kwargs,
        )

    def test_extracts_the_article_body(self):
        fetcher = self._fetcher(lambda r: httpx.Response(200, text=ARTICLE_HTML, request=r))

        result = fetcher.fetch("https://example.test/articles/1")

        assert result.skipped_reason is None
        assert "margin squeeze" in result.text
        # Navigation is not article text, and letting it through would let a
        # site's own menu match topic keywords.
        assert "Sport" not in result.text

    def test_scrubs_contact_details_from_the_extracted_body(self):
        fetcher = self._fetcher(lambda r: httpx.Response(200, text=ARTICLE_HTML, request=r))

        result = fetcher.fetch("https://example.test/articles/1")

        assert "newsroom@example.test" not in (result.text or "")
        assert "012-999 8888" not in (result.text or "")

    def test_a_disallowed_url_is_skipped_not_fetched(self):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, text=ARTICLE_HTML, request=request)

        fetcher = ArticleFetcher(
            client=_client(handler),
            robots=RobotsCache(
                client=_client(lambda r: httpx.Response(200, text=ROBOTS_BLOCK_ARTICLES, request=r))
            ),
            rate_limiter=HostRateLimiter(sleep=lambda _: None),
        )

        result = fetcher.fetch("https://example.test/articles/1")

        assert result.text is None
        assert result.skipped_reason == "robots_disallowed"
        assert calls["n"] == 0

    @patch("intelligence.retry.time.sleep")
    def test_a_failed_fetch_reports_a_reason_rather_than_raising(self, _sleep):
        fetcher = self._fetcher(lambda r: httpx.Response(404, request=r))

        result = fetcher.fetch("https://example.test/articles/1")

        assert result.text is None
        assert result.skipped_reason == "fetch_failed"

    @patch("intelligence.retry.time.sleep")
    def test_retries_a_server_error_then_succeeds(self, mock_sleep):
        attempts = {"n": 0}

        def handler(request):
            attempts["n"] += 1
            if attempts["n"] < 2:
                return httpx.Response(503, request=request)
            return httpx.Response(200, text=ARTICLE_HTML, request=request)

        fetcher = self._fetcher(handler)

        result = fetcher.fetch("https://example.test/articles/1")

        assert attempts["n"] == 2
        assert result.text is not None
        mock_sleep.assert_called_once()

    def test_a_page_with_no_extractable_body_reports_why(self):
        fetcher = self._fetcher(
            lambda r: httpx.Response(200, text="<html><body></body></html>", request=r)
        )

        result = fetcher.fetch("https://example.test/articles/1")

        assert result.text is None
        assert result.skipped_reason == "extraction_empty"
