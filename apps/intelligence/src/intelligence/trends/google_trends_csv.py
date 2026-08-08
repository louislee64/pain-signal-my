"""Google Trends CSV export provider (PROJECT_SPEC.md §15B monitoring).

Reads the "Interest over time" CSV that trends.google.com offers as a download
button. This is an official, sanctioned export — it is NOT scraping, which §69
explicitly rules out as a core implementation, and it needs no credentials at
all. That makes it the only Trends path that works today: the official API is
still an application-gated alpha, and BigQuery needs a billed GCP project.

The trade-off, stated plainly: this path is manual. Someone has to download the
file. It is the right Milestone 3 default precisely because it lets the whole
downstream pipeline (storage, rolling windows, growth, z-scores, charts) be
built and verified against real Google data now, instead of blocking on access
that may never be granted. See docs/trends-data-sources.md.

Export format handled (as produced by trends.google.com):

    Category: All categories

    Week,invoice software: (Malaysia),stock count: (Malaysia)
    2026-06-01,45,12
    2026-06-08,52,<1
"""

import csv
import re
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path

from intelligence.trends.base import TrendObservation, TrendProvider, TrendProviderError

# Google Trends labels the first column by granularity.
DATE_COLUMN_NAMES = {"day", "week", "month", "date", "time"}

# Column headers look like "invoice software: (Malaysia)".
KEYWORD_HEADER_PATTERN = re.compile(r"^(?P<keyword>.+?):\s*\((?P<geo>[^)]*)\)\s*$")

DATE_FORMATS = ("%Y-%m-%d", "%Y-%m")


def parse_trends_csv(text: str, geo: str = "MY") -> list[TrendObservation]:
    """Parse an "Interest over time" export into observations.

    Kept as a pure string -> list function so the format handling can be tested
    against fixtures without touching the filesystem.
    """

    rows = list(csv.reader(_significant_lines(text)))
    if not rows:
        raise TrendProviderError("Trends CSV contained no usable rows")

    header, *data_rows = rows
    if not header or header[0].strip().lower() not in DATE_COLUMN_NAMES:
        raise TrendProviderError(
            f"Unexpected Trends CSV header {header!r}: first column should be one of "
            f"{sorted(DATE_COLUMN_NAMES)}. Export 'Interest over time' from trends.google.com."
        )

    keywords = [_parse_keyword_header(h) for h in header[1:]]
    if not keywords:
        raise TrendProviderError("Trends CSV header declared no keyword columns")

    observations: list[TrendObservation] = []
    for row in data_rows:
        if not row or not row[0].strip():
            continue

        observed_on = _parse_date(row[0].strip())

        for index, keyword in enumerate(keywords, start=1):
            if index >= len(row):
                continue

            interest = _parse_interest(row[index])
            if interest is None:
                continue

            observations.append(
                TrendObservation(
                    keyword=keyword,
                    observed_on=observed_on,
                    interest=interest,
                    geo=geo,
                )
            )

    return observations


def _significant_lines(text: str) -> Iterable[str]:
    """Drop the leading "Category: ..." preamble and blank separator lines that
    Google puts above the real header row."""

    started = False
    for line in text.splitlines():
        stripped = line.strip()
        if not started:
            if not stripped or stripped.lower().startswith("category:"):
                continue
            started = True
        yield line


def _parse_keyword_header(header: str) -> str:
    match = KEYWORD_HEADER_PATTERN.match(header.strip())
    if match:
        return match.group("keyword").strip()
    # Some exports (and hand-trimmed files) carry a bare keyword with no
    # "(Geo)" suffix. Accept it rather than rejecting an otherwise valid file.
    return header.strip()


def _parse_date(value: str) -> date:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise TrendProviderError(f"Unrecognised date {value!r} in Trends CSV")


def _parse_interest(value: str) -> int | None:
    cleaned = value.strip()
    if not cleaned:
        return None
    # "<1" is Google's own token for "below 1% of peak interest", not a missing
    # value — it is a real, meaningfully-low reading, so it floors to 0 rather
    # than being dropped.
    if cleaned.startswith("<"):
        return 0
    try:
        return int(float(cleaned))
    except ValueError:
        raise TrendProviderError(f"Unrecognised interest value {value!r} in Trends CSV") from None


class GoogleTrendsCsvProvider(TrendProvider):
    name = "google_trends_csv"

    def __init__(self, config=None):
        super().__init__(config)
        self.path = self.config.get("path")
        self.geo = self.config.get("geo", "MY")

    def check_available(self) -> None:
        if not self.path:
            raise TrendProviderError(
                "google_trends_csv requires a 'path' to an Interest-over-time CSV export. "
                "Download one from trends.google.com (Explore -> set Malaysia + your terms -> "
                "the download icon on the 'Interest over time' panel). "
                "See docs/trends-data-sources.md."
            )
        if not Path(self.path).is_file():
            raise TrendProviderError(f"Trends CSV not found at {self.path}")

    def collect_observations(self, keywords: list[str]) -> Iterable[TrendObservation]:
        self.check_available()
        text = Path(self.path).read_text(encoding="utf-8-sig")
        observations = parse_trends_csv(text, geo=self.geo)

        if keywords:
            # The caller asked for a specific keyword set (the enabled rows in
            # the `keywords` table). Anything else in the file is ignored here
            # rather than silently creating keywords nobody registered.
            wanted = {k.casefold() for k in keywords}
            observations = [o for o in observations if o.keyword.casefold() in wanted]

        return observations
