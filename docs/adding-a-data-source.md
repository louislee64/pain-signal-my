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

## 2. A genuinely new source type (not data.gov.my)

Only then write a new collector:

1. Add a class in `apps/intelligence/src/intelligence/collectors/` implementing
   `Collector.collect(self, since) -> Iterable[CollectedDocument]` (see `base.py`).
2. Register it in `collectors/registry.py`'s `COLLECTOR_REGISTRY` under a new name.
3. Add a `config/sources.yaml` entry with `collector: <that name>`.

The rest of the pipeline (`ingest.py`'s idempotent upsert, `ingestion_runs` bookkeeping,
`sources:sync`) needs no changes — it only depends on the `Collector` interface.
