<?php

namespace App\Services;

use App\Support\CommercialStage;

/**
 * §39's report as Markdown.
 *
 * Markdown rather than HTML because the document has three destinations — the
 * dashboard, a Discord message, an email — and a format that reads acceptably as
 * plain text survives all three. It is also diffable, which is how a reader
 * checks that this week's report differs from last week's only where the data
 * differs.
 *
 * The renderer is pure: same sections in, same string out. It reads no clock and
 * no database, which is what lets the content hash be taken over the structured
 * sections and still describe the rendered document.
 */
class ReportRenderer
{
    public function render(array $report): string
    {
        $sections = $report['sections'];

        $lines = [
            "# {$report['title']}",
            '',
            "**Period:** {$report['period_start']} to {$report['period_end']}",
            '',
        ];

        $lines = array_merge($lines,
            $this->executiveSummary($sections['executive_summary']),
            $this->risingProblems($sections['rising_problems']),
            $this->commercialOpportunities($sections['commercial_opportunities']),
            $this->newSignals($sections['new_signals']),
            $this->buyerEvidence($sections['buyer_evidence']),
            $this->opportunitiesToIgnore($sections['opportunities_to_ignore']),
            $this->suggestedExperiments($sections['suggested_experiments']),
            $this->buildRecommendation($sections['build_recommendation']),
            $this->footer($report['inputs'] ?? []),
        );

        return implode("\n", $lines)."\n";
    }

    private function executiveSummary(array $summary): array
    {
        $lines = ['## Executive Summary', ''];

        if ($summary['quiet_period'] ?? false) {
            // A quiet week is a finding, not a formatting problem. Saying so
            // beats three padded bullets that imply something happened.
            $lines[] = 'Nothing of commercial significance happened this period: no payments, no stage';
            $lines[] = 'advances, no newly rising problems. That is a real answer, not missing data.';
            $lines[] = '';

            return $lines;
        }

        foreach ($summary['findings'] as $index => $finding) {
            $lines[] = ($index + 1).". **{$finding['headline']}** — {$finding['detail']}";
        }

        $lines[] = '';

        return $lines;
    }

    private function risingProblems(array $rising): array
    {
        $lines = ['## Rising Problems', ''];

        if ($rising === []) {
            $lines[] = 'No topic had more mentions this period than the one before it.';
            $lines[] = '';

            return $lines;
        }

        $lines[] = '| Problem | Mentions | Previous | Change | Opportunity | Confidence |';
        $lines[] = '|---|---:|---:|---:|---:|---:|';

        foreach ($rising as $row) {
            $lines[] = sprintf(
                '| %s | %d | %d | %s | %s | %s |',
                $row['title'],
                $row['mentions'],
                $row['previous_mentions'],
                $row['change_label'],
                $this->number($row['opportunity_score']),
                $this->number($row['confidence_score']),
            );
        }

        $lines[] = '';

        return $lines;
    }

    private function commercialOpportunities(array $top): array
    {
        $lines = ['## Commercial Opportunities', ''];

        if ($top === []) {
            $lines[] = 'No opportunity has been scored yet. Run `intelligence score` after classification.';
            $lines[] = '';

            return $lines;
        }

        $lines[] = '| Opportunity | Pain | Commercial | Opportunity | Confidence | Stage | Next action |';
        $lines[] = '|---|---:|---:|---:|---:|---|---|';

        foreach ($top as $row) {
            $lines[] = sprintf(
                '| %s | %s | %s | %s | %s | %s | %s |',
                $row['title'],
                $this->number($row['pain_score']),
                $this->number($row['commercial_score']),
                $this->number($row['opportunity_score']),
                $this->number($row['confidence_score']),
                CommercialStage::LABELS[$row['stage']] ?? $row['stage'],
                $row['recommendation'] ?? '—',
            );
        }

        // §30 in one sentence, next to the only table where the two numbers sit
        // side by side and could be mistaken for the same kind of claim.
        $lines[] = '';
        $lines[] = '*Confidence is not part of the opportunity score. A high score at low confidence';
        $lines[] = 'means "looks attractive, evidence is still thin".*';
        $lines[] = '';

        return $lines;
    }

    private function newSignals(array $new): array
    {
        $lines = ['## New Signals', ''];

        if ($new === []) {
            $lines[] = 'No previously unseen problem appeared this period.';
            $lines[] = '';

            return $lines;
        }

        foreach ($new as $row) {
            $scored = $row['scored']
                ? 'opportunity score '.$this->number($row['opportunity_score'])
                : 'not scored yet';
            $lines[] = "- **{$row['title']}** — first seen {$row['first_seen']}, "
                ."{$row['signals']} signal(s), {$scored}.";
        }

        $lines[] = '';

        return $lines;
    }

    private function buyerEvidence(array $buyer): array
    {
        $lines = ['## Buyer Evidence', ''];

        $interviews = $buyer['interviews'] ?? [];
        $evidence = $buyer['evidence'] ?? [];
        $stageChanges = $buyer['stage_changes'] ?? [];

        if ($interviews === [] && $evidence === [] && $stageChanges === []) {
            $lines[] = 'No interviews, commercial evidence or stage changes were recorded this period.';
            $lines[] = '';
            $lines[] = '*Every score above therefore rests on inferred signals alone, and §29 caps';
            $lines[] = 'those at 79 however strong they look.*';
            $lines[] = '';

            return $lines;
        }

        if ($interviews !== []) {
            $lines[] = sprintf(
                '**Interviews:** %d recorded, %d confirming the problem.',
                count($interviews),
                $buyer['confirmations'] ?? 0,
            );
            $lines[] = '';

            foreach ($interviews as $interview) {
                $confirmed = match ($interview['problem_confirmed']) {
                    true => 'confirmed',
                    false => 'did not confirm',
                    default => 'not established',
                };
                $parts = array_filter([
                    $interview['industry'],
                    $interview['respondent_role'],
                    $interview['willingness_to_pay'] ? "pays {$interview['willingness_to_pay']}" : null,
                ]);
                $lines[] = sprintf(
                    '- %s (%s) — %s%s, %s',
                    $interview['title'] ?? 'unknown opportunity',
                    // Pseudonymous label only (§21): nothing here identifies anyone.
                    $interview['company_ref'] ?? 'unattributed',
                    $confirmed,
                    $interview['pilot_interest'] === true ? ', pilot interest' : '',
                    $parts === [] ? $interview['interviewed_at'] : implode(', ', $parts),
                );
            }

            $lines[] = '';
        }

        $paid = $buyer['paid_evidence'] ?? [];
        if ($paid !== []) {
            // Money leads. §7 Gate 4: a payment is a different grade of evidence
            // from everything else in this section.
            $total = array_sum(array_map(fn ($e) => (float) ($e['value'] ?? 0), $paid));
            $lines[] = '**Money changed hands:**';
            $lines[] = '';
            foreach ($paid as $row) {
                $lines[] = sprintf(
                    '- %s — %s%s from %s on %s',
                    $row['title'] ?? 'unknown opportunity',
                    str_replace('_', ' ', $row['evidence_type']),
                    $row['value'] === null ? ' (no amount recorded)' : ', '.$row['currency'].' '.number_format($row['value'], 2),
                    $row['company_ref'] ?? 'unattributed',
                    $row['occurred_at'],
                );
            }
            if ($total > 0) {
                $lines[] = '';
                $lines[] = '**Total recorded this period:** MYR '.number_format($total, 2);
            }
            $lines[] = '';
        }

        $soft = array_values(array_filter(
            $evidence,
            fn ($e) => ! in_array($e['evidence_type'], \App\Models\CommercialEvidence::PAID_TYPES, true)
        ));
        if ($soft !== []) {
            $lines[] = '**Other commercial signals:**';
            $lines[] = '';
            foreach ($soft as $row) {
                $lines[] = sprintf(
                    '- %s — %s (%s) from %s on %s',
                    $row['title'] ?? 'unknown opportunity',
                    str_replace('_', ' ', $row['evidence_type']),
                    $row['strength'],
                    $row['company_ref'] ?? 'unattributed',
                    $row['occurred_at'],
                );
            }
            $lines[] = '';
        }

        if ($stageChanges !== []) {
            $lines[] = '**Stage changes:**';
            $lines[] = '';
            foreach ($stageChanges as $change) {
                $from = CommercialStage::LABELS[$change['from']] ?? $change['from'] ?? 'new';
                $to = CommercialStage::LABELS[$change['to']] ?? $change['to'];
                $lines[] = "- {$change['title']}: {$from} → **{$to}**"
                    .($change['note'] ? " — {$change['note']}" : '');
            }
            $lines[] = '';
        }

        return $lines;
    }

    private function opportunitiesToIgnore(array $ignore): array
    {
        $lines = ['## Opportunities to Ignore', ''];

        $poor = $ignore['poorly_monetizable'] ?? [];
        $already = $ignore['already_ignored'] ?? [];

        if ($poor === [] && $already === []) {
            $lines[] = 'Nothing is drawing attention without a commercial case.';
            $lines[] = '';

            return $lines;
        }

        foreach ($poor as $row) {
            $lines[] = sprintf(
                '- **%s** — %d mentions, pain %s, commercial %s. %s',
                $row['title'],
                $row['mentions'],
                $this->number($row['pain_score']),
                $this->number($row['commercial_score']),
                $row['reason'],
            );
        }

        if ($already !== []) {
            $lines[] = '';
            $lines[] = 'Already marked IGNORE: '.implode(', ', array_column($already, 'title')).'.';
        }

        $lines[] = '';

        return $lines;
    }

    private function suggestedExperiments(array $experiments): array
    {
        $lines = ['## Suggested Experiments', ''];

        $suggested = $experiments['suggested'] ?? [];
        $inProgress = $experiments['in_progress'] ?? [];
        $concluded = $experiments['concluded_this_period'] ?? [];

        if ($suggested === [] && $inProgress === [] && $concluded === []) {
            $lines[] = 'Nothing is scoring high enough to justify an experiment yet.';
            $lines[] = '';

            return $lines;
        }

        foreach ($suggested as $row) {
            $lines[] = "- **{$row['title']}** — next gate: {$row['next_gate']}.";
            $lines[] = "  {$row['blocked_by']}";
            if ($row['suggested_experiment']) {
                $lines[] = "  *Try:* {$row['suggested_experiment']}";
            }
        }

        if ($inProgress !== []) {
            $lines[] = '';
            $lines[] = '**Already running:**';
            $lines[] = '';
            foreach ($inProgress as $row) {
                $lines[] = "- {$row['title']} — {$row['experiment_type']} ({$row['status']}): "
                    ."{$row['hypothesis']} · success = {$row['success_metric']}";
            }
        }

        if ($concluded !== []) {
            $lines[] = '';
            $lines[] = '**Concluded this period:**';
            $lines[] = '';
            foreach ($concluded as $row) {
                $verdict = $row['succeeded'] === null ? 'no verdict' : ($row['succeeded'] ? 'succeeded' : 'failed');
                $lines[] = "- {$row['title']} — {$row['experiment_type']}: **{$verdict}**"
                    .($row['result'] ? " — {$row['result']}" : '');
            }
        }

        $lines[] = '';

        return $lines;
    }

    private function buildRecommendation(array $build): array
    {
        $lines = ['## Build Recommendation', ''];

        if ($build['recommended'] === []) {
            $lines[] = $build['note'] ?? 'Nothing to build yet.';
            $lines[] = '';

            return $lines;
        }

        foreach ($build['recommended'] as $row) {
            $lines[] = sprintf(
                '- **%s** — %s, opportunity %s at confidence %s, currently %s.',
                $row['title'],
                $row['recommendation'],
                $this->number($row['opportunity_score']),
                $this->number($row['confidence_score']),
                CommercialStage::LABELS[$row['stage']] ?? $row['stage'],
            );
        }

        if (($build['deferred_by_cap'] ?? []) !== []) {
            // The cap is a deliberate constraint (§39), so what it excluded is
            // reported. Silently truncating would read as "these are all there
            // are" rather than "these are the two to start with".
            $lines[] = '';
            $lines[] = sprintf(
                'Held back by the %d-opportunity cap (§39): %s.',
                $build['cap'],
                implode(', ', array_column($build['deferred_by_cap'], 'title')),
            );
        }

        $lines[] = '';

        return $lines;
    }

    private function footer(array $inputs): array
    {
        $counts = $inputs['counts'] ?? [];
        $versions = $inputs['scoring_config_versions'] ?? [];

        return [
            '---',
            '',
            sprintf(
                '*Built from %d signals, %d interviews and %d commercial evidence records in this period, '
                .'across %d scored opportunities from %d enabled sources.*',
                $counts['signals_in_period'] ?? 0,
                $counts['interviews_in_period'] ?? 0,
                $counts['evidence_in_period'] ?? 0,
                $counts['scored_opportunities'] ?? 0,
                $counts['enabled_sources'] ?? 0,
            ),
            '',
            // The version matters for comparing two reports: the same window
            // scored under different weights legitimately differs, and a reader
            // needs to see that rather than conclude the data changed.
            '*Scoring weights: '.($versions === [] ? 'none recorded' : 'v'.implode(', v', $versions))
            .'. Report builder: '.($inputs['builder_version'] ?? 'unknown').'.*',
        ];
    }

    private function number(?float $value): string
    {
        return $value === null ? '—' : number_format($value, 0);
    }
}
