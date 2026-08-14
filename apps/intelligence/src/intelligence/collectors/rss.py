"""RSS/Atom feed collector (PROJECT_SPEC.md §13 tier 3, §17).

Adding another feed is a config-only change: one `config/sources.yaml` entry
with `collector: rss_feed` and a `feed_url`. See docs/text-sources.md.

Two things make this more than a parse-and-store loop, and both are driven by
what Malaysian publishers actually serve (measured — see docs/text-sources.md):

  * Some feeds carry the whole article in `content:encoded` (2-9k characters);
    others carry a headline and nothing else. So the body may have to come from
    the article page, and that fetch is governed by robots + rate limits in
    collectors/fetching.py.

  * Several feeds send ETag/Last-Modified. §38's conditional-fetch path was
    written for data.gov.my, which sends neither, so until now it has never
    actually engaged. Here it does.
"""

import hashlib
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
from intelligence.collectors.fetching import (
    DEFAULT_REQUESTS_PER_MINUTE,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_USER_AGENT,
    ArticleFetcher,
    is_retryable_http_error,
    scrub_contact_details,
)
from intelligence.observability import get_logger, log_event
from intelligence.retry import call_with_retry

logger = get_logger("intelligence.collectors.rss")

# Below this many characters, a feed entry is a headline rather than an article,
# and there is not enough text for topic classification (§22) to say anything.
# Measured against live feeds: full-content feeds land at 2000-9000 characters,
# summary-only feeds at 0-430. Anything in between is ambiguous, and 600 sits in
# the empty gap between the two populations rather than at a round number.
DEFAULT_MIN_BODY_CHARS = 600

# A hard ceiling on article fetches per run. At the default rate limit each fetch
# costs ~3 seconds, so an unbounded run against a 100-entry headline-only feed
# would hold the source's ingestion open for five minutes. The cap is logged
# whenever it bites — a silently truncated run would look like a source that had
# less to say than it did.
DEFAULT_MAX_ARTICLE_FETCHES = 25

# Fields copied from the parsed entry into the stored payload for provenance.
# `author`/`dc:creator` is deliberately absent: every live feed measured carries
# a byline, and a journalist's name is personal information that no part of this
# system needs (§21). Dropping it at collection is the only way it is never
# stored.
PROVENANCE_FIELDS = ("id", "guidislink", "link", "title", "summary", "published", "updated")


class RssFeedCollector(Collector):
    """Collect entries from one RSS or Atom feed.

    Required `config` key: `feed_url`.

    Optional:
      fetch_articles       bool  default True   — fetch the page when the feed body is thin
      min_body_chars       int   default 600    — threshold for "thin"
      max_article_fetches  int   default 25     — per-run ceiling on page fetches
      requests_per_minute  int   default 20     — per-host politeness
      language             str   default "en"   — the feed's own language; normalize.py
                                                  still detects per document (§43)
      region               str   default "MY"
      user_agent           str
    """

    def __init__(
        self,
        config: dict[str, Any],
        *,
        client: httpx.Client | None = None,
        article_fetcher: ArticleFetcher | None = None,
    ):
        super().__init__(config)
        try:
            self.feed_url = config["feed_url"]
        except KeyError:
            raise ValueError(
                "rss_feed collector requires a 'feed_url' in the source's config block"
            ) from None

        self.fetch_articles: bool = config.get("fetch_articles", True)
        self.min_body_chars: int = config.get("min_body_chars", DEFAULT_MIN_BODY_CHARS)
        self.max_article_fetches: int = config.get(
            "max_article_fetches", DEFAULT_MAX_ARTICLE_FETCHES
        )
        self.language: str = config.get("language", "en")
        self.region: str | None = config.get("region", "MY")

        user_agent = config.get("user_agent", DEFAULT_USER_AGENT)
        requests_per_minute = config.get("requests_per_minute", DEFAULT_REQUESTS_PER_MINUTE)

        self._user_agent = user_agent
        self._client = client or httpx.Client(
            timeout=DEFAULT_TIMEOUT_SECONDS, follow_redirects=True
        )
        self._article_fetcher = article_fetcher
        self._requests_per_minute = requests_per_minute
        self._fetch_state = FetchState()

    def _articles(self) -> ArticleFetcher:
        # Built on first use so a run against a full-content feed never
        # constructs a fetcher, and so tests that inject one are not paying for
        # a second httpx client.
        if self._article_fetcher is None:
            self._article_fetcher = ArticleFetcher(
                user_agent=self._user_agent,
                requests_per_minute=self._requests_per_minute,
                client=self._client,
            )
        return self._article_fetcher

    def collect(
        self, since: datetime | None, fetch_state: FetchState | None = None
    ) -> Iterable[CollectedDocument]:
        import feedparser

        headers = {"User-Agent": self._user_agent}
        if fetch_state is not None:
            if fetch_state.etag:
                headers["If-None-Match"] = fetch_state.etag
            if fetch_state.last_modified:
                headers["If-Modified-Since"] = fetch_state.last_modified

        def get() -> httpx.Response:
            response = self._client.get(self.feed_url, headers=headers)
            if response.status_code == 304:
                return response
            response.raise_for_status()
            return response

        response = call_with_retry(get, is_retryable=is_retryable_http_error)

        self._fetch_state = FetchState(
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )

        if response.status_code == 304:
            raise SourceUnchanged(f"{self.feed_url} reports the feed unchanged since the last sync")

        parsed = feedparser.parse(response.content)

        # feedparser sets `bozo` on anything it had to repair. Publishers ship
        # malformed feeds constantly and feedparser usually recovers, so a
        # repaired feed with entries is worth using; a broken feed with no
        # entries is a failure that must be visible rather than reported as a
        # successful run that happened to find nothing (§41).
        if getattr(parsed, "bozo", 0) and not parsed.entries:
            raise RuntimeError(
                f"Could not parse feed {self.feed_url}: "
                f"{getattr(parsed, 'bozo_exception', 'no entries and no usable XML')}"
            )
        if getattr(parsed, "bozo", 0):
            log_event(
                logger,
                "rss.feed_repaired",
                feed_url=self.feed_url,
                entries=len(parsed.entries),
                error=str(getattr(parsed, "bozo_exception", "")),
            )

        fetched = 0
        skipped_old = 0
        capped = 0

        for entry in parsed.entries:
            published = _entry_datetime(entry)

            # Client-side incremental filter: RSS has no server-side date
            # parameter, so `since` can only be applied after parsing. Its real
            # value is not saving the upsert — that is already idempotent — but
            # not spending an article fetch on an entry we stored last night.
            if since is not None and published is not None and published <= since:
                skipped_old += 1
                continue

            feed_body = _entry_body(entry)
            body = feed_body
            body_source = "feed"
            fetch_note: str | None = None

            needs_article = self.fetch_articles and len(feed_body) < self.min_body_chars
            link = entry.get("link")

            if needs_article and link:
                if fetched >= self.max_article_fetches:
                    capped += 1
                    fetch_note = "per_run_cap_reached"
                else:
                    fetched += 1
                    result = self._articles().fetch(link)
                    if result.text:
                        body = result.text
                        body_source = "article"
                    else:
                        # Keep the headline. A thin document is worth storing —
                        # it is still evidence the story ran — and pretending the
                        # fetch never happened would hide why the body is short.
                        fetch_note = result.skipped_reason

            yield self._to_document(
                entry,
                body=body,
                body_source=body_source,
                published=published,
                fetch_note=fetch_note,
            )

        log_event(
            logger,
            "rss.collected",
            feed_url=self.feed_url,
            entries=len(parsed.entries),
            articles_fetched=fetched,
            skipped_already_seen=skipped_old,
            skipped_by_cap=capped,
        )
        if capped:
            log_event(
                logger,
                "rss.article_fetch_cap_reached",
                feed_url=self.feed_url,
                cap=self.max_article_fetches,
                entries_left_thin=capped,
            )

    def fetch_state(self) -> FetchState:
        return self._fetch_state

    def _to_document(
        self,
        entry: Any,
        *,
        body: str,
        body_source: str,
        published: datetime | None,
        fetch_note: str | None,
    ) -> CollectedDocument:
        title = scrub_contact_details(_clean(entry.get("title", ""))) or None
        link = entry.get("link")

        payload: dict[str, Any] = {
            field: _raw_get(entry, field)
            for field in PROVENANCE_FIELDS
            if _raw_get(entry, field) is not None
        }
        # Summary and title travel through the same §21 scrubber as the body;
        # the raw values must not be preserved next to the redacted ones or the
        # redaction would be pointless.
        if "summary" in payload:
            payload["summary"] = scrub_contact_details(_clean(str(payload["summary"])))
        if "title" in payload:
            payload["title"] = title
        payload["tags"] = [t.get("term") for t in entry.get("tags", []) if t.get("term")]
        payload["feed_url"] = self.feed_url
        payload["body"] = body
        # Provenance for the body itself: which of the two paths produced it, and
        # if the page was tried and refused, why. Without this a short document
        # is indistinguishable from a robots-blocked one.
        payload["body_source"] = body_source
        if fetch_note:
            payload["body_fetch_note"] = fetch_note

        return CollectedDocument(
            external_id=_external_id(entry, self.feed_url),
            payload=payload,
            title=title,
            body=body or None,
            url=link,
            published_at=published,
            language_raw=self.language,
            region_raw=self.region,
        )


def _raw_get(entry: Any, key: str) -> Any:
    """Read a field only if the feed actually provided it.

    feedparser's FeedParserDict aliases `published` and `updated` onto each other
    when one is missing. For provenance that alias is not a convenience but a
    falsehood — it would record a timestamp the publisher never sent, under a
    field name implying they did. Bypassing the alias keeps the stored payload a
    record of what arrived.
    """
    if isinstance(entry, dict) and key not in dict.keys(entry):
        return None
    return dict.get(entry, key) if isinstance(entry, dict) else entry.get(key)


def _clean(value: str) -> str:
    return " ".join(value.split())


def _entry_body(entry: Any) -> str:
    """The longest text the feed itself offers, scrubbed (§21).

    Longest rather than "content if present": some feeds ship a `content` field
    holding a one-line teaser alongside a longer `summary`, and taking the
    nominally-richer field would discard the better text.
    """
    candidates: list[str] = []

    for block in entry.get("content", []) or []:
        value = block.get("value")
        if value:
            candidates.append(value)

    for key in ("summary", "description"):
        value = entry.get(key)
        if value:
            candidates.append(str(value))

    if not candidates:
        return ""

    best = max(candidates, key=len)
    # HTML is stripped here rather than left for normalize.py's clean_text so the
    # length comparison against min_body_chars measures words, not markup: a
    # 700-character wrapper around a 40-character teaser is not an article.
    return scrub_contact_details(_strip_html(best)) or ""


def _strip_html(value: str) -> str:
    import re

    return _clean(re.sub(r"<[^>]+>", " ", value))


def _entry_datetime(entry: Any) -> datetime | None:
    """Publication time, preferring `published` and falling back to `updated`.

    Read through `dict.keys` rather than `entry.get`, because feedparser's
    FeedParserDict aliases a missing `published_parsed` onto `updated_parsed`
    and warns that the alias "will be removed in a future version". Depending on
    it would fail silently and expensively: every published_at would become None,
    every signal would land on the wrong date, and nothing would raise.
    """
    stored = set(dict.keys(entry)) if isinstance(entry, dict) else set()

    for key in ("published_parsed", "updated_parsed"):
        if key not in stored:
            continue
        parsed = dict.get(entry, key)
        if parsed:
            # feedparser normalises to UTC and returns a 9-tuple.
            return datetime(*parsed[:6], tzinfo=timezone.utc)
    return None


def _external_id(entry: Any, feed_url: str) -> str:
    """A stable natural key for one feed entry.

    Prefers the feed's own guid, then the link. Falls back to hashing the title
    so an entry with neither is still idempotent rather than being re-inserted
    under a new key on every run.

    `raw_documents.external_id` is varchar(255) with a unique index on
    (source_id, external_id), so anything longer is replaced by its digest
    instead of being truncated — two long URLs sharing a 255-character prefix
    would otherwise collapse into one document.
    """
    candidate = entry.get("id") or entry.get("link")
    if not candidate:
        basis = f"{feed_url}|{entry.get('title', '')}|{entry.get('published', '')}"
        return "sha256:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()

    candidate = str(candidate)
    if len(candidate) <= 255:
        return candidate
    return "sha256:" + hashlib.sha256(candidate.encode("utf-8")).hexdigest()
