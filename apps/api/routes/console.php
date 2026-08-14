<?php

use Illuminate\Foundation\Inspiring;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\Schedule;

Artisan::command('inspire', function () {
    $this->comment(Inspiring::quote());
})->purpose('Display an inspiring quote');

/*
|--------------------------------------------------------------------------
| Schedule (PROJECT_SPEC.md §38)
|--------------------------------------------------------------------------
|
| §38's conceptual schedule, made real. Two things about the shape:
|
| The Python pipeline stages are invoked as shell commands rather than
| reimplemented as Laravel jobs. §37 lists both kinds of worker, and the split
| stays where it already is — Laravel owns the schema and the API, Python owns
| collection and scoring. A Laravel job that reimplemented classification would
| be a second implementation of the thing the tests already cover.
|
| Every stage runs `withoutOverlapping()`. Ingestion of a large dataset can
| outlast its own interval, and two concurrent runs of the same collector would
| both insert, both fail the content-hash dedup in different orders, and produce
| an ingestion_runs history nobody can read.
|
| The pipeline is chained by *ordering within one command list* rather than by
| `->then()` callbacks: normalization after ingestion, classification after
| normalization (§38). Running them as separate scheduled entries at staggered
| times would work most days and silently skip a day whenever ingestion ran long.
|
| Nothing here is enabled by a scheduler unless something runs
| `php artisan schedule:work` (or a cron calling `schedule:run`). The compose
| stack does not start one — see docs/reporting.md for why that is deliberate.
|
*/

// Shell out to the intelligence container's CLI. `docker compose exec` is not
// available from inside a container, so this assumes the scheduler runs on the
// host or that INTELLIGENCE_CLI is set to something that reaches it.
$intelligence = fn (string $subcommand): string => trim(
    (string) env('INTELLIGENCE_CLI', 'docker compose exec -T intelligence python -m intelligence.cli')
).' '.$subcommand;

// OFFICIAL DATA — "check according to dataset publication frequency".
// Fuel prices publish weekly (Wednesdays). Checked daily anyway because the
// publication day is theirs to change, and conditional-fetch support makes an
// unchanged check nearly free (§38: "Do not download unchanged official datasets
// unnecessarily").
//
// Both entries below go through `sources:ingest`, which reads the registry, so
// neither names a source. §13/§67 require adding a data source to be a
// config-only change, and a slug hardcoded here would break that in the most
// annoying way possible: the source works when run by hand and never runs again.
Schedule::command('sources:ingest --type=official_dataset')
    ->dailyAt('01:00')
    ->withoutOverlapping()
    ->description('§38 official data');

// TEXT SOURCES — "daily or source-appropriate frequency".
//
// Separate from official data so the two cadences can diverge without touching
// each other; news publishes continuously while a government dataset publishes
// weekly. Runs after official data rather than alongside it because article
// fetching is rate-limited and can take minutes, and a slow feed must not delay
// the dataset check.
Schedule::command('sources:ingest --type=news_feed')
    ->dailyAt('01:15')
    ->withoutOverlapping()
    ->description('§38 text sources');

// NORMALIZATION after ingestion; CLASSIFICATION after normalization.
Schedule::exec($intelligence('normalize'))
    ->dailyAt('01:30')
    ->withoutOverlapping()
    ->description('§38 normalization');

Schedule::exec($intelligence('classify'))
    ->dailyAt('02:00')
    ->withoutOverlapping()
    ->description('§38 classification');

// TREND DATA — daily. `trends compute` only recomputes derived metrics from
// stored observations, so it is safe to run whether or not new observations
// arrived. Collection itself is not scheduled: the CSV provider needs a
// hand-exported file, and the BigQuery one needs credentials most installs do
// not have (see docs/trends-data-sources.md).
Schedule::exec($intelligence('trends compute'))
    ->dailyAt('02:30')
    ->withoutOverlapping()
    ->description('§38 trend metrics');

// METRICS — daily.
Schedule::exec($intelligence('aggregate'))
    ->dailyAt('03:00')
    ->withoutOverlapping()
    ->description('§38 daily metrics');

// OPPORTUNITY SCORING — daily.
Schedule::exec($intelligence('score'))
    ->dailyAt('03:30')
    ->withoutOverlapping()
    ->description('§38 opportunity scoring');

// LLM extraction is deliberately NOT scheduled. It is the one stage that spends
// money per document, and a nightly job that quietly bills an API is exactly
// what config/llm.yaml's `enabled: false` default exists to prevent. Add it here
// only after deciding the budget — the guard will still stop it, but a scheduled
// entry that always refuses is noise.

// ALERTS — after scoring, so §40's score-based conditions see today's numbers.
Schedule::command('alerts:check --notify')
    ->dailyAt('04:00')
    ->withoutOverlapping()
    ->description('§40 alerting');

// REPORT — weekly. Monday morning for the week ending Sunday, so a full week of
// data is closed before it is summarised.
Schedule::command('reports:generate --notify --verify')
    ->weeklyOn(1, '06:00')
    ->withoutOverlapping()
    ->description('§39 weekly report');
