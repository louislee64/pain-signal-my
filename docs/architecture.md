# Architecture

Status: Milestone 3 (Trends). This document reflects what exists today, not the full target architecture described in `PROJECT_SPEC.md` §8.

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
- **config/** (repo root) — mounted read-only into `api` and `intelligence` at `/config`. `config/sources.yaml` (source registry, §12) and `config/topics.yaml` (taxonomy, §4) sync into the DB via `php artisan sources:sync` / `topics:sync`. `config/keywords.yaml` (Trends monitoring clusters, §15B) syncs via `php artisan keywords:sync`. `config/signal_rules.yaml` (rule-based severity/urgency/economic-impact keyword weights) is read directly by Python — it has no DB-synced counterpart. See `docs/data-model.md`, `docs/adding-a-data-source.md` and `docs/trends-data-sources.md`.

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

## Trend pipeline (Milestone 3)

```text
config/keywords.yaml --keywords:sync--> keywords table (curated monitoring list, §15B)
                                              │
                    ┌─────────────────────────┴──────────────────────────┐
                    ▼                                                    ▼
     trends collect <provider>                              trends discover <provider>
     (§15B interest-over-time)                              (§15A top/rising terms)
                    │                                                    │
     trend_metrics raw interest                        new keywords rows, source='discovered'
     + collection_batch/method                         (keywords:sync never touches these)
                    │
     trends compute -> rolling_7d/30d, baseline_90d,
                       growth_7d/30d, growth_score, z_score
                    │
     GET /api/v1/trends            -> latest per keyword, most-rising first
     GET /api/v1/trends/{keyword}  -> full stored series
                    │
     Nuxt /trends page -> line chart + table view
```

Providers sit behind a `TrendProvider` interface (`trends/base.py`) resolved through
`trends/registry.py`, so a new source is one class plus one registry line. Two are
implemented: `google_trends_csv` (official CSV export — works today, no credentials) and
`google_trends_bigquery` (public dataset discovery — optional extra, needs a billed GCP
project). The official Trends API is `PROJECT_SPEC.md` §69's stated first preference but is
still an application-gated alpha with no public contract, so no adapter is written for it
yet — see `docs/trends-data-sources.md` for the full rationale and exactly what to add when
access is granted.

The Nuxt page reaches the API through a Nitro proxy (`/api/v1/**` in `nuxt.config.ts`) rather
than a configured absolute URL, because server-side rendering runs inside the container
(`http://api:8000`) while the browser uses a published host port — one same-origin path means
neither side has to know which it is.

## Intelligence layer (Milestone 4)

Two subsystems, deliberately kept apart.

**Scoring** (`src/intelligence/scoring/`) is deterministic and free. `measurements.py`
gathers per-topic facts from `problem_signals` joined back through
`normalized_documents` to `raw_documents` — the join exists so `distinct_sources`
counts *sources* rather than documents (§31), which is what makes fifty posts on one
forum stop looking like consensus. `model.py` holds pure functions with no database
or config access; `config.py` loads every weight from `config/scoring.yaml` and
**raises rather than defaulting** when a key is missing, because a silent default is a
hard-coded weight wearing a disguise. `engine.py` persists, and never writes
`status`, `title`, or human-authored narrative on a rescore (§52).

**LLM extraction** (`src/intelligence/llm/`) follows Milestone 1's collector and
Milestone 3's trend-provider pattern: an ABC with `check_available()` that raises an
actionable error, a registry, and adapters that are the only files importing a vendor
SDK. Two providers ship — `anthropic` (real, optional extra, needs a key) and
`fixture` (replays recorded answers, free, what CI uses).

The prompt lives in `llm/base.py`, not in the adapters. A prompt is part of the
extraction contract rather than a vendor detail; adapters whose prompts drifted apart
would make the §70 evaluation results incomparable between providers.

This is the first code path in the project that spends money per document, which is
why `config/llm.yaml` defaults `enabled: false`, the budget is checked before each
call rather than after the run, and dedup keys on the `ai_usage` ledger instead of on
produced signals. `docs/llm-providers.md` covers each guard and why it exists.

LLM and rule-based extraction coexist rather than compete: they write
`problem_signals` under different `classification_method` values, so running one never
destroys the other's evidence, and the scoring engine reads both.

## Dashboard (Milestone 5)

Nuxt pages read Laravel endpoints through the Nitro proxy; no page talks to Postgres
and no page recomputes a score. That constraint is what keeps the dashboard honest:
every number it shows was computed by the Python engine and stored, so the page and
the engine cannot disagree. The "fastest rising" card reads the same stored `growth`
raw value the detail page renders in its breakdown table.

Design tokens moved from `pages/trends.vue`'s scoped block to
`assets/css/tokens.css` when four more pages needed them. Scoped styles cannot share
custom properties, so the alternative was five copies of the palette drifting apart.

`Source::health()` lives on the Eloquent model rather than in `SourceController`
because the overview's collection block asks the same question the source page does.
A second implementation would drift silently — one page reporting no problems while
the other lists three — so a test asserts the two agree.

Two things §36 lists are deliberately absent, both for the same reason: they would
give the API write access to a pipeline the Python service owns.
`POST /sources/{id}/run` would hide a long-running collector behind a button;
scheduling is §38 (Milestone 7). And nothing in the dashboard writes to
`opportunities` — §52 keeps `status`, `title` and narrative fields human-authored.

`DemoDataSeeder` exists because a dashboard cannot be verified on an empty database
and the only real source so far (fuel prices) yields no topic matches by design. It
writes signals and evidence, never `opportunities` rows, so what the pages display
is the real engine's output rather than a hand-written number that would make a
broken scorer look fine. Everything is prefixed `demo_`; `demo:purge` removes exactly
that prefix and nothing else.

## Commercial validation (Milestone 6)

The first write path in the project, and the only one. Three tables (§21) hang off
`opportunities`; Laravel owns them and Python reads them.

`CommercialStage` (a plain support class, not a model) holds §3's funnel and §7's
gate checks. It lives in one place because three things ask about stages — the API,
the dashboard, and the suggestion logic — and a funnel whose order is written down
in three places is three funnels.

Two columns encode §52. `status` is human-only, written exclusively by
`PATCH /stage`. `suggested_status` is what the engine computes from the gates and
rewrites on every evidence change. Neither the scoring pipeline nor an evidence
write can move `status`, which is the one invariant this milestone is built around.

The evidence counting rules exist **twice** — `Opportunity::evidenceSummary()` in
PHP and `scoring/commercial.py` in Python — because Laravel decides whether a
promotion is allowed and Python decides whether §29's cap lifts. That duplication
is deliberate (neither service should call the other synchronously for this) and
guarded: a test reads the PHP source and asserts the evidence-type lists match. If
they drifted, an opportunity could sit at `paid_pilot` while scoring as though
nobody had ever paid, and nothing else in the system would report it.

`Opportunity::evidenceSummary()` is one method rather than four call sites
computing the same counts, because the gate check, the suggestion, the API response
and the transition snapshot must all see identical numbers — otherwise the UI
offers a promotion the API then refuses.

## Reporting and scheduling (Milestone 7)

`ReportBuilder` → `ReportRenderer` → `ReportService`, split by what changes for
different reasons: what the findings *are*, how they *read*, and how they are
*stored and hashed*. The renderer is pure — no clock, no database — which is what
lets the content hash be taken over the structured sections and still describe the
rendered document.

Reports are stored three ways because each answers a different question:
`sections` for consumers, `markdown` frozen so a report cannot change under its
reader, and `inputs` (config versions, row counts) so "reproducible" is falsifiable
rather than a claim.

`AlertDetector` writes rows; the command sends them. Separating detection from
delivery means a delivery outage leaves alerts pending rather than losing them,
and a `dedupe_key` unique in the database is what stops §40's standing conditions
re-firing nightly.

Notification channels follow the same shape as collectors, trend providers and LLM
providers: interface, registry, `checkAvailable()` with an actionable message. The
default is `log` only — nothing leaves the machine until an operator says so.

The scheduler shells out to the Python CLI rather than reimplementing the pipeline
as Laravel jobs. §37 lists both kinds of worker; the split stays where it already
is. Nothing starts a scheduler in the compose stack, so the schedule is inert
until someone runs `schedule:work` or wires a cron.

`Collector.collect()` gained a `fetch_state` argument and a `fetch_state()`
companion for §38's conditional fetching. `SourceUnchanged` is an exception rather
than an empty iterator because "unchanged" and "empty" are different outcomes, and
`last_successful_sync` is separate from `last_synced_at` for the same reason.

## The feedback loop (Milestone 8)

Two tables and one analyser close §57's loop. `opportunity_revenue` is separate
from `commercial_evidence` because "something happened" and "money arrived" are
different claims; `opportunity_outcomes` snapshots the score and the counts at
conclusion rather than joining them live, because a live score has already been
dragged toward the answer by the evidence recorded along the way.

`CalibrationAnalyser` is the only component in the system whose subject is the
system. Its two defining constraints are both refusals: it never writes
`config/scoring.yaml` (§52, applied to the model itself), and it declines to
conclude below a sample size — every finding carries its support count, and the
`sample.sufficient` flag exists so no consumer can mistake "the model is
miscalibrated" for "we have four data points".

`SuccessMetrics` keeps §56's technical/business split rather than flattening it.
The state it is designed to make visible is a green technical panel above an empty
business panel: everything runs and nothing has been sold.

§59's machine learning is deliberately absent — the spec opens that section with
"Do NOT start here", and `opportunity_outcomes` is shaped as its eventual training
set.

## Public text sources

The first text source: eight Malaysian news/business RSS feeds via a
config-driven `rss_feed` collector. Full detail and measurements in
[text-sources.md](text-sources.md); the decisions worth recording here are the
architectural ones.

**Two new dependencies, both narrow.** `feedparser` handles the malformed-but-real
feeds publishers actually serve (mismatched encodings, RSS 2.0 vs Atom, missing
dates) and `trafilatura` extracts article bodies. Both replace work that is
classically a mistake to hand-roll: a regex feed parser and per-publisher CSS
selectors that break on every redesign. `trafilatura` is imported lazily so
nothing in the scoring, reporting or API paths pays its `lxml` import cost.

**§17's obligations live in one module, not in each collector.**
`collectors/fetching.py` holds the robots.txt cache, the per-host rate limiter
that honours `Crawl-delay`, and §21's contact scrubber. Putting them behind the
collector interface would make them optional; putting them in a shared module
that `ArticleFetcher` always applies makes skipping them require deliberate
effort.

**§21 is enforced at collection, which contradicts §18, on purpose.** §18 wants an
immutable raw layer; §21 says do not collect unnecessary personal information. For
free-form human text these conflict: once a phone number reaches
`raw_documents`, immutability preserves it forever. The scrub therefore runs
before storage, and provenance is redefined as source + URL + feed entry + fetch
timestamp + `body_source`/`body_fetch_note` — a faithful record of what arrived
and how, rather than a byte-identical copy of the publisher's HTML. This is the
one place in the project where "raw" is not literally raw, and it is the reason
`body_source` exists.

**The schedule stopped naming sources.** `sources:ingest` reads the registry, so
§13/§67's config-only promise now extends to the scheduler. A hardcoded slug in
`routes/console.php` broke it invisibly: a new source worked by hand and never ran
again.

**Two latent defects surfaced, both invisible until a second source existed:**

- `get_unclassified_documents` had `LIMIT` with no `ORDER BY`, and documents that
  match nothing are re-scanned forever by design. Postgres could return the same
  arbitrary 500 never-matching rows indefinitely, so once the unmatched backlog
  passed the batch size, newly ingested documents were never classified at all.
  With 945 fuel-price documents ahead of them, the news articles were
  unreachable. Now newest-first with an id tiebreak
  (`tests/test_classification_order.py`).
- Laravel migrations create `timestamp(0)` columns — WITHOUT time zone — so
  Postgres returns naive datetimes despite `db.py` declaring
  `DateTime(timezone=True)`. Any collector comparing `since` against a parsed date
  raised, but only on the **second** run, because the first has no
  `last_successful_sync`. Fixed once at the read boundary in
  `repositories/sources.py`.

§38's conditional-fetch path, written for data.gov.my and never exercised because
that API sends no validators, now returns real 304s from live feeds.

## Why this shape

- Three independently deployable apps sharing two datastores, per `PROJECT_SPEC.md` §8/§9 — no message broker or orchestrator introduced yet (`PROJECT_SPEC.md` §54 explicitly excludes Kafka/Kubernetes for V1).
- `intelligence`'s dependencies are `pydantic`, `sqlalchemy`, `psycopg`, `httpx`, `redis`, `python-dotenv`, `python-ulid`, `pyyaml`, plus `feedparser` and `trafilatura` for feed parsing and article extraction — the heavier analytics libraries named in `PROJECT_SPEC.md` §9 (`pandas`, `polars`, `pyarrow`, `scikit-learn`, `numpy`) still haven't been needed even through normalization/classification/aggregation (plain regex, dict-based rules, and SQL `GROUP BY` cover it); add them when a milestone's workload actually calls for a dataframe or a model, not preemptively.
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

`official_metrics` (§20), and §59's machine learning, which the spec explicitly
defers until enough outcome data exists. The practical gap remains data rather
than code, though it has narrowed: eight news feeds now supply real Malaysian
text, but news carries macroeconomic commentary rather than SME operational
complaints (measured yield: 9 keyword matches in 191 articles — see
[text-sources.md](text-sources.md)). What would move the needle is a source where
owners describe their own problems — a forum, app-store reviews, an
industry-association list — each of which carries a terms question the news feeds
do not. `vulcanpost_my` is registered but disabled because 9 of 10 entries were
Singaporean; enabling it needs per-entry country detection rather than a
per-source region constant. `LLMProvider.classify_problem()` and `generate_summary()` are
declared but raise: the rule-based classifier already assigns topics deterministically and for
free, and no milestone needs summaries yet — better an unimplemented method than a plausible
stub. See `PROJECT_SPEC.md` §55 for the milestone sequence.
