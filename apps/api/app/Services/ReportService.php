<?php

namespace App\Services;

use App\Models\Report;
use Carbon\CarbonImmutable;

/**
 * Builds, hashes and stores a report — the "reproducible" half of Milestone 7's
 * acceptance criterion.
 *
 * The hash is taken over the *structured sections*, not the Markdown. The
 * renderer is pure, so identical sections always render identically; hashing the
 * prose instead would make a wording change look like a data change, which is
 * exactly the signal the hash exists to carry.
 *
 * `generated_at` is deliberately excluded from the hash. It is metadata about the
 * run, not about the findings, and including it would make every report
 * trivially unique — turning a reproducibility check into a tautology.
 */
class ReportService
{
    public function __construct(
        private readonly ReportRenderer $renderer = new ReportRenderer(),
    ) {}

    /**
     * Generate the weekly report for the period ending on `$end`.
     *
     * Regenerating the same period replaces the row in place. §55 asks for
     * "report history", which is a history of periods rather than of attempts —
     * and a table with nine near-identical Tuesday reports is not a history,
     * it is a log.
     */
    public function generateWeekly(CarbonImmutable $end, ?CarbonImmutable $generatedAt = null): Report
    {
        $built = ReportBuilder::forWeekEnding($end)->build();
        $markdown = $this->renderer->render($built);
        $hash = $this->hash($built);

        // whereDate, not where: the builder returns 'Y-m-d' strings while the
        // column is a date, and a plain equality comparison misses whenever the
        // driver stores or returns a time component. The miss is silent — it
        // looks like "no existing report" and then trips the unique constraint.
        $existing = Report::query()
            ->where('report_type', 'weekly')
            ->whereDate('period_start', $built['period_start'])
            ->whereDate('period_end', $built['period_end'])
            ->first();

        $attributes = [
            'title' => $built['title'],
            'sections' => $built['sections'],
            'markdown' => $markdown,
            'inputs' => $built['inputs'],
            'content_hash' => $hash,
            'generated_at' => $generatedAt ?? now(),
        ];

        if ($existing !== null) {
            $existing->update($attributes);

            return $existing->fresh();
        }

        return Report::create($attributes + [
            'report_type' => 'weekly',
            'period_start' => $built['period_start'],
            'period_end' => $built['period_end'],
        ]);
    }

    /**
     * Build the same period again and report whether the findings changed.
     *
     * This is how the acceptance criterion gets *tested* rather than asserted.
     * A changed hash is not necessarily a bug — new evidence for a past week
     * legitimately changes that week's report — so this returns the facts and
     * leaves the judgement to the caller.
     */
    public function verifyReproducible(Report $report): array
    {
        $rebuilt = ReportBuilder::forWeekEnding(
            CarbonImmutable::parse($report->period_end)
        )->build();

        $hash = $this->hash($rebuilt);
        $markdown = $this->renderer->render($rebuilt);

        return [
            'reproducible' => $hash === $report->content_hash,
            'stored_hash' => $report->content_hash,
            'rebuilt_hash' => $hash,
            'markdown_identical' => $markdown === $report->markdown,
        ];
    }

    /**
     * A stable hash over the findings.
     *
     * `JSON_PRESERVE_ZERO_FRACTION` matters: without it 45.0 encodes as `45` and
     * 45.5 as `45.5`, so a score landing exactly on an integer would hash
     * differently from the same score computed a hair off — the hash would flap
     * on data that had not meaningfully changed.
     */
    private function hash(array $built): string
    {
        return hash('sha256', json_encode(
            [
                'title' => $built['title'],
                'period_start' => $built['period_start'],
                'period_end' => $built['period_end'],
                'sections' => $built['sections'],
                // Included: the same window under different scoring weights is
                // genuinely a different report, and the hash should say so.
                'inputs' => $built['inputs'],
            ],
            JSON_THROW_ON_ERROR | JSON_PRESERVE_ZERO_FRACTION | JSON_UNESCAPED_UNICODE,
        ));
    }
}
