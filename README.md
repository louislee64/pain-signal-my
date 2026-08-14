# Malaysia SME Pain Radar (`my-pain-radar`)

Problem intelligence, opportunity discovery, and commercial-validation platform for Malaysian SME operational friction.

See [`PROJECT_SPEC.md`](./PROJECT_SPEC.md) for the full product specification, [`AGENTS.md`](./AGENTS.md) / [`CLAUDE.md`](./CLAUDE.md) for coding-agent rules, [`docs/architecture.md`](./docs/architecture.md) for system architecture, [`docs/data-model.md`](./docs/data-model.md) for the database schema, [`docs/scoring-model.md`](./docs/scoring-model.md) for how opportunities are scored, [`docs/llm-providers.md`](./docs/llm-providers.md) for LLM extraction, cost and evaluation, [`docs/dashboard.md`](./docs/dashboard.md) for the dashboard and its API, [`docs/commercial-validation.md`](./docs/commercial-validation.md) for the funnel, the gates and the personal-data posture, [`docs/reporting.md`](./docs/reporting.md) for the weekly report, alerting and the schedule, [`docs/text-sources.md`](./docs/text-sources.md) for the news-feed collector, its robots/terms posture and its measured yield, and [`docs/outcomes-and-calibration.md`](./docs/outcomes-and-calibration.md) for the feedback loop.

**Current status:** Milestone 8 — Real Market Validation. The loop closes: §58's outcome dataset records what happened when an opportunity met a real business, §56's `opportunity_revenue` answers *"did this system actually help create revenue?"*, and §57's calibration report says where the scoring model was wrong — while refusing to conclude from too little data and never editing the weights itself. All eight milestones in `PROJECT_SPEC.md` §55 are implemented.

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

# One source by slug…
docker compose exec intelligence python -m intelligence.cli ingest data_gov_my_fuelprice

# …or everything in the registry, which is what the schedule runs.
docker compose exec api php artisan sources:ingest
docker compose exec api php artisan sources:ingest --type=news_feed
```

Two source types are wired: the data.gov.my fuel-price dataset, and eight Malaysian
news/business RSS feeds (English and Bahasa Malaysia). Article pages are fetched only for
feeds that publish headlines alone, and only within robots.txt and rate limits —
see [`docs/text-sources.md`](./docs/text-sources.md), which also reports the measured
signal yield honestly.

Re-running `ingest` is safe — unchanged rows are skipped, changed rows are updated in place,
nothing is duplicated. See [`docs/data-model.md`](./docs/data-model.md) and
[`docs/adding-a-data-source.md`](./docs/adding-a-data-source.md) for the schema and how to
configure another dataset or feed.

## Analytics pipeline

Sync the taxonomy, then normalize → classify → aggregate:

```bash
docker compose exec api php artisan topics:sync
docker compose exec intelligence python -m intelligence.cli normalize
docker compose exec intelligence python -m intelligence.cli classify
docker compose exec intelligence python -m intelligence.cli aggregate
```

Every stage is idempotent and re-runnable; `normalize`/`classify` accept `--source <slug>` to
scope a run to one source. `classify` is rule-based keyword matching against
`config/topics.yaml` — free, deterministic, and unaffected by whether LLM extraction is
enabled. See [`docs/data-model.md`](./docs/data-model.md) for what each stage writes and why.

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

## Opportunity scoring

```bash
docker compose exec intelligence python -m intelligence.cli score
```

Ranks every topic on pain, commercial attractiveness, blended opportunity and confidence.
Confidence is a *separate* score, not folded into opportunity: "looks attractive, evidence
is still thin" is more useful than one number pretending to certainty.

Every weight lives in [`config/scoring.yaml`](./config/scoring.yaml) and every score stores
its own arithmetic — each dimension's raw input, normalized value, weight and contribution.
See [`docs/scoring-model.md`](./docs/scoring-model.md).

## Dashboard

Open <http://localhost:3000>. The overview answers §33's question — *what should I
investigate or sell this week?* — with §33's five cards and a ranked table where every
row links to the stored breakdown behind its score.

```bash
curl http://localhost:8000/api/v1/dashboard
curl http://localhost:8000/api/v1/opportunities
curl http://localhost:8000/api/v1/opportunities/1   # §34 sections + score_components
curl http://localhost:8000/api/v1/topics
curl http://localhost:8000/api/v1/sources           # health, with reasons
```

The dashboard needs data to be worth opening, and the one real source wired up so far
(fuel prices) matches no topic keywords by design. Seed a demo set:

```bash
docker compose exec api php artisan db:seed --class=DemoDataSeeder
docker compose exec intelligence python -m intelligence.cli aggregate
docker compose exec intelligence python -m intelligence.cli score

docker compose exec api php artisan demo:purge    # removes exactly what it created
```

Everything it creates is prefixed `demo_` and marked fabricated. It writes signals and
never `opportunities` rows, so what the dashboard shows is the real engine's output —
a hand-written score would make a broken scorer look fine. See
[`docs/dashboard.md`](./docs/dashboard.md).

## LLM extraction (optional, costs money)

Off by default. `config/llm.yaml` is the only thing that turns it on.

```bash
# What would a run do, and to how many documents? Calls nothing.
docker compose exec intelligence python -m intelligence.cli llm extract --dry-run

# Spend against the configured daily/monthly ceilings
docker compose exec intelligence python -m intelligence.cli llm usage

# The §70 evaluation cases, replayed from recordings — free and deterministic
docker compose exec intelligence python -m intelligence.cli llm evaluate --provider fixture
```

The LLM does bounded extraction only — read one document, report the problem it describes.
It is never asked whether something is a good business opportunity; that judgement belongs to
the scoring engine, where it is explainable and testable. Budget ceilings are checked *before*
each call, and every call is recorded in `ai_usage` whether it succeeded or not.

See [`docs/llm-providers.md`](./docs/llm-providers.md) for providers, costs, guards and the
evaluation suite.

## Commercial validation

§3's funnel, gated by §7. An opportunity moves `observed → investigating →
buyer_identified → problem_validated → commercially_validated → paid_pilot →
repeatable_solution`, and each advance is refused until the evidence behind it
exists.

```bash
API=http://localhost:8000/api/v1; ID=1

curl $API/opportunities/$ID/validation          # gates, evidence, stage history

curl -X POST $API/opportunities/$ID/interviews -H 'Content-Type: application/json' \
  -d '{"company_ref":"retailer-a","problem_confirmed":true,"interviewed_at":"2026-08-02"}'

curl -X POST $API/opportunities/$ID/evidence -H 'Content-Type: application/json' \
  -d '{"evidence_type":"paid_pilot","company_ref":"retailer-a","value":4500,"occurred_at":"2026-08-07"}'

curl -X PATCH $API/opportunities/$ID/stage -H 'Content-Type: application/json' \
  -d '{"status":"paid_pilot","note":"RM4,500 pilot invoiced and paid"}'
```

Or use the form at `/opportunities/{id}/validation` in the dashboard.

**The pipeline never promotes.** §52 — recording evidence updates
`suggested_status`; moving `status` is always a person's call. The gap between the
two is shown rather than auto-resolved.

**Recording a payment lifts §29's cap.** Rerun `intelligence score` and a topic
that was pinned under 79 can exceed it. On the demo data: 55.82 → 75.49, with
`+15 paid pilot bonus (§29)` stored in the breakdown, `WATCH → SELL_PILOT`.

**No personal data.** `customer_interviews` has no name, email, phone or company
name — §21 and §7 Gate 2, with a test asserting the schema never grows one.
`company_ref` is a pseudonymous label (`retailer-a`) whose only job is to let
Gate 3 count independent businesses without naming them.

## Reports and alerts

```bash
# §39's weekly report, built from stored data
docker compose exec api php artisan reports:generate --week-ending=2026-08-08 --verify
#   hash: d91f2f0e…
#   reproducible: yes — rebuilding produced an identical hash

# §40's alert conditions, deduplicated so a standing fact fires once
docker compose exec api php artisan alerts:check --notify

# which channels could actually deliver right now
docker compose exec api php artisan notifications:status
```

Or read them at `/reports` in the dashboard, which has a button to check
reproducibility on any stored report.

**Reproducible means checkable, not asserted.** Nothing in the builder reads the
clock — every query is bounded by the reporting window — nothing is written by an
LLM (§41), and every sort has a tiebreak so the hash cannot flap on identical
data. `GET /api/v1/reports/{id}/verify` rebuilds the period and compares.

**Alerts fire once.** §40's conditions are standing facts, not events, so each
carries a `dedupe_key` unique in the database. Reaching PRODUCTIZE alerts again;
staying at SELL_PILOT does not.

**Notifications default to `log`.** Nothing leaves the machine until
`NOTIFICATION_CHANNELS` says so.

## Scheduling

```bash
docker compose exec api php artisan schedule:list
docker compose exec api php artisan schedule:work    # nothing runs it by default
```

§38's schedule: ingest → normalize → classify → trends → aggregate → score daily,
alerts after scoring, report weekly on Monday. LLM extraction is deliberately
absent — it is the one stage that spends money per document.

## Outcomes and calibration

The loop the whole system exists to close. Record what happened when you took an
opportunity to a real business, then ask whether the score was right.

```bash
# §58 — conclude an opportunity
curl -X POST $API/opportunities/4/outcome -H 'Content-Type: application/json' -d '{
  "outcome": "no_budget",
  "reason": "Six owners agreed the problem is real. None had a budget line for it.",
  "concluded_at": "2026-08-09"}'

# §56 — money actually received (the ultimate KPI)
curl -X POST $API/opportunities/2/revenue -H 'Content-Type: application/json' -d '{
  "revenue_type": "paid_pilot", "amount": 4500,
  "company_ref": "retailer-c", "received_at": "2026-08-05"}'

# §57 — where was the model wrong?
docker compose exec api php artisan calibration:report
```

Or read it at `/outcomes` in the dashboard.

**The score is snapshotted, not joined.** By the time you conclude an outcome the
live score has already been dragged toward the answer by the evidence you logged
along the way — comparing it against the outcome it helped produce measures
nothing.

**Revenue is not evidence.** A signed proposal is one piece of evidence and zero
revenue until it is paid; a pilot invoiced monthly is one piece of evidence and
many revenue rows. Summing `commercial_evidence.value` would make §56's question
unanswerable.

**Calibration never edits `config/scoring.yaml`,** and it refuses to conclude
below 8 outcomes. §52 applies with more force here than anywhere: auto-tuning
would let a handful of results silently rewrite the model that ranks everything.

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
- LLM extraction is opt-in and disabled by default; the test suites and CI never make a paid API call. See `PROJECT_SPEC.md` §55 for the full milestone roadmap.
