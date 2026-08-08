# Google Trends data sources

PROJECT_SPEC.md §69 sets a strict acquisition order and one prohibition:

> 1. Official Google Trends API when credentials/access are configured.
> 2. Google Trends BigQuery public dataset for available discovery signals.
> 3. Adapter interface allowing future providers.
>
> Do not create brittle scraping as the core implementation.

Here is what each option actually costs to reach, as of this milestone, and what
is implemented.

## 1. Official Google Trends API — preferred, not available

Google launched an official Trends API in July 2025. It is **still an
application-gated alpha**: access requires applying through Google's developer
portal, and the public documentation carries no endpoint list, request shape, or
auth contract to build against.

**No `google_trends_api` provider exists in this repo**, deliberately. Writing an
adapter against an unpublished contract would produce code that looks finished,
passes its own invented tests, and fails the first time it meets the real API —
which is worse than an honest gap.

### When access is granted

1. Add `apps/intelligence/src/intelligence/trends/google_trends_api.py` with a
   `TrendProvider` subclass (see `trends/base.py`).
2. Implement `check_available()` (credential presence) and
   `collect_observations()`; add `discover_terms()` if the API serves top/rising
   queries.
3. Register it in `trends/registry.py`.

Nothing else changes — storage, metric computation, the CLI, the API endpoints
and the dashboard all sit behind the `TrendProvider` interface. Make it the
default in `config/sources.yaml`-style operational docs once proven.

## 2. BigQuery public dataset — implemented, needs a billed GCP project

`google_trends_bigquery` queries `bigquery-public-data.google_trends.international_top_terms`
and `…international_top_rising_terms` for Malaysian top/rising queries. This
serves §15A **discovery**: surfacing terms the system was not already watching.

Shape and limits of that dataset:

- Weekly granularity, rolling 5-year window, rows expire 30 days after `refresh_date`.
- Top 25 and Top 25 Rising per country and sub-region, with `rank` and `score`.
- Country filter is `country_code = 'MY'`.

Setup:

```bash
# 1. Install the optional extra (kept out of the default image on purpose —
#    it is heavy and unusable without credentials).
docker compose exec intelligence pip install -e ".[bigquery]"

# 2. Point at a GCP project with billing enabled and a service-account key
#    holding the "BigQuery Job User" role.
export GOOGLE_CLOUD_PROJECT=your-project-id
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/key.json

# 3. Confirm the provider can run before using it.
docker compose exec intelligence python -m intelligence.cli trends check google_trends_bigquery
```

The dataset is free to read; BigQuery bills for bytes scanned beyond the monthly
free tier. The provider's query filters on `country_code` and a `week` lower
bound specifically to keep scanned bytes (and therefore cost) small.

Discovered terms are written to `keywords` with `source='discovered'`, which
`php artisan keywords:sync` deliberately never touches — they were never in
`config/keywords.yaml`, so their absence from it must not be read as "removed".

## 3. CSV export — implemented, works today with no credentials

`google_trends_csv` reads the "Interest over time" CSV that trends.google.com
offers as a download button. This is an **official, sanctioned export**, not
scraping: no HTML parsing, no rate-limit evasion, no undocumented endpoint.

This is the Milestone 3 default, and the trade-off is stated plainly: **it is
manual**. Someone downloads the file. That is acceptable — and better than the
alternative — because it lets the entire downstream pipeline (storage,
idempotent re-import, rolling windows, growth, z-scores, the API, the chart) be
built and verified against real Google data now, rather than blocking
indefinitely on alpha access that may never arrive.

### Producing an export

1. Open <https://trends.google.com/trends/explore>.
2. Set **Country: Malaysia** and a date range.
3. Enter up to 5 search terms — values are scaled *relative to each other within
   one request*, so keep a comparison set stable if you intend to compare across
   downloads (see the warning below).
4. Click the download icon on the **Interest over time** panel.

```bash
docker compose exec intelligence python -m intelligence.cli \
  trends collect google_trends_csv --path /app/data/samples/multiTimeline.csv

docker compose exec intelligence python -m intelligence.cli trends compute
```

Keywords not present in the `keywords` table are skipped, not auto-created:
monitoring is a curated list (§15B). Add them to `config/keywords.yaml` and run
`php artisan keywords:sync` first.

## The scaling warning that governs all of this

PROJECT_SPEC.md §16: *"Never interpret Trends numbers as absolute search volume."*

Google Trends returns **relative interest, 0-100, scaled to the peak within a
single request**. Two consequences the schema enforces rather than hopes for:

- Every `trend_metrics` row records `collection_batch` (a ULID per collection run)
  and `collection_method`. Values are only comparable within a batch.
- The `/api/v1/trends` responses repeat the caveat in `meta.interest_scale`, so
  anything built on the API carries it forward.

A **missing** series is also not a zero. Low-volume queries — which many of the
Bahasa Malaysia and Chinese terms in `config/keywords.yaml` will be in a market
Malaysia's size — return no data at all. That means "not enough search volume to
measure", not "nobody has this problem".

Per §16, treat Trends as **corroborating** evidence, never as standalone
market-size evidence.
