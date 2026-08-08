<?php

namespace App\Console\Commands;

use App\Notifications\Notifier;
use App\Services\ReportService;
use Carbon\CarbonImmutable;
use Illuminate\Console\Command;

/**
 * §39's weekly report — the "automatic" half of Milestone 7's acceptance
 * criterion when run from the scheduler, the reproducible half when run twice.
 */
class GenerateReport extends Command
{
    protected $signature = 'reports:generate
        {--week-ending= : Last date of the reporting period (Y-m-d). Defaults to yesterday.}
        {--notify : Deliver via the configured notification channels}
        {--verify : Rebuild the same period afterwards and report whether it matched}';

    protected $description = 'Generate the §39 weekly opportunity report from stored data';

    public function handle(ReportService $reports): int
    {
        // Defaults to yesterday, not today: a report for a day still in progress
        // would change if regenerated an hour later, which is the one thing the
        // acceptance criterion forbids.
        $end = $this->option('week-ending')
            ? CarbonImmutable::parse($this->option('week-ending'))
            : CarbonImmutable::yesterday();

        $report = $reports->generateWeekly($end);

        $this->info("Report generated: {$report->period_start->toDateString()} to {$report->period_end->toDateString()}");
        $this->line("  hash: {$report->content_hash}");
        $this->line('  findings: '.count($report->sections['executive_summary']['findings'] ?? []));

        if ($this->option('verify')) {
            $check = $reports->verifyReproducible($report);
            if ($check['reproducible']) {
                $this->info('  reproducible: yes — rebuilding produced an identical hash');
            } else {
                // Not necessarily a bug: new evidence for a past period
                // legitimately changes that period's report. Reported plainly and
                // left for a person to judge.
                $this->warn('  reproducible: NO');
                $this->warn("    stored:  {$check['stored_hash']}");
                $this->warn("    rebuilt: {$check['rebuilt_hash']}");
                $this->warn('    Either the underlying data changed, or the builder is not deterministic.');
            }
        }

        if ($this->option('notify')) {
            $notifier = new Notifier();
            $this->line('  channels: '.implode(', ', $notifier->channelNames()));

            $results = $notifier->send($report->title.' — '.$report->period_end->toDateString(), $report->markdown);

            foreach ($results as $result) {
                $result['delivered']
                    ? $this->info("  delivered via {$result['channel']}")
                    : $this->error("  {$result['channel']} failed: {$result['error']}");
            }
        }

        return self::SUCCESS;
    }
}
