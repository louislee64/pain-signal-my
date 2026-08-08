<?php

namespace App\Console\Commands;

use App\Services\CalibrationAnalyser;
use Illuminate\Console\Command;

/**
 * §57's feedback loop, on the terminal.
 *
 * Prints what looks miscalibrated and stops. It never edits
 * config/scoring.yaml — §52 applies with more force here than anywhere else,
 * because auto-tuning would let a handful of outcomes silently rewrite the model
 * that ranks everything.
 */
class CalibrationReport extends Command
{
    protected $signature = 'calibration:report {--json : Machine-readable output}';

    protected $description = 'Report where the scoring model was wrong, using recorded outcomes (§57)';

    public function handle(CalibrationAnalyser $analyser): int
    {
        $report = $analyser->analyse();

        if ($this->option('json')) {
            $this->line(json_encode($report, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));

            return self::SUCCESS;
        }

        $sample = $report['sample'];
        $this->info("Outcomes recorded: {$sample['outcomes_recorded']}");

        if (! $sample['sufficient']) {
            $this->warn($sample['note']);
            $this->newLine();
        }

        if ($report['accuracy'] !== null) {
            $a = $report['accuracy'];
            $this->line('Against the §35 INVESTIGATE threshold of '.$a['score_threshold'].':');
            $this->table(
                ['', 'Worked', 'Failed'],
                [
                    ['Scored high', $a['scored_high_and_worked'], $a['scored_high_and_failed']],
                    ['Scored low', $a['scored_low_and_worked'], $a['scored_low_and_failed']],
                ]
            );
            // Named rather than left as a cell: these are the two errors that
            // cost something, and they cost different things.
            $this->line("  wasted effort: {$a['wasted_effort']}   missed: {$a['missed']}");
            $this->newLine();
        }

        if ($report['overestimated'] !== []) {
            $this->warn('Overestimated (§57 Opportunity A):');
            foreach ($report['overestimated'] as $row) {
                $this->line(sprintf(
                    '  %s — scored %s, %d interviews, ended %s%s',
                    $row['title'],
                    number_format($row['initial_score'], 0),
                    $row['buyer_interviews'],
                    str_replace('_', ' ', $row['outcome']),
                    $row['implicates'] ? " (implicates {$row['implicates']})" : '',
                ));
            }
            $this->newLine();
        }

        if ($report['underestimated'] !== []) {
            $this->warn('Underestimated (§57 Opportunity B):');
            foreach ($report['underestimated'] as $row) {
                $this->line(sprintf(
                    '  %s — scored %s, %d paid pilot(s), MYR %s revenue',
                    $row['title'],
                    number_format($row['initial_score'], 0),
                    $row['paid_pilots'],
                    number_format($row['revenue'], 2),
                ));
            }
            $this->newLine();
        }

        $signals = collect($report['dimension_signals'])->filter(fn ($s) => $s['verdict'] !== null);
        if ($signals->isNotEmpty()) {
            $this->line('Dimensions that may be mis-weighted:');
            foreach ($signals as $name => $signal) {
                $this->line(sprintf(
                    '  %-26s %s (failed %s vs worked %s, %d examples)',
                    $name,
                    $signal['verdict'],
                    $signal['mean_in_overestimated'],
                    $signal['mean_in_underestimated'],
                    $signal['support'],
                ));
            }
            $this->newLine();
        }

        $revenue = $report['revenue'];
        $this->info(sprintf(
            'Opportunity-Generated Revenue: %s %s across %d opportunity(ies)',
            $revenue['currency'],
            number_format($revenue['total'], 2),
            $revenue['revenue_generating_opportunities'],
        ));
        $this->newLine();

        foreach ($report['suggestions'] as $suggestion) {
            $this->line("• {$suggestion['text']}");
        }

        $this->newLine();
        $this->comment('Nothing here has been applied. Weights live in config/scoring.yaml and are yours to change (§52).');

        return self::SUCCESS;
    }
}
