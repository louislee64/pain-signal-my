# Malaysia SME Pain Radar (`my-pain-radar`)

Problem intelligence, opportunity discovery, and commercial-validation platform for Malaysian SME operational friction.

See [`PROJECT_SPEC.md`](./PROJECT_SPEC.md) for the full product specification, [`AGENTS.md`](./AGENTS.md) / [`CLAUDE.md`](./CLAUDE.md) for coding-agent rules, [`docs/architecture.md`](./docs/architecture.md) for system architecture, and [`docs/data-model.md`](./docs/data-model.md) for the database schema.

**Current status:** Milestone 1 — Data Foundation. The source registry and first data.gov.my/OpenDOSM collector are live; no normalization, classification, or scoring yet.

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
config/           YAML configuration: topics, keywords, scoring weights, sources
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
- No normalization, classification, or scoring exists yet — see `PROJECT_SPEC.md` §55 for the full milestone roadmap.
