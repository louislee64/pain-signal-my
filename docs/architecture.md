# Architecture

Status: Milestone 2 (Analytics Foundation). This document reflects what exists today, not the full target architecture described in `PROJECT_SPEC.md` §8.

## Services

```text
┌────────────┐   ┌────────────┐   ┌────────────────┐
│  Laravel   │   │    Nuxt    │   │  Python worker  │
│    api     │   │    web     │   │  intelligence   │
│  :8000     │   │  :3000     │   │  (no HTTP port) │
└─────┬──────┘   └─────┬──────┘   └────────┬────────┘
      │                │                   │
      └───────┬────────┴─────────┬─────────┘
              ▼                  ▼
        ┌───────────┐      ┌───────────┐
        │ PostgreSQL│      │   Redis   │
        │  :5432    │      │  :6379    │
        └───────────┘      └───────────┘
```

- **api** (`apps/api`) — Laravel 13. Owns the PostgreSQL schema and exposes `/api/v1/*`. `GET /api/v1/health` reports app + database connectivity.
- **web** (`apps/web`) — Nuxt 3. Talks to `api` over HTTP (`NUXT_PUBLIC_API_BASE_URL`). `GET /api/health` (a Nitro server route) reports the dashboard process itself.
- **intelligence** (`apps/intelligence`) — Python 3.11 package. No HTTP server; runs as a long-lived worker process. `python -m intelligence.cli health` checks Postgres + Redis connectivity and is used as the Docker healthcheck. `ingest` / `normalize` / `classify` / `aggregate` subcommands run the pipeline stages below. Scoring (pain/commercial/opportunity) lands in Milestone 4 (`PROJECT_SPEC.md` §55).
- **postgres** / **redis** — shared infrastructure, each with a native healthcheck (`pg_isready`, `redis-cli ping`).
- **config/** (repo root) — mounted read-only into `api` and `intelligence` at `/config`. `config/sources.yaml` (source registry, §12) and `config/topics.yaml` (taxonomy, §4) sync into the DB via `php artisan sources:sync` / `topics:sync`. `config/signal_rules.yaml` (rule-based severity/urgency/economic-impact keyword weights) is read directly by Python — it has no DB-synced counterpart. See `docs/data-model.md` and `docs/adding-a-data-source.md`.

## Data ingestion (Milestone 1)

```text
config/sources.yaml --sources:sync--> sources table (Laravel-owned schema)
                                            │
                                            ▼
                          intelligence.cli ingest <slug>
                                            │
                     collectors.registry resolves `collector` name
                                            │
                          Collector.collect(since=last_synced_at)
                                            │
                         raw_documents upsert (insert / update / unchanged
                         by content_hash, keyed on source_id+external_id)
                                            │
                          ingestion_runs row records the outcome
```

Laravel owns the `sources` / `ingestion_runs` / `raw_documents` schema via migrations; Python
maps to the same tables with SQLAlchemy Core (`apps/intelligence/src/intelligence/db.py`) but
never runs DDL. The only collector so far (`collectors/data_gov_my.py`) is generic across any
dataset on the data.gov.my/OpenDOSM Open API — adding another one is a `config/sources.yaml`
edit, not a code change.

## Analytics pipeline (Milestone 2)

```text
raw_documents ──normalize── cleanup, language detect, near-dup hash ──> normalized_documents
                                                                              │
                                                          classify (rule-based keyword match
                                                           against config/topics.yaml)
                                                                              │
                                              ┌───────────────────────────────┴──────────────┐
                                              ▼                                               ▼
                                     document_topics                          problem_signals (rule-based
                                    (topic + confidence)                   severity/urgency/economic_impact
                                                                          via config/signal_rules.yaml)
                                                                                              │
                                                                                        aggregate (daily rollup)
                                                                                              ▼
                                                                                     topic_daily_metrics
```

`intelligence.cli normalize` / `classify` / `aggregate` run these stages; each is idempotent
and safe to re-run (`normalize`/`classify` accept `--source <slug>` to scope a run, which
tests use to stay deterministic against a shared dev database that also holds unrelated real
data). Every step here is deterministic rule-based logic — no LLM calls exist yet
(`PROJECT_SPEC.md` §23/§24; that's Milestone 4). See `docs/data-model.md` for exactly what
each table stores and why, including where this implementation adds columns beyond
`PROJECT_SPEC.md` §20's literal field lists.

## Why this shape

- Three independently deployable apps sharing two datastores, per `PROJECT_SPEC.md` §8/§9 — no message broker or orchestrator introduced yet (`PROJECT_SPEC.md` §54 explicitly excludes Kafka/Kubernetes for V1).
- `intelligence`'s dependencies are still just `pydantic`, `sqlalchemy`, `psycopg`, `httpx`, `redis`, `python-dotenv`, `python-ulid`, `pyyaml` — the heavier analytics libraries named in `PROJECT_SPEC.md` §9 (`pandas`, `polars`, `pyarrow`, `scikit-learn`, `numpy`) still haven't been needed even through normalization/classification/aggregation (plain regex, dict-based rules, and SQL `GROUP BY` cover it); add them when a milestone's workload actually calls for a dataframe or a model, not preemptively.
- `docker-compose.yml` bind-mounts each app's source for hot-reload, but keeps `vendor/` (Laravel) and `node_modules/` (Nuxt) in named volumes — Docker seeds each named volume from the image's own build the first time it's created, so the container always runs the dependency tree it was built with (PHP 8.4 Alpine, `node:20-slim`) regardless of what a host-side install produced.
- `depends_on` uses `condition: service_healthy` so `api` and `intelligence` don't start against a Postgres/Redis that isn't accepting connections yet.

## Pitfall: don't add `env_file:` to the `api` service

`apps/api/docker-compose` config deliberately has no `env_file:` for `api` (only `web` and
`intelligence` have one). Laravel already reads its bind-mounted `.env` itself via dotenv —
`env_file:` would additionally inject the same values as real container OS environment
variables. That matters because `phpunit.xml`'s `<env>` block (which points tests at an
in-memory sqlite database) only overrides a variable that *isn't already set* in the OS
environment — real container env vars win even with `force="true"` set on every entry (this
was tested empirically, not just per PHPUnit's docs). With `env_file:` present, every test run
silently used the real Postgres connection, and `RefreshDatabase` truncated/rebuilt the schema
against it — this is how a real ingested dataset gets wiped by running `php artisan test`. If
`api` ever needs a real container-level env var again, add it under `environment:` for that
one key (as done for `SOURCES_REGISTRY_PATH`), not via `env_file:`.

## Not yet implemented

`trend_metrics` / `official_metrics` (Milestone 3, needs Google Trends), the scoring formulas
in §26-29 and the `opportunities` table that depends on them (Milestone 4), and the commercial
CRM tables in §21 (Milestone 6) onward. See `PROJECT_SPEC.md` §55 for the milestone sequence.
