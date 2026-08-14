"""Polite web fetching for text sources (PROJECT_SPEC.md §13, §17, §21).

§13 places "public web collection where permitted" last in the acquisition
order, and §17 spells out the obligations that come with it: review robots
policy, avoid bypassing technical controls, store only what analysis needs.
This module is where those obligations are actually enforced, so a collector
cannot accidentally skip them.

Three separate concerns live here, deliberately not merged:

  RobotsCache    — may we fetch this URL at all?
  HostRateLimiter — how fast may we fetch from this host?
  scrub_contact_details — what must never reach the database?

The first two are about being a well-behaved client. The third is about §21,
and it runs on every piece of text regardless of where the text came from.
"""

import re
import time
import urllib.robotparser
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse

import httpx

from intelligence.observability import get_logger, log_event
from intelligence.retry import call_with_retry

logger = get_logger("intelligence.collectors.fetching")

# Identify honestly, with a URL a publisher can use to find out who we are and
# complain. An anonymous or spoofed browser UA would be exactly the "bypassing
# technical controls" §17 rules out.
DEFAULT_USER_AGENT = (
    "PainRadarBot/0.1 (Malaysia SME Pain Radar; "
    "+https://github.com/louislee64/pain-signal-my)"
)

DEFAULT_TIMEOUT_SECONDS = 20.0

# Conservative default: 20 requests/minute is one every three seconds, which is
# slower than a human clicking through articles. A publisher's own Crawl-delay
# always wins when it asks for more (see HostRateLimiter.delay_for).
DEFAULT_REQUESTS_PER_MINUTE = 20

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class RobotsDisallowed(Exception):
    """robots.txt forbids fetching this URL.

    Not an error the run should fail on — the correct response is to skip the
    article and keep whatever the feed itself provided.
    """


class RobotsCache:
    """One robots.txt per host, fetched once per process.

    Failure handling follows RFC 9309 §2.3.1, which distinguishes two cases that
    are easy to collapse and mean opposite things:

      4xx ("unavailable")  -> no restrictions exist; allow.
      5xx / network error ("unreachable") -> we do not know what the rules are,
                                             so assume the strictest; disallow.

    Collapsing them into "allow on any failure" is how a crawler ends up
    ignoring a robots.txt that was merely behind a flaky proxy.
    """

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        client: httpx.Client | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.user_agent = user_agent
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self._parsers: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        # Hosts we could not reach robots.txt for, and must therefore refuse.
        self._unreachable: set[str] = set()

    def _robots_url(self, url: str) -> tuple[str, str]:
        parts = urlparse(url)
        host = f"{parts.scheme}://{parts.netloc}"
        return host, urlunparse((parts.scheme, parts.netloc, "/robots.txt", "", "", ""))

    def _parser_for(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        host, robots_url = self._robots_url(url)

        if host in self._parsers:
            return self._parsers[host]
        if host in self._unreachable:
            return None

        try:
            response = self._client.get(robots_url, headers={"User-Agent": self.user_agent})
        except httpx.HTTPError as exc:
            log_event(logger, "robots.unreachable", host=host, error=str(exc))
            self._unreachable.add(host)
            return None

        if response.status_code >= 500:
            log_event(logger, "robots.unreachable", host=host, status=response.status_code)
            self._unreachable.add(host)
            return None

        parser = urllib.robotparser.RobotFileParser()
        if response.status_code >= 400:
            # No robots.txt published: nothing is disallowed. `parse([])` gives a
            # parser that permits everything, which is the correct reading.
            log_event(logger, "robots.absent", host=host, status=response.status_code)
            parser.parse([])
        else:
            parser.parse(response.text.splitlines())
            log_event(logger, "robots.loaded", host=host, bytes=len(response.text))

        self._parsers[host] = parser
        return parser

    def can_fetch(self, url: str) -> bool:
        parser = self._parser_for(url)
        if parser is None:
            return False
        return parser.can_fetch(self.user_agent, url)

    def crawl_delay(self, url: str) -> float | None:
        parser = self._parser_for(url)
        if parser is None:
            return None
        delay = parser.crawl_delay(self.user_agent)
        if delay is None:
            delay = parser.crawl_delay("*")
        return float(delay) if delay is not None else None


@dataclass
class HostRateLimiter:
    """Minimum interval between requests, tracked per host.

    Per host rather than globally: two publishers are two unrelated servers, and
    making a request to one is not a reason to keep the other waiting.
    """

    requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE
    sleep: object = field(default=time.sleep)
    clock: object = field(default=time.monotonic)
    _last_request: dict[str, float] = field(default_factory=dict)

    def delay_for(self, host: str, crawl_delay: float | None = None) -> float:
        """Seconds this host must wait before its next request.

        A publisher's Crawl-delay wins whenever it asks for *more* patience than
        our own setting; it is never used to go faster than configured, because
        a site declaring `Crawl-delay: 0` is not an invitation to hammer it.
        """
        configured = 60.0 / max(1, self.requests_per_minute)
        interval = max(configured, crawl_delay or 0.0)

        last = self._last_request.get(host)
        if last is None:
            return 0.0
        return max(0.0, interval - (self.clock() - last))

    def wait(self, url: str, crawl_delay: float | None = None) -> float:
        host = urlparse(url).netloc
        delay = self.delay_for(host, crawl_delay)
        if delay > 0:
            self.sleep(delay)
        self._last_request[host] = self.clock()
        return delay


# §21: "Avoid collecting unnecessary personal information." Full-article text is
# the first place in this project where free-form human text is stored, and a
# news article can carry a contact email or a mobile number ("call 012-345 6789
# for enquiries"). Neither is needed to detect a business problem.
#
# Redaction happens before the text is stored, not after — §21 is a rule about
# what we collect, so the unredacted string must never reach the database at
# all. The trade-off against §18's immutable-raw principle is real and is
# recorded in docs/architecture.md: provenance is preserved as source + URL +
# feed entry + timestamp, not as a byte-identical copy of the publisher's HTML.
#
# The marker is left visible rather than deleting silently, so a reader can tell
# that something was removed and does not read the result as the original text.
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]*[\w]")

# Malaysian phone shapes: 012-345 6789, 03-1234 5678, +6012-3456789, 60123456789.
# Bounded by (?<!\d)/(?!\d) so a longer digit run (a price, an ID) is not clipped
# in the middle and mistaken for a number.
MY_PHONE_PATTERN = re.compile(r"(?<!\d)(?:\+?60|0)[\s.-]?1?\d[\s.-]?\d{3,4}[\s.-]?\d{4}(?!\d)")

EMAIL_REDACTION = "[email redacted]"
PHONE_REDACTION = "[phone redacted]"


def scrub_contact_details(text: str | None) -> str | None:
    """Remove direct contact details from free-form text (§21)."""
    if not text:
        return text
    scrubbed = EMAIL_PATTERN.sub(EMAIL_REDACTION, text)
    return MY_PHONE_PATTERN.sub(PHONE_REDACTION, scrubbed)


@dataclass(frozen=True)
class ArticleFetchResult:
    url: str
    text: str | None
    skipped_reason: str | None = None


class ArticleFetcher:
    """Fetch and extract the body of one article page.

    Every fetch passes robots first and the rate limiter second. Extraction
    failure returns `text=None` with a reason rather than raising: a publisher
    whose markup trafilatura cannot read is a normal event, and the feed summary
    we already have is still worth keeping.
    """

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
        robots: RobotsCache | None = None,
        rate_limiter: HostRateLimiter | None = None,
    ):
        self.user_agent = user_agent
        self._client = client or httpx.Client(timeout=timeout, follow_redirects=True)
        self._robots = robots if robots is not None else RobotsCache(
            user_agent=user_agent, client=self._client, timeout=timeout
        )
        self._rate_limiter = rate_limiter or HostRateLimiter(requests_per_minute=requests_per_minute)

    def fetch(self, url: str) -> ArticleFetchResult:
        if not self._robots.can_fetch(url):
            log_event(logger, "article.robots_disallowed", url=url)
            return ArticleFetchResult(url=url, text=None, skipped_reason="robots_disallowed")

        self._rate_limiter.wait(url, crawl_delay=self._robots.crawl_delay(url))

        def get() -> httpx.Response:
            response = self._client.get(url, headers={"User-Agent": self.user_agent})
            response.raise_for_status()
            return response

        try:
            response = call_with_retry(get, is_retryable=is_retryable_http_error)
        except httpx.HTTPError as exc:
            log_event(logger, "article.fetch_failed", url=url, error=str(exc))
            return ArticleFetchResult(url=url, text=None, skipped_reason="fetch_failed")

        text = extract_article_text(response.text, url=url)
        if not text:
            log_event(logger, "article.extraction_empty", url=url)
            return ArticleFetchResult(url=url, text=None, skipped_reason="extraction_empty")

        return ArticleFetchResult(url=url, text=scrub_contact_details(text))


def extract_article_text(html: str, *, url: str | None = None) -> str | None:
    """Main article body from an HTML page, or None if nothing usable was found.

    Imported lazily: trafilatura pulls in lxml and friends, and nothing in the
    scoring, reporting or API paths should pay that import cost to run a test
    that never touches an article page.
    """
    import trafilatura

    return trafilatura.extract(
        html,
        url=url,
        # Comments are other people's words about the article, not the article,
        # and they are the most personal-data-dense part of a news page (§21).
        include_comments=False,
        include_tables=False,
        # Precision over recall: a short clean body beats a long one padded with
        # navigation and related-article headlines, which would otherwise match
        # topic keywords and manufacture signals from a site's own menu.
        favor_precision=True,
        output_format="txt",
    )


def is_retryable_http_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS_CODES
    return isinstance(exc, httpx.TransportError)
