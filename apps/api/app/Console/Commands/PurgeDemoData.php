<?php

namespace App\Console\Commands;

use App\Models\NormalizedDocument;
use App\Models\Opportunity;
use App\Models\ProblemSignal;
use App\Models\RawDocument;
use App\Models\Source;
use App\Models\TopicDailyMetric;
use Database\Seeders\DemoDataSeeder;
use Illuminate\Console\Command;

/**
 * Removes exactly what DemoDataSeeder created.
 *
 * Seeded data that cannot be cleanly removed is a trap: it survives into
 * screenshots, into reports, and eventually into a decision. Deletion is scoped
 * strictly to sources whose slug carries the `demo_` prefix — this command must
 * never be able to touch a real source, however it is invoked.
 */
class PurgeDemoData extends Command
{
    protected $signature = 'demo:purge {--force : Skip confirmation}';

    protected $description = 'Delete every row created by DemoDataSeeder (demo_ prefixed sources and their documents)';

    public function handle(): int
    {
        $sources = Source::where('slug', 'like', DemoDataSeeder::PREFIX.'%')->get();

        if ($sources->isEmpty()) {
            $this->info('No demo sources found. Nothing to purge.');

            return self::SUCCESS;
        }

        $rawIds = RawDocument::whereIn('source_id', $sources->pluck('id'))->pluck('id');
        $documentIds = NormalizedDocument::whereIn('raw_document_id', $rawIds)->pluck('id');
        $signals = ProblemSignal::whereIn('document_id', $documentIds);

        $this->table(
            ['What', 'Count'],
            [
                ['Demo sources', $sources->count()],
                ['Raw documents', $rawIds->count()],
                ['Normalized documents', $documentIds->count()],
                ['Problem signals', (clone $signals)->count()],
            ]
        );

        if (! $this->option('force') && ! $this->confirm('Delete these rows?', true)) {
            $this->warn('Aborted.');

            return self::FAILURE;
        }

        // Child rows first: the FKs would otherwise refuse, and a partial
        // delete is worse than none.
        $signals->delete();
        \DB::table('document_topics')->whereIn('document_id', $documentIds)->delete();
        NormalizedDocument::whereIn('id', $documentIds)->delete();
        RawDocument::whereIn('id', $rawIds)->delete();
        \App\Models\IngestionRun::whereIn('source_id', $sources->pluck('id'))->delete();
        Source::whereIn('id', $sources->pluck('id'))->delete();

        $this->info('Demo sources and their documents deleted.');

        // Derived rows are left in place deliberately. They are recomputed from
        // whatever signals remain by `intelligence aggregate` / `score`, and
        // deleting an opportunity here would also destroy any human-authored
        // narrative on it (§52).
        $stale = Opportunity::count() + TopicDailyMetric::count();
        if ($stale > 0) {
            $this->warn('Derived rows (opportunities, topic_daily_metrics) still reflect the demo signals.');
            $this->warn('Recompute them: intelligence aggregate && intelligence score');
        }

        return self::SUCCESS;
    }
}
