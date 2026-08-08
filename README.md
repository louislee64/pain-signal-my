# Malaysia SME Pain Radar (`my-pain-radar`)

Problem intelligence, opportunity discovery, and commercial-validation platform for Malaysian SME operational friction.

See [`PROJECT_SPEC.md`](./PROJECT_SPEC.md) for the full product specification, [`AGENTS.md`](./AGENTS.md) / [`CLAUDE.md`](./CLAUDE.md) for coding-agent rules, [`docs/architecture.md`](./docs/architecture.md) for system architecture, and [`docs/data-model.md`](./docs/data-model.md) for the database schema.

**Current status:** Milestone 3 — Trends. Adds Google Trends keyword monitoring: a config-driven keyword registry, pluggable trend providers, derived rolling/growth/z-score metrics, a trends API and a `/trends` dashboard page. No LLM extraction or opportunity scoring yet.

## Stack

| Layer | Technology |
|---|---|
| API | Laravel 13 (PHP 8.4) |
| Dashboard | Nuxt 3 (Vue) |
| Data / Analytics | Python 3.11 |
| Database | PostgreSQL 16 |
| Queue / Cache | Redis 7 |
| Orchestration | Docker Compose |

## Repository layout

```text
apps/
  api/            Laravel application
  web/            Nuxt dashboard
  intelligence/   Python data/analytics package
packages/         Shared taxonomy, schemas, config (cross-app)
config/           YAML configuration: sources.yaml, topics.yaml, keywords.yaml, signal_rules.yaml
docs/             Architecture, business model, data model, policy docs
infrastructure/   Dockerfiles, nginx, scripts
tests/            Fixtures and integration tests
```

## Prerequisites

- Docker and Docker Compose v2 (`docker compose version`)

No local PHP, Node, or Python toolchain is required — everything runs in containers.

## Getting started

```bash
cp .env.example .env
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env
cp apps/intelligence/.env.example apps/intelligence/.env

docker compose up --build
```

Then verify each service is healthy:

```bash
curl http://localhost:8000/api/v1/health   # Laravel API
curl http://localhost:3000/api/health      # Nuxt dashboard
docker compose ps                          # all services should report "healthy"
```

| Service | Default URL |
|---|---|
| API | http://localhost:8000 |
| Dashboard | http://localhost:3000 |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |

If those ports are already taken by other projects on your machine, override `POSTGRES_PORT` / `REDIS_PORT` / `API_PORT` / `WEB_PORT` in your local `.env` (gitignored) — the containers' internal ports and inter-service URLs stay the same either way.

The `intelligence` service has no HTTP port; it runs as a background worker. Check its health with:

```bash
docker compose exec intelligence python -m intelligence.cli health
```

## Data ingestion

Sync the source registry (`config/sources.yaml`) into the database, then run a collector:

```bash
docker compose exec api php artisan sources:sync
docker compose exec intelligence python -m intelligence.cli ingest data_gov_my_fuelprice
```

Re-running `ingest` is safe — unchanged rows are skipped, changed rows are updated in place,
nothing is duplicated. See [`docs/data-model.md`](./docs/data-model.md) and
[`docs/adding-a-data-source.md`](./docs/adding-a-data-source.md) for the schema and how to
configure another dataset.

## Analytics pipeline

Sync the taxonomy, then normalize → classify → aggregate:

```bash
docker compose exec api php artisan topics:sync
docker compose exec intelligence python -m intelligence.cli normalize
docker compose exec intelligence python -m intelligence.cli classify
docker compose exec intelligence python -m intelligence.cli aggregate
```

Every stage is idempotent and re-runnable; `normalize`/`classify` accept `--source <slug>` to
scope a run to one source. Classification is rule-based keyword matching against
`config/topics.yaml` (no LLM calls yet — that's Milestone 4). See
[`docs/data-model.md`](./docs/data-model.md) for what each stage writes and why.

## Search trends

Sync the keyword clusters, then collect and compute:

```bash
docker compose exec api php artisan keywords:sync

# Which providers can actually run right now, and why not if they can't:
docker compose exec intelligence python -m intelligence.cli trends check google_trends_csv

# Collect from an official trends.google.com CSV export (no credentials needed):
docker compose exec intelligence python -m intelligence.cli \
  trends collect google_trends_csv --path /app/tests/fixtures/google_trends_interest_over_time.csv
docker compose exec intelligence python -m intelligence.cli trends compute
```

Then open the dashboard at `/trends`, or query the API:

```bash
curl http://localhost:8000/api/v1/trends
curl "http://localhost:8000/api/v1/trends/invoice%20software"
```

**Trends values are relative interest (0-100), never absolute search volume** and are only
comparable within one `collection_batch` — see
[`docs/trends-data-sources.md`](./docs/trends-data-sources.md), which also covers the
BigQuery discovery provider and what to do when official Trends API access is granted.

## Running tests

```bash
# Laravel
docker compose exec api php artisan test

# Nuxt (once test suite exists)
docker compose exec web npm test

# Python
docker compose exec intelligence pytest
```

## Development notes

- `apps/*/.env.example` documents required environment variables per service; `.env` files are gitignored.
- Application source directories are bind-mounted into containers for hot-reload during development; `vendor/` and `node_modules/` are kept in named Docker volumes so host and container dependency installs never collide.
- No LLM extraction or opportunity scoring exists yet — see `PROJECT_SPEC.md` §55 for the full milestone roadmap.
