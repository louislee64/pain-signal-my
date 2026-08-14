# Adding a data source

PROJECT_SPEC.md §13/§67 requires that adding a new official dataset not require changing
collector code. Two cases:

## 1. Another data.gov.my / OpenDOSM dataset

This is a pure config change. Add an entry to `config/sources.yaml` reusing the existing
`data_gov_my_dataset` collector:

```yaml
sources:
  - slug: data_gov_my_pricecatcher   # unique, becomes the CLI argument
    name: "PriceCatcher: Transactional Records"
    source_type: official_dataset
    base_url: "https://api.data.gov.my/data-catalogue"
    collector: data_gov_my_dataset    # same collector class, different config
    config:
      dataset_id: pricecatcher        # the `id=` query param at api.data.gov.my
      date_column: date               # column used for date_start incremental filtering
    collection_method: http_api
    rate_limit: "4/minute"            # documented at developer.data.gov.my/rate-limit
    reliability_score: 95
    license: "Terms of Use for Government Open Data Malaysia 1.0"
    terms_status: reviewed
    personal_data_risk: none
    enabled: true
```

Then:

```bash
docker compose exec api php artisan sources:sync
docker compose exec intelligence python -m intelligence.cli ingest data_gov_my_pricecatcher
```

No Python code changes. The generic collector
(`apps/intelligence/src/intelligence/collectors/data_gov_my.py`) builds the request from
`dataset_id`/`date_column` alone and stores each row's `series_type` (when present) alongside
the date in `external_id`, so datasets shaped like `fuelprice` (multiple series per date) and
plain one-row-per-date datasets both work unchanged.

Before enabling a new dataset, check its actual row count and shape first (`curl
"https://api.data.gov.my/data-catalogue?id=<id>&limit=3&meta=true"`) — a dataset with
millions of rows (PriceCatcher itself, at >1M rows/month) will need pagination/chunking this
collector does not yet implement; see the note in `data_gov_my.py`.

## 2. Another RSS/Atom feed

Also a pure config change, reusing the `rss_feed` collector:

```yaml
sources:
  - slug: some_publisher_business
    name: "Some Publisher — Business"
    source_type: news_feed          # `sources:ingest --type=news_feed` picks this up
    base_url: "https://example.com"
    collector: rss_feed
    config:
      feed_url: "https://example.com/business/feed/"
      fetch_articles: false         # true ONLY if the feed carries no body
      requests_per_minute: 20       # must equal the `rate_limit` below
      language: en                  # ms / zh for non-English feeds
      region: MY                    # null if the content is not Malaysian
    collection_method: rss
    rate_limit: "20/minute"
    reliability_score: 65
    license: "All rights reserved by publisher; headline/summary use only"
    terms_url: "https://example.com/terms"
    terms_status: unreviewed        # see below before writing `reviewed`
    personal_data_risk: low
    enabled: true
```

Before enabling, check three things — all of which have caught a real feed:

1. **Does it have items?** A 200 response is not a working feed
   (`sinarharian.com.my/rssFeed/220/Bisnes` returns valid XML with zero entries).
2. **Does it carry article bodies?** Compare `content:encoded` length against the
   ~600-character threshold. Set `fetch_articles: true` only when it does not —
   asking a publisher for a page they already sent is rude and slow.
3. **Is the content actually Malaysian?** `vulcanpost_my` is disabled because 9 of
   10 entries were Singaporean; `region: MY` would have been a false claim (§41).

`terms_status` should stay `unreviewed` unless a human has actually read that
publisher's Terms of Use. robots.txt permission is not the same thing — see the
`businesstoday_my` 403 case in [text-sources.md](text-sources.md).

There is a test (`tests/collectors/test_rss.py::TestRegistryConsistency`) asserting
that `rate_limit` and `config.requests_per_minute` agree, and that article
fetching stays confined to the feeds that need it.

## 3. A genuinely new source type (not data.gov.my, not a feed)

Only then write a new collector:

1. Add a class in `apps/intelligence/src/intelligence/collectors/` implementing
   `Collector.collect(self, since, fetch_state=None) -> Iterable[CollectedDocument]`
   (see `base.py`). Override `fetch_state()` too if the source exposes an ETag or
   `Last-Modified`, which is how a collector opts into §38's conditional fetching.
2. Register it in `collectors/registry.py`'s `COLLECTOR_REGISTRY` under a new name.
3. Add a `config/sources.yaml` entry with `collector: <that name>`.

The rest of the pipeline (`ingest.py`'s idempotent upsert, `ingestion_runs` bookkeeping,
`sources:sync`, and the `sources:ingest` schedule) needs no changes — it only depends on
the `Collector` interface.

If the new source involves fetching web pages, reuse
`collectors/fetching.py` rather than writing requests directly. It holds the
robots.txt cache, the per-host rate limiter that honours `Crawl-delay`, and §21's
contact-detail scrubber — the obligations §17 imposes, in one place, so a
collector cannot skip them by accident.
