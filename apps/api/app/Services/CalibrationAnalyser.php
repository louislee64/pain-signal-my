<?php

namespace App\Services;

use App\Models\OpportunityOutcome;
use App\Models\OpportunityRevenue;
use Illuminate\Support\Collection;

/**
 * §57's feedback loop: where was the scoring model wrong?
 *
 * > "Every commercial result must feed back into scoring... Adjust scoring
 * > weights using real commercial outcomes. Eventually the scoring system
 * > becomes personalized to what this developer can actually sell and build."
 *
 * Two things this deliberately does NOT do, and both matter more than anything
 * it does:
 *
 * **It never edits config/scoring.yaml.** §52's rule applies with more force
 * here than anywhere else in the system: auto-tuning weights would let five
 * outcomes silently rewrite the model that ranks everything, and the developer
 * would have no idea why last month's rankings no longer reproduce. The report
 * says what looks wrong and by how much; a person makes the edit.
 *
 * **It refuses to conclude from too little data.** Nothing here is statistics —
 * with six outcomes there is no statistics to do — so instead of computing a
 * correlation coefficient nobody should trust, every finding carries the count
 * behind it and the report states plainly when that count is too small to act
 * on. §30's separation of score from confidence, applied to the system's
 * opinion of itself.
 */
class CalibrationAnalyser
{
    /**
     * Below this, the report describes rather than concludes.
     *
     * Not a statistical threshold — it is the point below which a single
     * unusual outcome moves every average enough to mislead. With four
     * outcomes, one bad week looks like a broken model.
     */
    public const MIN_OUTCOMES_TO_CONCLUDE = 8;

    /** Per-pattern minimum. Two examples of anything is an anecdote. */
    public const MIN_PATTERN_SUPPORT = 3;

    /**
     * A score this far above what the outcome justified counts as
     * overestimation. On a 0–100 scale, 20 points is roughly two §35
     * recommendation bands — enough that it changed what you would have done.
     */
    public const MISCALIBRATION_THRESHOLD = 20.0;

    public function analyse(): array
    {
        $outcomes = OpportunityOutcome::with('opportunity:id,title')
            ->whereNotNull('initial_score')
            ->orderBy('id')
            ->get();

        $total = $outcomes->count();

        if ($total === 0) {
            return $this->nothingYet();
        }

        $overestimated = $this->overestimated($outcomes);
        $underestimated = $this->underestimated($outcomes);

        return [
            'sample' => [
                'outcomes_recorded' => $total,
                'minimum_to_conclude' => self::MIN_OUTCOMES_TO_CONCLUDE,
                // The single most important field in this payload. Every
                // consumer must be able to tell "the model is miscalibrated"
                // from "we have four data points".
                'sufficient' => $total >= self::MIN_OUTCOMES_TO_CONCLUDE,
                'note' => $total >= self::MIN_OUTCOMES_TO_CONCLUDE
                    ? null
                    : sprintf(
                        'Only %d outcome(s) recorded. This report describes what has happened; '
                        .'it is not yet a basis for changing weights in config/scoring.yaml.',
                        $total,
                    ),
            ],
            'accuracy' => $this->accuracy($outcomes),
            'overestimated' => $overestimated,
            'underestimated' => $underestimated,
            'by_outcome' => $this->byOutcome($outcomes),
            'dimension_signals' => $this->dimensionSignals($outcomes, $overestimated, $underestimated),
            'revenue' => $this->revenue(),
            'suggestions' => $this->suggestions($outcomes, $overestimated, $underestimated),
        ];
    }

    private function nothingYet(): array
    {
        return [
            'sample' => [
                'outcomes_recorded' => 0,
                'minimum_to_conclude' => self::MIN_OUTCOMES_TO_CONCLUDE,
                'sufficient' => false,
                'note' => 'No outcomes recorded yet. Conclude an opportunity via '
                    .'POST /api/v1/opportunities/{id}/outcome once you have taken it to '
                    .'a real business and found out.',
            ],
            'accuracy' => null,
            'overestimated' => [],
            'underestimated' => [],
            'by_outcome' => [],
            'dimension_signals' => [],
            // Same shape as the populated path, not a hand-written subset: a
            // caller that has to handle two shapes will eventually handle one
            // of them wrong.
            'revenue' => $this->revenue(),
            'suggestions' => [],
        ];
    }

    /**
     * How often a high score meant a good outcome, and vice versa.
     *
     * Reported as four counts rather than as a single accuracy percentage. A
     * percentage hides the asymmetry, and the asymmetry is the whole point:
     * scoring something high that flopped costs weeks of wasted effort, while
     * scoring something low that would have worked costs an opportunity you
     * never knew you missed. They are not the same error and should not average.
     */
    private function accuracy(Collection $outcomes): array
    {
        $threshold = 60.0;   // §35's INVESTIGATE floor

        $truePositive = $outcomes->filter(
            fn ($o) => (float) $o->initial_score >= $threshold && $o->isPositive()
        )->count();
        $falsePositive = $outcomes->filter(
            fn ($o) => (float) $o->initial_score >= $threshold && ! $o->isPositive()
        )->count();
        $trueNegative = $outcomes->filter(
            fn ($o) => (float) $o->initial_score < $threshold && ! $o->isPositive()
        )->count();
        $falseNegative = $outcomes->filter(
            fn ($o) => (float) $o->initial_score < $threshold && $o->isPositive()
        )->count();

        return [
            'score_threshold' => $threshold,
            'scored_high_and_worked' => $truePositive,
            'scored_high_and_failed' => $falsePositive,
            'scored_low_and_failed' => $trueNegative,
            'scored_low_and_worked' => $falseNegative,
            'wasted_effort' => $falsePositive,
            'missed' => $falseNegative,
        ];
    }

    /**
     * §57's Opportunity A: "score = 92, 10 interviews, 0 businesses willing to
     * pay. Result: commercial assumptions were wrong."
     *
     * The test is not "high score and bad outcome" — that would flag an
     * opportunity nobody actually pursued. It requires real effort to have gone
     * in: interviews happened, and still nothing came of it. Without that
     * condition the report would blame the model for work that was never done.
     */
    private function overestimated(Collection $outcomes): array
    {
        return $outcomes
            ->filter(fn ($o) => ! $o->isPositive())
            ->filter(fn ($o) => $o->buyer_interviews >= 2)
            ->filter(fn ($o) => (float) $o->initial_score >= self::MISCALIBRATION_THRESHOLD * 2)
            ->sortByDesc('initial_score')
            ->map(fn ($o) => [
                'opportunity_id' => $o->opportunity_id,
                'title' => $o->opportunity?->title,
                'initial_score' => (float) $o->initial_score,
                'initial_commercial_score' => $o->initial_commercial_score === null ? null : (float) $o->initial_commercial_score,
                'outcome' => $o->outcome,
                'reason' => $o->reason,
                'buyer_interviews' => $o->buyer_interviews,
                'confirmed_buyers' => $o->confirmed_buyers,
                'paid_pilots' => $o->paid_pilots,
                'implicates' => OpportunityOutcome::OUTCOME_IMPLICATES[$o->outcome] ?? null,
            ])
            ->values()
            ->all();
    }

    /**
     * §57's Opportunity B: "score = 68, 3 interviews, 2 paid pilots. Result:
     * system underestimated opportunity."
     *
     * Keyed on money rather than on the outcome label. `successful` is a
     * judgement someone typed; a paid pilot is a fact, and this is the half of
     * the loop where being strict costs nothing.
     */
    private function underestimated(Collection $outcomes): array
    {
        return $outcomes
            ->filter(fn ($o) => $o->paid_pilots >= 1 || $o->customers >= 1 || (float) $o->revenue > 0)
            ->filter(fn ($o) => (float) $o->initial_score < 60.0)
            ->sortBy('initial_score')
            ->map(fn ($o) => [
                'opportunity_id' => $o->opportunity_id,
                'title' => $o->opportunity?->title,
                'initial_score' => (float) $o->initial_score,
                'initial_commercial_score' => $o->initial_commercial_score === null ? null : (float) $o->initial_commercial_score,
                'outcome' => $o->outcome,
                'reason' => $o->reason,
                'paid_pilots' => $o->paid_pilots,
                'customers' => $o->customers,
                'revenue' => (float) $o->revenue,
            ])
            ->values()
            ->all();
    }

    private function byOutcome(Collection $outcomes): array
    {
        return collect(OpportunityOutcome::OUTCOMES)
            ->mapWithKeys(function (string $outcome) use ($outcomes) {
                $matching = $outcomes->where('outcome', $outcome);

                return [$outcome => [
                    'count' => $matching->count(),
                    'mean_initial_score' => $matching->isEmpty()
                        ? null
                        : round($matching->avg(fn ($o) => (float) $o->initial_score), 1),
                    'implicates' => OpportunityOutcome::OUTCOME_IMPLICATES[$outcome] ?? null,
                ]];
            })
            ->filter(fn (array $row) => $row['count'] > 0)
            ->all();
    }

    /**
     * Which *dimension* looks mis-weighted.
     *
     * §57 asks for weight adjustment, which needs more than "the score was too
     * high" — it needs to know which of the eleven dimensions carried the score
     * there. So for each dimension, this compares its mean normalized value
     * among overestimated opportunities against the mean among underestimated
     * ones.
     *
     * A dimension that scored high on things that flopped and low on things that
     * worked is doing the opposite of its job. That is the strongest signal
     * available from this data, and it is still only a hint: `support` carries
     * how many rows are behind each figure, and anything under
     * MIN_PATTERN_SUPPORT is reported without a verdict.
     */
    private function dimensionSignals(Collection $outcomes, array $over, array $under): array
    {
        $overIds = collect($over)->pluck('opportunity_id')->all();
        $underIds = collect($under)->pluck('opportunity_id')->all();

        $overRows = $outcomes->whereIn('opportunity_id', $overIds);
        $underRows = $outcomes->whereIn('opportunity_id', $underIds);

        $dimensionValues = function (Collection $rows): array {
            $values = [];
            foreach ($rows as $row) {
                foreach (($row->initial_score_components ?? []) as $block) {
                    if (! is_array($block) || ! isset($block['dimensions'])) {
                        continue;
                    }
                    foreach ($block['dimensions'] as $name => $dimension) {
                        if (! isset($dimension['normalized']) || ! is_numeric($dimension['normalized'])) {
                            continue;
                        }
                        $values[$name][] = (float) $dimension['normalized'];
                    }
                }
            }

            return $values;
        };

        $overValues = $dimensionValues($overRows);
        $underValues = $dimensionValues($underRows);

        $signals = [];

        foreach (array_unique(array_merge(array_keys($overValues), array_keys($underValues))) as $dimension) {
            $overMean = isset($overValues[$dimension]) && $overValues[$dimension] !== []
                ? array_sum($overValues[$dimension]) / count($overValues[$dimension])
                : null;
            $underMean = isset($underValues[$dimension]) && $underValues[$dimension] !== []
                ? array_sum($underValues[$dimension]) / count($underValues[$dimension])
                : null;

            $support = count($overValues[$dimension] ?? []) + count($underValues[$dimension] ?? []);

            $verdict = null;
            if ($overMean !== null && $underMean !== null && $support >= self::MIN_PATTERN_SUPPORT) {
                $gap = $overMean - $underMean;
                if ($gap >= self::MISCALIBRATION_THRESHOLD) {
                    // Scored high on failures, low on successes: actively
                    // misleading, not merely uninformative.
                    $verdict = 'over_weighted';
                } elseif ($gap <= -self::MISCALIBRATION_THRESHOLD) {
                    $verdict = 'under_weighted';
                }
            }

            $signals[$dimension] = [
                'mean_in_overestimated' => $overMean === null ? null : round($overMean, 1),
                'mean_in_underestimated' => $underMean === null ? null : round($underMean, 1),
                'support' => $support,
                'verdict' => $verdict,
                'note' => $support < self::MIN_PATTERN_SUPPORT
                    ? 'Too few examples to read anything into this.'
                    : null,
            ];
        }

        ksort($signals);

        return $signals;
    }

    /**
     * §56's ultimate KPI, per opportunity and in total.
     *
     * Independent of concluded outcomes on purpose: money can arrive from an
     * opportunity nobody has written a conclusion for yet, and the KPI must not
     * wait on paperwork.
     */
    private function revenue(): array
    {
        $rows = OpportunityRevenue::with('opportunity:id,title')->orderBy('id')->get();

        $byOpportunity = $rows
            ->groupBy('opportunity_id')
            ->map(fn (Collection $group) => [
                'opportunity_id' => $group->first()->opportunity_id,
                'title' => $group->first()->opportunity?->title,
                'total' => round($group->sum(fn ($r) => (float) $r->amount), 2),
                'entries' => $group->count(),
                'first_received' => $group->min('received_at')?->toDateString(),
                'distinct_customers' => $group->pluck('company_ref')->filter()->unique()->count(),
            ])
            ->sortByDesc('total')
            ->values()
            ->all();

        return [
            'total' => round($rows->sum(fn ($r) => (float) $r->amount), 2),
            'currency' => 'MYR',
            'entries' => $rows->count(),
            'revenue_generating_opportunities' => count($byOpportunity),
            'by_opportunity' => $byOpportunity,
        ];
    }

    /**
     * What a person might change, phrased as observations rather than orders.
     *
     * Every suggestion carries its support count, and none of them is applied
     * automatically. The wording matters: "consider" and "looks" rather than
     * "reduce" and "is", because with this much data the honest register is
     * tentative and a confident tone would invite exactly the unearned
     * weight-fiddling this whole class exists to discourage.
     */
    private function suggestions(Collection $outcomes, array $over, array $under): array
    {
        $suggestions = [];
        $total = $outcomes->count();

        if ($total < self::MIN_OUTCOMES_TO_CONCLUDE) {
            return [[
                'kind' => 'insufficient_data',
                'support' => $total,
                'text' => sprintf(
                    'Record at least %d outcomes before changing anything in config/scoring.yaml. '
                    .'At %d, a single unusual result moves every average enough to mislead.',
                    self::MIN_OUTCOMES_TO_CONCLUDE,
                    $total,
                ),
            ]];
        }

        // §57's Opportunity A, generalised: which failure reason keeps recurring
        // among things the model rated highly?
        $failureReasons = collect($over)->countBy('outcome')->sortDesc();
        foreach ($failureReasons as $outcome => $count) {
            if ($count < self::MIN_PATTERN_SUPPORT) {
                continue;
            }
            $dimension = OpportunityOutcome::OUTCOME_IMPLICATES[$outcome] ?? null;
            $suggestions[] = [
                'kind' => 'recurring_failure',
                'support' => $count,
                'outcome' => $outcome,
                'implicates' => $dimension,
                'text' => sprintf(
                    '%d highly-scored opportunities ended in %s. That points at %s being too '
                    .'generous — consider whether the dimensions behind it are measuring '
                    .'intent rather than budget.',
                    $count,
                    str_replace('_', ' ', $outcome),
                    $dimension ?? 'the score',
                ),
            ];
        }

        if (count($under) >= self::MIN_PATTERN_SUPPORT) {
            $suggestions[] = [
                'kind' => 'systematic_underestimation',
                'support' => count($under),
                'text' => sprintf(
                    '%d opportunities that produced money scored below 60. The model is '
                    .'missing something these share — read their reasons before adjusting '
                    .'weights, since the fix may be a new dimension rather than a reweighting.',
                    count($under),
                ),
            ];
        }

        $accuracy = $this->accuracy($outcomes);
        if ($accuracy['wasted_effort'] > $accuracy['scored_high_and_worked'] && $total >= self::MIN_OUTCOMES_TO_CONCLUDE) {
            $suggestions[] = [
                'kind' => 'high_scores_unreliable',
                'support' => $accuracy['wasted_effort'],
                'text' => sprintf(
                    'More high-scoring opportunities failed (%d) than succeeded (%d). Raising '
                    .'§35\'s INVESTIGATE threshold would not fix this — the ordering itself is '
                    .'not carrying signal yet.',
                    $accuracy['wasted_effort'],
                    $accuracy['scored_high_and_worked'],
                ),
            ];
        }

        if ($suggestions === []) {
            $suggestions[] = [
                'kind' => 'no_clear_pattern',
                'support' => $total,
                'text' => sprintf(
                    'No consistent miscalibration across %d outcomes. The weights in '
                    .'config/scoring.yaml are not contradicted by what has happened so far.',
                    $total,
                ),
            ];
        }

        return $suggestions;
    }
}
