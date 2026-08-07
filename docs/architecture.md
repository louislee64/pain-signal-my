# Architecture

Status: Milestone 1 (Data Foundation). This document reflects what exists today, not the full target architecture described in `PROJECT_SPEC.md` §8.

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
- **intelligence** (`apps/intelligence`) — Python 3.11 package. No HTTP server; runs as a long-lived worker process. `python -m intelligence.cli health` checks Postgres + Redis connectivity and is used as the Docker healthcheck. `python -m intelligence.cli ingest <source_slug>` runs one collector (see below). Normalization, classification, and scoring land here in later milestones (`PROJECT_SPEC.md` §55).
- **postgres** / **redis** — shared infrastructure, each with a native healthcheck (`pg_isready`, `redis-cli ping`).
- **config/** (repo root) — mounted read-only into `api` and `intelligence` at `/config`. `config/sources.yaml` is the source registry (`PROJECT_SPEC.md` §12); `php artisan sources:sync` upserts it into the `sources` table. See `docs/data-model.md` and `docs/adding-a-data-source.md`.

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

## Why this shape

- Three independently deployable apps sharing two datastores, per `PROJECT_SPEC.md` §8/§9 — no message broker or orchestrator introduced yet (`PROJECT_SPEC.md` §54 explicitly excludes Kafka/Kubernetes for V1).
- `intelligence` ships with only `pydantic`, `sqlalchemy`, `psycopg`, `httpx`, `redis`, `python-dotenv` — the heavier analytics libraries named in `PROJECT_SPEC.md` §9 (`pandas`, `polars`, `pyarrow`, `scikit-learn`, `numpy`) are deferred until Milestone 2/3 actually need them, so the Milestone 0 image stays fast to build and there are no unused dependencies to maintain.
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

Everything under `PROJECT_SPEC.md` §20 not yet listed above (`normalized_documents`, `topics`,
`document_topics`, `problem_signals`, `topic_daily_metrics`, `opportunities`, and the commercial
CRM tables in §21), §22 (processing pipeline), §26-29 (scoring), and onward. See
`PROJECT_SPEC.md` §55 for the milestone sequence.
