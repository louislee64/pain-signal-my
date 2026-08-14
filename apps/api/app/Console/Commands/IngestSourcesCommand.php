<?php

namespace App\Console\Commands;

use App\Models\Source;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Process;

/**
 * Run the collector for every enabled source (PROJECT_SPEC.md §38).
 *
 * This exists so the schedule does not name sources. §13/§67 require that
 * adding a data source be a config-only change, and a scheduler with
 * `ingest data_gov_my_fuelprice` hardcoded quietly breaks that promise: the
 * source registers, syncs, ingests by hand, and then never runs again because
 * nobody remembered to edit routes/console.php. The registry is already the
 * list of what to collect, so it is the list this reads.
 */
class IngestSourcesCommand extends Command
{
    protected $signature = 'sources:ingest
        {--type= : Only sources with this source_type (e.g. news_feed)}
        {--source= : Only this slug}
        {--timeout=1800 : Seconds allowed per source}';

    protected $description
        = 'Run the intelligence collector for each enabled source in the registry (§38)';

    public function handle(): int
    {
        $query = Source::query()->where('enabled', true);

        if ($type = $this->option('type')) {
            $query->where('source_type', $type);
        }
        if ($slug = $this->option('source')) {
            $query->where('slug', $slug);
        }

        $sources = $query->orderBy('slug')->get();

        if ($sources->isEmpty()) {
            // Not a failure in itself, but it must not look like success either:
            // a filter that matches nothing is usually a typo, and silently
            // reporting "done" is how a schedule ends up collecting nothing.
            $this->warn('No enabled sources matched. Nothing ingested.');

            return self::SUCCESS;
        }

        $failed = [];

        foreach ($sources as $source) {
            $this->info("Ingesting {$source->slug} …");

            $result = Process::timeout((int) $this->option('timeout'))
                ->run($this->commandFor($source->slug));

            // The CLI prints one JSON object per run on its last line. Echo the
            // whole output rather than parsing it: this command's job is to
            // invoke collectors, and ingestion_runs already holds the record.
            $output = trim($result->output().$result->errorOutput());
            if ($output !== '') {
                $this->line($output);
            }

            if ($result->failed()) {
                $failed[] = $source->slug;
                $this->error("  {$source->slug} failed (exit {$result->exitCode()})");
            }
        }

        if ($failed !== []) {
            $this->error('Failed sources: '.implode(', ', $failed));

            // Non-zero when ANY source failed, matching the single-source CLI's
            // contract so `sources:ingest` behaves the same way whether it runs
            // one collector or eight. Every other source still ran first — one
            // broken publisher must not stop the rest — and the /sources health
            // page is where chronic failure is told apart from a bad night.
            return self::FAILURE;
        }

        $this->info("Ingested {$sources->count()} source(s).");

        return self::SUCCESS;
    }

    /**
     * How to reach the Python CLI.
     *
     * Same env var as routes/console.php on purpose: there should be exactly one
     * definition of how Laravel talks to the intelligence container, because two
     * would disagree the first time someone deploys them differently.
     */
    private function commandFor(string $slug): string
    {
        $base = trim((string) env(
            'INTELLIGENCE_CLI',
            'docker compose exec -T intelligence python -m intelligence.cli'
        ));

        return "{$base} ingest {$slug}";
    }
}
