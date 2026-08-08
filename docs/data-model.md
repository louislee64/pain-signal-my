# Data Model — Milestone 4

Status: `sources`, `ingestion_runs`, `raw_documents` (Milestone 1); `normalized_documents`,
`topics`, `document_topics`, `problem_signals`, `topic_daily_metrics` (Milestone 2);
`keywords`, `trend_metrics` (Milestone 3); `opportunities`, `ai_usage` (Milestone 4) — all
per PROJECT_SPEC.md §20. `official_metrics` and the commercial CRM tables (§21) land later.

## Schema ownership

**Laravel owns the schema.** Migrations in `apps/api/database/migrations` are the single
source of truth for every table below. `apps/intelligence/src/intelligence/db.py` declares
the same tables as SQLAlchemy Core `Table` objects so Python can read/write them, but Python
never runs migrations or DDL — it only maps to what Laravel already created. This avoids two
schema definitions drifting out of sync in different languages.

## sources

The config-driven source registry (§12). Rows are upserted from `config/sources.yaml` by
`php artisan sources:sync` — never created by hand or by a collector.

- `collector` names a Python class registered in `collectors/registry.py`. It is a shared,
  generic collector (e.g. `data_gov_my_dataset`), never a one-off per-dataset class.
- `config` (jsonb) holds whatever that collector class needs (e.g. `dataset_id`,
  `date_column`) — this is what makes "add a dataset" a config change, not a code change.
- `last_synced_at` is the incremental-sync checkpoint (§38): collectors receive it as `since`
  and may use it to ask the upstream API for only what changed.
- Running `sources:sync` again is idempotent: it upserts by `slug` and disables any source
  slug that disappeared from the YAML (soft-disable, never deletes).

## ingestion_runs

One row per collector invocation. `records_received` is what the collector yielded;
`records_inserted` / `records_updated` / `unchanged` (not persisted, only returned to the
caller) / `records_rejected` account for it. A run's `status` is `succeeded` or `failed` —
a per-document failure does not fail the run (see below), so `failed` means the collector
itself raised (e.g. the upstream API was unreachable after retries).

## raw_documents

One row per natural key `(source_id, external_id)`. `content_hash` is a SHA-256 of the
collector's verbatim payload (canonical JSON, sorted keys) — this is what makes re-running a
collector against unchanged upstream data a no-op instead of a duplicate.

**On immutability.** PROJECT_SPEC.md §19 says the RAW layer is "exactly what was collected,
never modify." Read literally, that would mean a re-published upstream value should become a
*new* row rather than an in-place update. This implementation instead updates the existing
row when `content_hash` changes for the same `(source_id, external_id)` — chosen because
§20's `ingestion_runs.records_updated` field only makes sense if raw_documents *can* be
updated, and because for these sources "raw" already means "exactly the source's current
row for this key," not "every historical revision." The rule this implementation actually
enforces is the one immediately useful today: **normalization/classification (Milestone 2+)
must never write into raw_documents** — only a collector's own re-sync of its own natural key
may update a row. If a future source needs full revision history instead of latest-value,
give it a versioned natural key (e.g. append a revision or fetched-at component to
`external_id`) rather than changing this table's semantics.

### Why fuelprice as the first dataset

PriceCatcher is PROJECT_SPEC.md's flagship example (§14) but publishes over a million rows a
month and needs two lookup tables joined in — too much surface for the first collector to
prove idempotency against. `fuelprice` (data.gov.my dataset id `fuelprice`) is weekly,
~945 rows total, single endpoint, no auth, no joins — it proves the collector abstraction and
the insert/update/unchanged accounting cleanly. PriceCatcher (and any other data.gov.my
dataset) becomes a config-only addition once this pattern is trusted — see
[adding-a-data-source.md](./adding-a-data-source.md).

## normalized_documents

One row per `raw_document` (unique FK). Built by
`apps/intelligence/src/intelligence/normalize.py`:

- `cleaned_text` = title + body with HTML tags stripped and whitespace collapsed.
- `language` — `en` / `ms` / `zh` / `mixed` / `unknown`, from
  `apps/intelligence/src/intelligence/language.py`. This is a hand-rolled heuristic (CJK
  Unicode-range ratio for `zh`; an explicit Bahasa Malaysia function-word list for `ms`/
  `mixed`), not a general-purpose language-ID library — `langdetect` and similar do not
  reliably separate Malay from Indonesian, and a wrong "accurate-looking" answer is worse
  than an honestly crude, testable one. Classification does not gate on this field: keyword
  matching runs against the raw text regardless of detected language, so a wrong language tag
  degrades a display label, not a business decision.
- `country`/`state`/`city` — `country` is hard-coded `"MY"` (every source so far is
  Malaysia-only); `state` is passed straight through from `raw_documents.region_raw` with no
  parsing yet (fuelprice's collector sets that to the literal string `"MY"` since it has no
  per-state breakdown — a real `state`/city taxonomy is future work).
- `industry_id` exists (nullable, no FK constraint yet) but nothing populates it — no
  industries taxonomy exists yet. Deliberately deferred; add `config/industries.yaml` +
  a real FK when a source actually needs it.
- `normalized_content_hash` / `duplicate_of_normalized_document_id` — near-duplicate
  detection **beyond** `raw_documents.content_hash` (which only catches byte-identical
  re-fetches of the same natural key). This catches the same cleaned text arriving under a
  *different* natural key — e.g. syndicated copies (§42) — by hashing the lowercased,
  whitespace-collapsed `cleaned_text` and pointing at the first document with that hash. This
  is exact-after-cleaning matching only; true fuzzy near-duplicate similarity (§42) is not
  implemented — everything ingested so far is either structured government data or synthetic
  test fixtures, neither of which exercises genuine near-duplicate text.
- Neither `industry_id` nor the dedup FK/hash columns are in PROJECT_SPEC.md §20's literal
  field list for this table — both are minimal, justified extensions (see the immutability
  note above for the same kind of call on `raw_documents`).

## topics

The taxonomy from PROJECT_SPEC.md §4, synced from `config/topics.yaml` by
`php artisan topics:sync` (mirrors `sources:sync`). Self-referencing `parent_id` gives the
category → subtopic hierarchy. Sync is idempotent and soft-disables (never deletes) topics
removed from the YAML.

**Keywords are not a database column.** `config/topics.yaml` attaches a `keywords` list to
subtopics for the rule-based classifier, but `keywords` never syncs into the `topics` table —
it isn't in §20's field list, nothing displays it, and only
`apps/intelligence/src/intelligence/taxonomy.py` (loaded straight from the YAML) needs it.
Only 4 of the 12 top-level categories have subtopics/keywords defined yet — the ones
PROJECT_SPEC.md §4 actually enumerates (`billing_invoice`, `inventory_stock`,
`booking_reservation`, `customer_service`). The other 8 exist as enabled top-level rows with
no keywords, so the rule-based classifier can never match them yet — add keywords when a real
source needs that category.

## document_topics / problem_signals

`document_id` points at `normalized_documents.id`, not `raw_documents.id` — classification
runs after normalization (§22's pipeline order). Both tables have a `classification_method`
column (not in §20's literal list) with a unique constraint on
`(document_id, topic_id, classification_method)`: re-running rule-based classification
upserts in place instead of duplicating, and a future LLM-based method (§24, Milestone 4) can
coexist as a second row per document/topic rather than overwriting the rule-based one.

**Rule-based extraction is a deliberate stand-in for §24's LLM extraction**, not a
lower-quality version of the same thing — the goal for Milestone 2 is a keyword-driven,
zero-cost, fully deterministic pipeline that proves out end-to-end before any LLM
cost/latency/hallucination risk is introduced (§23). Concretely
(`apps/intelligence/src/intelligence/classify.py` + `signals.py` +
`config/signal_rules.yaml`):

- A document matches a topic if its cleaned text contains ≥1 of that topic's keywords
  (case-insensitive substring match — deliberately naive, since CJK text has no word
  boundaries to tokenize on and multi-word EN/BM phrases need substring matching anyway).
  `confidence` = `min(100, 50 + 25 × (matches - 1))`.
- `severity_score` / `urgency_score` / `economic_impact_score` are each the sum of matched
  keyword groups' `points` in `config/signal_rules.yaml`, clipped to 100. `frequency_hint`
  and `payer_type` come from the same file's keyword groups (first match wins for
  `payer_type`).
- `evidence_json` stores every matched keyword per dimension, plus the topic keywords that
  triggered the classification — so every score is traceable back to the literal text that
  produced it (§41: raw evidence must stay traceable).

Expect `config/signal_rules.yaml` to need real tuning once customer-discovery outcomes exist
(§57) — the point-values are an initial hypothesis, not a calibrated model.

## topic_daily_metrics

Rebuilt by `apps/intelligence/src/intelligence/aggregate.py` from `problem_signals`, grouped
by `(date, topic_id, region)`. Only `mention_count`, `source_count`, `avg_severity`, and
`avg_urgency` are populated in Milestone 2 — `trend_score` (needs Google Trends, Milestone 3),
`official_score`/`pain_score`/`commercial_score`/`opportunity_score` (need the scoring
formulas, Milestone 4) stay `NULL` until those milestones exist. `region` is `NOT NULL` with
`''` meaning "no region breakdown" rather than nullable — Postgres unique constraints treat
`NULL` as distinct per row, which would silently defeat the `(date, topic_id, region)` unique
constraint for every "no region" row.

Recomputation is a full rebuild over every date with any `problem_signals` row, not an
incremental "dirty dates" update — simple and correct at today's data volume; revisit if it
becomes slow.

## keywords

The Google Trends monitoring list (§15B), synced from `config/keywords.yaml` by
`php artisan keywords:sync`. Not in §20's table list — §16 names `keyword` and `keyword_group`
as things to store and §20's `trend_metrics` carries a `keyword_id`, so a keywords table is
required for that FK to point anywhere.

- Unique on `(keyword, geo)`: the same phrase can legitimately be tracked for different
  regions.
- `keyword_group` is the cluster (`sme_finance`, `inventory`, …). §15B is explicit that a
  single keyword is a weak proxy — the group is the unit of interpretation.
- `language` (`en`/`ms`/`zh`) exists because Malaysian search is genuinely trilingual (§43),
  and a problem phrased in Bahasa Malaysia does not surface under its English phrasing.
- `source` is `config` or `discovered`. This distinction is load-bearing: `keywords:sync`
  disables config keywords that vanish from the YAML, and must never do that to a term
  surfaced by a discovery provider (§15A), which was never in the file to begin with.

## trend_metrics

One row per `(keyword_id, date, region)`. Raw observations are written by
`intelligence trends collect`; the derived columns are filled by a second pass,
`intelligence trends compute`, because a rolling window can only be computed once the whole
series is present.

**`interest` is relative, 0-100, never absolute search volume** (§16) — see
[trends-data-sources.md](./trends-data-sources.md). Two provenance columns exist because of
that, both from §16's storage list and neither optional:

- `collection_method` — which adapter produced the row.
- `collection_batch` — a ULID per collection run. Trends scales values to the peak *within a
  single request*, so two batches are not comparable. Without this marker a later analysis
  could silently compare differently-scaled runs and read the artefact as a trend.

`region` is `NOT NULL` defaulting to `''` for the same reason as `topic_daily_metrics.region`:
Postgres treats `NULL` as distinct per row in a unique constraint, which would let unlimited
duplicate "national level" rows through.

### The derived metrics, defined precisely

Computed by `apps/intelligence/src/intelligence/trends/metrics.py`. §16 names these but does
not define them, so the definitions chosen are recorded here rather than left implicit:

| Column | Definition |
|---|---|
| `rolling_7d` | mean interest over the 7 calendar days ending on this row's date, inclusive |
| `rolling_30d` | mean interest over the 30 calendar days ending on this row's date |
| `baseline_90d` | mean interest over the 90 calendar days ending on this row's date |
| `growth_7d` | percent change of `rolling_7d` vs the 7-day window immediately before it |
| `growth_30d` | percent change of `rolling_30d` vs the 30-day window immediately before it |
| `growth_score` | `rolling_7d / baseline_90d` — §16's `trend_signal`; >1 means running hotter than baseline |
| `z_score` | `(latest interest − baseline_90d) / population stdev of the baseline window` |

Three decisions worth stating, because each has a plausible wrong alternative:

1. **Windows are calendar-day ranges, not counts of observations.** The two providers deliver
   different granularities — CSV exports are daily or weekly depending on range, the BigQuery
   discovery dataset is weekly. A count-based window would silently mean "7 weeks" for one
   provider and "7 days" for another. It also stops a window from reaching back across a
   collection gap further than intended.
2. **`None` is used for "undefined", never 0.** Growth against a zero-valued prior window has
   no finite percentage; a z-score against a perfectly flat baseline has no scale. Returning
   `0.0` would read as "no change" / "exactly average", which is a different and misleading
   claim.
3. **Each date is computed against only the observations up to that date.** Back-filling a
   history therefore produces exactly the values it would have produced had it been collected
   day by day — the series is not retroactively rewritten by later data.

`growth_score` uses the 7-day rolling average rather than the single latest reading so one
spiky day cannot dominate it. Note that on a *weekly* series `rolling_7d` necessarily equals
that week's raw value (only one observation falls in a 7-day window) — which is why the
dashboard chart plots `rolling_30d` as its smoothing line.

## opportunities

One row per topic (unique on `topic_id`), rewritten by
`apps/intelligence/src/intelligence/scoring/engine.py`. Holds the four scores
(§26, §27, §29, §30), a `recommendation` from §35's state machine, and —
the column that justifies the table existing at all — `score_components`.

`score_components` is JSONB storing, for every dimension of every score, its raw
input, its normalized 0–100 value, its weight, and its contribution. Normalization
makes the raw inputs (counts, percentages, dates) unrecoverable from the final
number, so without this a score is a claim nobody can check. Any adjustment the
engine applied is recorded as a note rather than left to be inferred — "capped at
79: not commercially validated" is stored text.

`scoring_config_version` records which set of weights produced the row, so scores
computed under different hypotheses are never silently compared. §57 expects
those weights to move.

Raw `date`/`Decimal` values are coerced to JSON-safe types before storage — the
`data_recency` dimension's raw input is a date, which is not JSONB-serializable
and failed loudly the first time it was written.

**Rescoring never touches `status`, `title`, or human-authored narrative fields**
(§52). The engine owns the numbers; a person owns the judgement. An engine that
reset someone's "we decided to ignore this" on every cron run would teach people
to stop recording decisions in the system.

## ai_usage

Every LLM call, successful or not, written before its result is used (§44).
Failed calls still consumed tokens, and omitting them would understate real spend
exactly when something is going wrong.

`estimated_cost` is `decimal(12,6)`. One extraction costs roughly $0.015; at 2dp a
thousand of them would round to either nothing or double. The name is honest —
these are published per-token rates, not an invoice.

`document_id` is the **`raw_documents`** ULID, not `normalized_documents.id`, and
it does double duty. Besides answering "what did this document cost", it is the
dedup key for extraction: a document is considered processed when a *successful*
row exists for it under the current `prompt_version`. Failed rows are excluded, so
a transient API error retries rather than blacklisting the document. See
`docs/llm-providers.md` for why dedup keys on the ledger instead of on produced
signals.

`prompt_version` and `processing_version` are stored per row (§70) so a shift in
extraction quality can be traced to the change that caused it.

## problem_signals from LLM extraction

LLM extraction writes `problem_signals` under `classification_method =
"llm_extract_problem_v1"`, alongside — never replacing — the rule-based
`rule_based_keyword_v1` rows. The unique constraint on `(document_id, topic_id,
classification_method)` is what makes that coexistence work, and it is why the
column was added in Milestone 2 before anything needed it.

The two methods are comparable by design: `frequency_hint` and `payer_type` use
the same vocabularies in both paths, because `ProblemExtraction`'s enums were
written against `config/signal_rules.yaml`'s values.

`evidence_json` on an LLM row carries the extraction's own account of itself —
affected role, one-line summary, suggested solution category, the model's
confidence — plus the provider, model and prompt version that produced it.

Two extractions are recorded but deliberately not trusted as evidence:
`problem_present: false` writes nothing, and an extraction below
`min_confidence` writes nothing while still being paid for and logged. A
low-confidence extraction that became a row would be indistinguishable from a
confident one. An invented topic slug is dropped rather than mapped to something
nearby — a wrong topic silently inflates that topic's score, while a missing one
only loses a signal.
