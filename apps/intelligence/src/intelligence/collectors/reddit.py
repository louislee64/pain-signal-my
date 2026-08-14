"""Reddit subreddit collector (PROJECT_SPEC.md §17 "public forum discussions").

The first source in the project where business owners describe their own problems
in their own words, rather than a journalist describing the economy. That is the
whole point: §4's taxonomy is written in the language of operational friction
("stock discrepancy", "kena reconcile manual entry"), and news prose does not
speak it.

## Why the official API and not the website

§13 ranks "Official API" first. Reddit has one, and the alternative is ruled out
twice over:

  * `https://www.reddit.com/robots.txt` is `User-agent: * / Disallow: /` — a
    blanket refusal to be crawled.
  * The legacy unauthenticated `.json` endpoints now return 403.

So this collector talks to `oauth.reddit.com` with credentials and **never
fetches a reddit.com page**. That is not a way around robots.txt; it is the
reason robots.txt does not apply — we are not crawling. Nothing here may be
"fixed" later by adding a page fetch or a browser User-Agent.

## Why it ships disabled

Reddit's Data API terms and Public Content Policy restrict commercial use, and
§6 gives this project commercial intent. That conflict is a licensing decision
for a human, not something a collector can resolve, so every Reddit source is
registered with `terms_status: needs_review` and `enabled: false`. See
docs/text-sources.md.
"""

import time
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any

import httpx

from intelligence.collectors.base import CollectedDocument, Collector, FetchState
from intelligence.collectors.fetching import (
    is_retryable_http_error,
    scrub_contact_details,
)
from intelligence.observability import get_logger, log_event
from intelligence.retry import call_with_retry

logger = get_logger("intelligence.collectors.reddit")

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_BASE_URL = "https://oauth.reddit.com"

# Reddit's free Data API tier allows 100 requests/minute per OAuth client. 60 is
# deliberately under it: the ceiling is shared by every source using the same
# credentials, and three subreddits ingesting in sequence must not be able to
# breach it between them.
DEFAULT_REQUESTS_PER_MINUTE = 60

# Reddit's maximum page size for listings.
PAGE_SIZE = 100

# A run that keeps paginating forever is a bug, not thoroughness. 10 pages is
# 1,000 posts from one subreddit in one run — far more than a day produces.
DEFAULT_MAX_PAGES = 10

# Reddit removes and deletes content, leaving these markers in place of the text.
# They are not usable evidence, and storing them as body text would let a deleted
# post look like a real one with nothing to say.
TOMBSTONES = {"[deleted]", "[removed]"}

# Fields copied into the stored payload for provenance.
#
# `author` is deliberately absent, and this is the most important line in the
# file. A Reddit username is a durable pseudonymous identifier that links every
# post a person has ever made — more identifying than the journalist bylines
# dropped in the RSS collector, not less. §21 says avoid collecting unnecessary
# personal information, and nothing downstream needs to know who posted.
# `author_fullname`, `author_flair_text` and friends are excluded for the same
# reason.
#
# Volatile engagement counters (`score`, `ups`, `num_comments`, `upvote_ratio`)
# are also excluded, for a different reason: they change every hour, so including
# them in the payload would change the content hash and mark every recent post
# "updated" on every nightly run. Nothing consumes them today — §26's
# mention_frequency counts signals, not upvotes — so storing a snapshot that goes
# stale immediately buys churn and no information. If engagement-weighted
# severity is ever wanted, it needs its own mechanism, not a field that quietly
# rewrites raw_documents every night.
PROVENANCE_FIELDS = (
    "id",
    "name",
    "subreddit",
    "permalink",
    "created_utc",
    "link_flair_text",
    "is_self",
    "over_18",
)


class RedditCredentialsMissing(RuntimeError):
    """Raised when the collector cannot authenticate.

    A distinct type so the message can say exactly what to configure. The ingest
    pipeline records it on the run and the /sources health page shows it, which is
    far more useful than a run that succeeds with zero documents.
    """


class RedditSubredditCollector(Collector):
    """Collect recent posts from one subreddit via the official Data API.

    Required `config` key: `subreddit`.

    Credentials come from the environment, never from config — `config` is
    committed to git and these are secrets:
      REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, and optionally REDDIT_USERNAME.

    Optional config:
      requests_per_minute  int  default 60   — stays under Reddit's 100/min
      max_pages            int  default 10   — per-run pagination ceiling
      min_body_chars       int  default 0    — drop posts thinner than this
      language             str  default "en" — normalize.py still detects per doc
      region               str  default "MY"
    """

    def __init__(
        self,
        config: dict[str, Any],
        *,
        client: httpx.Client | None = None,
        credentials: dict[str, str] | None = None,
        sleep=time.sleep,
    ):
        super().__init__(config)
        try:
            self.subreddit = config["subreddit"]
        except KeyError:
            raise ValueError(
                "reddit_subreddit collector requires a 'subreddit' in the source's config block"
            ) from None

        import os

        source = credentials if credentials is not None else os.environ
        self.client_id = source.get("REDDIT_CLIENT_ID") or None
        self.client_secret = source.get("REDDIT_CLIENT_SECRET") or None
        self.username = source.get("REDDIT_USERNAME") or None

        self.requests_per_minute = config.get("requests_per_minute", DEFAULT_REQUESTS_PER_MINUTE)
        self.max_pages = config.get("max_pages", DEFAULT_MAX_PAGES)
        self.min_body_chars = config.get("min_body_chars", 0)
        self.language = config.get("language", "en")
        self.region = config.get("region", "MY")

        self._client = client or httpx.Client(timeout=30.0, follow_redirects=True)
        self._sleep = sleep
        self._token: str | None = None
        self._interval = 60.0 / max(1, self.requests_per_minute)
        self._last_request: float | None = None

    # ------------------------------------------------------------------ availability

    def check_available(self) -> None:
        """Raise with an actionable message if this collector cannot run.

        Called at the top of `collect()` rather than in `__init__` so that merely
        syncing the registry never fails on a source nobody is running.
        """
        if not self.client_id or not self.client_secret:
            raise RedditCredentialsMissing(
                "reddit_subreddit collector needs REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET "
                "in apps/intelligence/.env. Create a 'script' app at "
                "https://www.reddit.com/prefs/apps to get them, and read the commercial-use "
                "note in docs/text-sources.md before enabling the source."
            )

    # ------------------------------------------------------------------ auth

    def user_agent(self) -> str:
        """Reddit requires a descriptive, unique User-Agent and throttles
        generic ones hard. Its documented shape is
        `<platform>:<app id>:<version> (by /u/<username>)`, so REDDIT_USERNAME is
        used when present and a contact URL substituted when it is not.
        """
        suffix = f"by /u/{self.username}" if self.username else (
            "+https://github.com/louislee64/pain-signal-my"
        )
        return f"python:my.painradar.collector:0.1 ({suffix})"

    def _access_token(self) -> str:
        if self._token is not None:
            return self._token

        def post() -> httpx.Response:
            response = self._client.post(
                TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
                headers={"User-Agent": self.user_agent()},
            )
            response.raise_for_status()
            return response

        try:
            response = call_with_retry(post, is_retryable=is_retryable_http_error)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                # Wrong credentials are a configuration problem with a fix, not a
                # transient outage — say so instead of retrying into a wall.
                raise RedditCredentialsMissing(
                    "Reddit rejected REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET "
                    f"(HTTP {exc.response.status_code}). Confirm the app is a 'script' type at "
                    "https://www.reddit.com/prefs/apps and that the secret has not been rotated."
                ) from None
            raise

        token = response.json().get("access_token")
        if not token:
            raise RedditCredentialsMissing(
                "Reddit returned no access_token for the client_credentials grant."
            )

        self._token = token
        return token

    # ------------------------------------------------------------------ rate limiting

    def _throttle(self, response: httpx.Response | None = None) -> None:
        """Wait before the next request.

        Two limits, and the server's wins. Our own interval is a floor derived
        from `requests_per_minute`; `X-Ratelimit-Remaining` is Reddit telling us
        how much of the real budget is left, which is better information than any
        static guess because the budget is shared across sources using the same
        credentials.
        """
        if response is not None:
            remaining = _as_float(response.headers.get("X-Ratelimit-Remaining"))
            reset = _as_float(response.headers.get("X-Ratelimit-Reset"))
            if remaining is not None and remaining < 1 and reset:
                log_event(
                    logger,
                    "reddit.rate_limit_exhausted",
                    subreddit=self.subreddit,
                    sleeping_seconds=reset,
                )
                self._sleep(reset)
                self._last_request = time.monotonic()
                return

        if self._last_request is not None:
            elapsed = time.monotonic() - self._last_request
            if elapsed < self._interval:
                self._sleep(self._interval - elapsed)
        self._last_request = time.monotonic()

    # ------------------------------------------------------------------ collection

    def collect(
        self, since: datetime | None, fetch_state: FetchState | None = None
    ) -> Iterable[CollectedDocument]:
        self.check_available()

        token = self._access_token()
        after: str | None = None
        pages = 0
        yielded = 0
        stopped_early = False

        while pages < self.max_pages:
            self._throttle()

            params: dict[str, Any] = {"limit": PAGE_SIZE, "raw_json": 1}
            if after:
                params["after"] = after

            def get() -> httpx.Response:
                response = self._client.get(
                    f"{API_BASE_URL}/r/{self.subreddit}/new",
                    params=params,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "User-Agent": self.user_agent(),
                    },
                )
                response.raise_for_status()
                return response

            response = call_with_retry(get, is_retryable=is_retryable_http_error)
            self._throttle(response)
            pages += 1

            listing = response.json().get("data") or {}
            children = listing.get("children") or []
            if not children:
                break

            for child in children:
                post = child.get("data") or {}
                created = _created_at(post)

                # `/new` is reverse-chronological, so the first post older than
                # our last successful sync means every remaining post is too.
                # Stopping here is what makes incremental collection cheap rather
                # than re-reading the whole subreddit nightly.
                if since is not None and created is not None and created <= since:
                    stopped_early = True
                    break

                document = self._to_document(post, created)
                if document is None:
                    continue

                yielded += 1
                yield document

            if stopped_early:
                break

            after = listing.get("after")
            if not after:
                break

        log_event(
            logger,
            "reddit.collected",
            subreddit=self.subreddit,
            pages=pages,
            documents=yielded,
            stopped_at_last_sync=stopped_early,
        )
        if pages >= self.max_pages and not stopped_early:
            # No silent caps: without this, a run that hit the ceiling looks
            # identical to one that reached the end of the subreddit.
            log_event(
                logger,
                "reddit.page_cap_reached",
                subreddit=self.subreddit,
                max_pages=self.max_pages,
            )

    def _to_document(self, post: dict[str, Any], created: datetime | None) -> CollectedDocument | None:
        post_id = post.get("id")
        if not post_id:
            return None

        title = _clean(post.get("title") or "")
        selftext = _clean(post.get("selftext") or "")

        if title in TOMBSTONES:
            return None
        if selftext in TOMBSTONES:
            selftext = ""

        body = f"{title}\n\n{selftext}".strip() if selftext else title
        body = scrub_contact_details(body) or ""

        if len(body) < self.min_body_chars:
            return None

        payload: dict[str, Any] = {
            field: post.get(field) for field in PROVENANCE_FIELDS if post.get(field) is not None
        }
        payload["title"] = scrub_contact_details(title)
        payload["body"] = body
        # Which subreddit produced this, spelled out rather than inferred from the
        # source slug, so a document remains self-describing if sources are ever
        # merged or renamed.
        payload["subreddit"] = post.get("subreddit") or self.subreddit
        payload["is_selftext"] = bool(selftext)

        permalink = post.get("permalink")

        return CollectedDocument(
            external_id=f"reddit:{post_id}",
            payload=payload,
            title=scrub_contact_details(title) or None,
            body=body or None,
            url=f"https://www.reddit.com{permalink}" if permalink else None,
            published_at=created,
            language_raw=self.language,
            region_raw=self.region,
        )


def _clean(value: str) -> str:
    return " ".join(value.split())


def _as_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _created_at(post: dict[str, Any]) -> datetime | None:
    created = post.get("created_utc")
    if created is None:
        return None
    try:
        return datetime.fromtimestamp(float(created), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None
