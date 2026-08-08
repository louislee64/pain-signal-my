<?php

namespace App\Services;

use App\Models\Alert;
use App\Models\CommercialEvidence;
use App\Models\Opportunity;
use App\Models\ProblemSignal;
use App\Models\Source;
use App\Models\TrendMetric;
use App\Support\CommercialStage;
use Illuminate\Support\Facades\DB;

/**
 * §40's alert conditions, evaluated against stored data.
 *
 * The hard part of §40 is not detecting the conditions — most are a query — it is
 * that they are *standing facts* rather than events. "Opportunity reaches
 * SELL_PILOT" stays true for as long as the recommendation holds, so a scheduled
 * evaluation naively implemented re-fires it every night. A channel that repeats
 * itself daily gets muted within a week, and then the one alert that mattered
 * goes unread.
 *
 * So every rule produces a `dedupe_key` encoding the condition plus whatever
 * makes this instance distinct. The key is unique in the database, which means
 * "have we already said this?" is answered by an insert failing rather than by a
 * query that could race with a concurrent run.
 *
 * Detection is separate from delivery. This class only writes `alerts` rows;
 * `NotifyAlerts` sends them. An alert that was detected but failed to send is a
 * different state from one never detected, and only the first should be retried.
 */
class AlertDetector
{
    /**
     * Score movement worth interrupting someone for.
     *
     * §40 says "increases significantly" without a number. 10 points is a
     * judgement: on a 0–100 scale it is roughly the difference between two
     * adjacent §35 recommendation bands, so it tends to coincide with a change in
     * what you would actually do.
     */
    public const SIGNIFICANT_SCORE_INCREASE = 10.0;

    public const TOP_N = 10;

    /** Z-score beyond which a trend reading counts as a §40 "major anomaly". */
    public const TREND_ANOMALY_Z = 2.5;

    /** Distinct sources on a new topic that make it "multiple independent". */
    public const INDEPENDENT_SOURCE_THRESHOLD = 2;

    /**
     * Evaluate every rule and record what is newly true.
     *
     * @return array{detected: list<Alert>, skipped_duplicates: int}
     */
    public function detect(): array
    {
        $candidates = array_merge(
            $this->scoreIncreases(),
            $this->newEntrantsToTop10(),
            $this->trendAnomalies(),
            $this->multiSourceNewIssues(),
            $this->newCommercialEvidence(),
            $this->recommendationMilestones(),
        );

        $detected = [];
        $duplicates = 0;

        foreach ($candidates as $candidate) {
            // firstOrCreate on the unique dedupe_key: "already said" is settled by
            // the database, not by a read that a concurrent run could interleave
            // with.
            $alert = Alert::firstOrCreate(
                ['dedupe_key' => $candidate['dedupe_key']],
                $candidate + ['detected_at' => now()],
            );

            if ($alert->wasRecentlyCreated) {
                $detected[] = $alert;
            } else {
                $duplicates++;
            }
        }

        return ['detected' => $detected, 'skipped_duplicates' => $duplicates];
    }

    // ------------------------------------------------------------------- rules

    /**
     * §40: "Opportunity score increases significantly."
     *
     * Compared against the score at the last alert for this opportunity rather
     * than against a fixed baseline, so a topic climbing 8 points a week does
     * eventually alert — but only once per 10-point band rather than every week.
     * The band is baked into the dedupe key.
     */
    private function scoreIncreases(): array
    {
        $alerts = [];

        $previous = Alert::query()
            ->where('alert_type', 'score_increase')
            ->whereNotNull('opportunity_id')
            ->orderBy('id')
            ->get()
            ->groupBy('opportunity_id')
            ->map(fn ($group) => (float) ($group->last()->context['score'] ?? 0));

        $opportunities = Opportunity::with('topic:id,slug,name')
            ->whereNotNull('opportunity_score')
            ->orderBy('id')
            ->get();

        foreach ($opportunities as $opportunity) {
            $score = (float) $opportunity->opportunity_score;
            $baseline = $previous->get($opportunity->id);

            if ($baseline === null) {
                // No prior alert: the baseline is the band the score currently
                // sits in, so an opportunity that has always been at 80 does not
                // alert as though it just got there.
                continue;
            }

            if ($score - $baseline < self::SIGNIFICANT_SCORE_INCREASE) {
                continue;
            }

            $band = (int) floor($score / self::SIGNIFICANT_SCORE_INCREASE);

            $alerts[] = [
                'alert_type' => 'score_increase',
                'severity' => 'info',
                'opportunity_id' => $opportunity->id,
                'title' => "{$opportunity->title}: opportunity score up to ".number_format($score, 0),
                'body' => sprintf(
                    "Opportunity score moved from %s to %s (confidence %s).\nRecommendation: %s. Stage: %s.",
                    number_format($baseline, 0),
                    number_format($score, 0),
                    $opportunity->confidence_score === null ? '—' : number_format((float) $opportunity->confidence_score, 0),
                    $opportunity->recommendation ?? 'none',
                    CommercialStage::LABELS[$opportunity->status] ?? $opportunity->status,
                ),
                'context' => [
                    'score' => $score,
                    'previous_score' => $baseline,
                    'confidence' => $opportunity->confidence_score === null ? null : (float) $opportunity->confidence_score,
                ],
                'dedupe_key' => "score_increase:{$opportunity->id}:band{$band}",
            ];
        }

        // Seed a baseline for opportunities that have never alerted, so the
        // *next* significant rise is detectable. Recorded as delivered so it
        // never gets sent — it is bookkeeping, not news.
        foreach ($opportunities as $opportunity) {
            if ($previous->has($opportunity->id)) {
                continue;
            }
            Alert::firstOrCreate(
                ['dedupe_key' => "score_increase:{$opportunity->id}:baseline"],
                [
                    'alert_type' => 'score_increase',
                    'severity' => 'info',
                    'opportunity_id' => $opportunity->id,
                    'title' => "Baseline recorded for {$opportunity->title}",
                    'body' => 'Initial score recorded so future increases can be measured. Not sent.',
                    'context' => ['score' => (float) $opportunity->opportunity_score, 'baseline' => true],
                    'detected_at' => now(),
                    'delivered_at' => now(),
                    'delivered_via' => 'suppressed:baseline',
                ]
            );
        }

        return $alerts;
    }

    /** §40: "New topic enters Top 10." */
    private function newEntrantsToTop10(): array
    {
        $top = Opportunity::with('topic:id,slug,name')
            ->whereNotNull('opportunity_score')
            ->orderByDesc('opportunity_score')
            ->orderBy('id')
            ->limit(self::TOP_N)
            ->get();

        $alerts = [];

        foreach ($top as $rank => $opportunity) {
            $alerts[] = [
                'alert_type' => 'top10_entry',
                'severity' => 'info',
                'opportunity_id' => $opportunity->id,
                'title' => "{$opportunity->title} is in the top ".self::TOP_N,
                'body' => sprintf(
                    'Ranked #%d at opportunity score %s (confidence %s).',
                    $rank + 1,
                    number_format((float) $opportunity->opportunity_score, 0),
                    $opportunity->confidence_score === null ? '—' : number_format((float) $opportunity->confidence_score, 0),
                ),
                'context' => [
                    'rank' => $rank + 1,
                    'score' => (float) $opportunity->opportunity_score,
                ],
                // Keyed on the opportunity alone, not the rank: shuffling from #7
                // to #6 is not news, and including the rank would alert on every
                // reordering.
                'dedupe_key' => "top10_entry:{$opportunity->id}",
            ];
        }

        return $alerts;
    }

    /** §40: "Major trend anomaly detected." */
    private function trendAnomalies(): array
    {
        $rows = TrendMetric::query()
            ->join('keywords', 'keywords.id', '=', 'trend_metrics.keyword_id')
            ->whereNotNull('trend_metrics.z_score')
            ->whereRaw('ABS(trend_metrics.z_score) >= ?', [self::TREND_ANOMALY_Z])
            ->orderBy('trend_metrics.date')
            ->orderBy('trend_metrics.id')
            ->get([
                'trend_metrics.id',
                'trend_metrics.date',
                'trend_metrics.z_score',
                'trend_metrics.interest',
                'keywords.keyword',
                'keywords.keyword_group',
            ]);

        return $rows->map(fn ($row) => [
            'alert_type' => 'trend_anomaly',
            'severity' => 'info',
            'opportunity_id' => null,
            'title' => "Search anomaly: {$row->keyword}",
            'body' => sprintf(
                "Interest %d on %s, z-score %s against its own 90-day baseline (group: %s).\n"
                .'Relative interest, never absolute volume (§16).',
                $row->interest,
                (string) $row->date,
                number_format((float) $row->z_score, 2),
                $row->keyword_group,
            ),
            'context' => [
                'keyword' => $row->keyword,
                'date' => (string) $row->date,
                'z_score' => (float) $row->z_score,
                'interest' => (int) $row->interest,
            ],
            // Per keyword per date: the same spike must not re-alert, but a fresh
            // spike next week must.
            'dedupe_key' => "trend_anomaly:{$row->keyword}:{$row->date}",
        ])->all();
    }

    /**
     * §40: "Multiple independent sources mention same new issue."
     *
     * Both halves matter. `new` is a first-seen date inside the last 14 days;
     * `independent` is distinct *sources*, not documents — §31 is explicit that
     * one chatty forum is not corroboration.
     */
    private function multiSourceNewIssues(): array
    {
        $since = now()->subDays(14)->toDateString();

        $rows = ProblemSignal::query()
            ->join('normalized_documents', 'normalized_documents.id', '=', 'problem_signals.document_id')
            ->join('raw_documents', 'raw_documents.id', '=', 'normalized_documents.raw_document_id')
            ->select(
                'problem_signals.topic_id',
                DB::raw('MIN(problem_signals.signal_date) as first_seen'),
                DB::raw('COUNT(DISTINCT raw_documents.source_id) as source_count'),
                DB::raw('COUNT(*) as signal_count'),
            )
            ->groupBy('problem_signals.topic_id')
            ->havingRaw('MIN(problem_signals.signal_date) >= ?', [$since])
            ->havingRaw('COUNT(DISTINCT raw_documents.source_id) >= ?', [self::INDEPENDENT_SOURCE_THRESHOLD])
            ->get();

        if ($rows->isEmpty()) {
            return [];
        }

        $opportunities = Opportunity::with('topic:id,slug,name')
            ->whereIn('topic_id', $rows->pluck('topic_id'))
            ->get()
            ->keyBy('topic_id');

        return $rows->map(function ($row) use ($opportunities) {
            $opportunity = $opportunities->get($row->topic_id);
            $title = $opportunity?->title ?? "topic {$row->topic_id}";

            return [
                'alert_type' => 'corroborated_new_issue',
                'severity' => 'warning',
                'opportunity_id' => $opportunity?->id,
                'title' => "New issue corroborated across {$row->source_count} sources: {$title}",
                'body' => sprintf(
                    'First seen %s. %d signals from %d independent sources — §31 ranks that '
                    .'well above the same volume from one source.',
                    (string) $row->first_seen,
                    $row->signal_count,
                    $row->source_count,
                ),
                'context' => [
                    'first_seen' => (string) $row->first_seen,
                    'source_count' => (int) $row->source_count,
                    'signal_count' => (int) $row->signal_count,
                ],
                'dedupe_key' => "corroborated_new_issue:{$row->topic_id}:{$row->first_seen}",
            ];
        })->all();
    }

    /** §40: "Commercial evidence added." */
    private function newCommercialEvidence(): array
    {
        return CommercialEvidence::with('opportunity:id,title')
            ->orderBy('id')
            ->get()
            ->map(function (CommercialEvidence $evidence) {
                $isPaid = in_array($evidence->evidence_type, CommercialEvidence::PAID_TYPES, true);

                return [
                    'alert_type' => 'commercial_evidence',
                    // Money is the thing worth waking up for. §7 Gate 4: a
                    // payment is "considerably more valuable than 'I would
                    // probably use this'".
                    'severity' => $isPaid ? 'critical' : 'info',
                    'opportunity_id' => $evidence->opportunity_id,
                    'title' => sprintf(
                        '%s: %s recorded',
                        $evidence->opportunity?->title ?? 'Unknown opportunity',
                        str_replace('_', ' ', $evidence->evidence_type),
                    ),
                    'body' => sprintf(
                        "%s (%s strength)%s from %s on %s.%s",
                        str_replace('_', ' ', ucfirst($evidence->evidence_type)),
                        $evidence->strength,
                        $evidence->value === null ? '' : ', '.$evidence->currency.' '.number_format((float) $evidence->value, 2),
                        $evidence->company_ref ?? 'an unattributed business',
                        $evidence->occurred_at?->toDateString() ?? 'an unrecorded date',
                        $isPaid ? "\n\nThis is money changing hands — §29's 79-point cap no longer applies once rescored." : '',
                    ),
                    'context' => [
                        'evidence_type' => $evidence->evidence_type,
                        'value' => $evidence->value === null ? null : (float) $evidence->value,
                        'company_ref' => $evidence->company_ref,
                        'is_paid' => $isPaid,
                    ],
                    'dedupe_key' => "commercial_evidence:{$evidence->id}",
                ];
            })
            ->all();
    }

    /** §40: "Opportunity reaches SELL_PILOT" / "reaches PRODUCTIZE". */
    private function recommendationMilestones(): array
    {
        return Opportunity::with('topic:id,slug,name')
            ->whereIn('recommendation', ['SELL_PILOT', 'PRODUCTIZE'])
            ->orderBy('id')
            ->get()
            ->map(fn (Opportunity $o) => [
                'alert_type' => 'recommendation_milestone',
                'severity' => $o->recommendation === 'PRODUCTIZE' ? 'critical' : 'warning',
                'opportunity_id' => $o->id,
                'title' => "{$o->title} reached {$o->recommendation}",
                'body' => sprintf(
                    "Opportunity %s at confidence %s. Commercial stage: %s.\n\n%s",
                    number_format((float) $o->opportunity_score, 0),
                    $o->confidence_score === null ? '—' : number_format((float) $o->confidence_score, 0),
                    CommercialStage::LABELS[$o->status] ?? $o->status,
                    $o->recommendation === 'PRODUCTIZE'
                        ? 'Repeatability is established (§7 Gate 5) — this is the point at which major investment is licensed.'
                        : 'The evidence supports asking for money. §35 suggests it; the decision is yours (§52).',
                ),
                'context' => [
                    'recommendation' => $o->recommendation,
                    'score' => (float) $o->opportunity_score,
                    'stage' => $o->status,
                ],
                // Keyed on the recommendation too, so an opportunity that later
                // reaches PRODUCTIZE alerts again rather than being suppressed by
                // its earlier SELL_PILOT.
                'dedupe_key' => "recommendation_milestone:{$o->id}:{$o->recommendation}",
            ])
            ->all();
    }

    /**
     * Alerts detected but not yet delivered, oldest first.
     *
     * Ordered oldest-first deliberately: if delivery has been broken for a while,
     * the backlog should arrive in the order it happened rather than newest-first,
     * which would tell the story backwards.
     */
    public function pending()
    {
        return Alert::with('opportunity:id,title')
            ->whereNull('delivered_at')
            ->orderBy('detected_at')
            ->orderBy('id')
            ->get();
    }
}
