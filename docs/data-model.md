# Data Model — Milestone 1

Status: `sources`, `ingestion_runs`, `raw_documents` only (PROJECT_SPEC.md §20). Later
tables (`normalized_documents`, `topics`, `problem_signals`, etc.) land in Milestone 2+.

## Schema ownership

**Laravel owns the schema.** Migrations in `apps/api/database/migrations` are the single
source of truth for these three tables. `apps/intelligence/src/intelligence/db.py` declares
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
