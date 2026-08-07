# Architecture

Status: Milestone 0 (Foundation). This document reflects what exists today, not the full target architecture described in `PROJECT_SPEC.md` §8.

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
- **intelligence** (`apps/intelligence`) — Python 3.11 package. No HTTP server; runs as a long-lived worker process. `python -m intelligence.cli health` checks Postgres + Redis connectivity and is used as the Docker healthcheck. Collectors, normalization, classification, and scoring land here in later milestones (`PROJECT_SPEC.md` §55).
- **postgres** / **redis** — shared infrastructure, each with a native healthcheck (`pg_isready`, `redis-cli ping`).

## Why this shape

- Three independently deployable apps sharing two datastores, per `PROJECT_SPEC.md` §8/§9 — no message broker or orchestrator introduced yet (`PROJECT_SPEC.md` §54 explicitly excludes Kafka/Kubernetes for V1).
- `intelligence` ships with only `pydantic`, `sqlalchemy`, `psycopg`, `httpx`, `redis`, `python-dotenv` — the heavier analytics libraries named in `PROJECT_SPEC.md` §9 (`pandas`, `polars`, `pyarrow`, `scikit-learn`, `numpy`) are deferred until Milestone 2/3 actually need them, so the Milestone 0 image stays fast to build and there are no unused dependencies to maintain.
- `docker-compose.yml` bind-mounts each app's source for hot-reload, but keeps `vendor/` (Laravel) and `node_modules/` (Nuxt) in named volumes — Docker seeds each named volume from the image's own build the first time it's created, so the container always runs the dependency tree it was built with (PHP 8.4 Alpine, `node:20-slim`) regardless of what a host-side install produced.
- `depends_on` uses `condition: service_healthy` so `api` and `intelligence` don't start against a Postgres/Redis that isn't accepting connections yet.

## Not yet implemented

Everything under `PROJECT_SPEC.md` §20 (core schema), §22 (processing pipeline), §26-29 (scoring), and onward. See `PROJECT_SPEC.md` §55 for the milestone sequence.
