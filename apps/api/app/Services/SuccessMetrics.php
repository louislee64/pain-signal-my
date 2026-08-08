<?php

namespace App\Services;

use App\Models\AiUsage;
use App\Models\Alert;
use App\Models\CommercialEvidence;
use App\Models\CustomerInterview;
use App\Models\IngestionRun;
use App\Models\NormalizedDocument;
use App\Models\Opportunity;
use App\Models\OpportunityOutcome;
use App\Models\OpportunityRevenue;
use App\Models\ProblemSignal;
use App\Models\RawDocument;
use App\Models\Report;
use App\Models\Source;
use Illuminate\Support\Facades\DB;

/**
 * §56's success metrics.
 *
 * §56 splits them into technical and business, and the split is worth keeping
 * visible rather than flattening into one dashboard of numbers: technical
 * metrics tell you whether the machine is working, business metrics tell you
 * whether the machine is *worth* working. A green technical panel above an empty
 * business panel is the most important state this system can be in, because it
 * means everything runs and nothing has been sold.
 *
 * §54's "avoid vanity analytics" is the constraint. Every metric here answers a
 * question someone would act on; document counts appear only as denominators.
 */
class SuccessMetrics
{
    public function collect(): array
    {
        return [
            'technical' => $this->technical(),
            'business' => $this->business(),
            'revenue' => $this->revenue(),
        ];
    }

    /**
     * §56: collector reliability, data freshness, classification accuracy,
     * duplicate rate, processing cost, report generation reliability.
     */
    private function technical(): array
    {
        $runs = IngestionRun::query()->orderByDesc('started_at')->limit(100)->get();
        $succeeded = $runs->where('status', 'succeeded')->count();

        $normalized = NormalizedDocument::count();
        $duplicates = NormalizedDocument::whereNotNull('duplicate_of_normalized_document_id')->count();

        $classified = DB::table('document_topics')->distinct()->count('document_id');

        $lastSuccessful = Source::where('enabled', true)
            ->whereNotNull('last_successful_sync')
            ->max('last_successful_sync');

        return [
            // Reliability over the last 100 runs, not all time: a collector
            // fixed six months ago should not be permanently penalised, and one
            // that broke yesterday should show it immediately.
            'collector_reliability' => [
                'runs_considered' => $runs->count(),
                'succeeded' => $succeeded,
                'success_rate' => $runs->isEmpty() ? null : round($succeeded / $runs->count() * 100, 1),
                'sources_unhealthy' => Source::where('enabled', true)->get()
                    ->filter(fn (Source $s) => $s->health()['status'] !== 'ok')
                    ->count(),
            ],

            'data_freshness' => [
                'last_successful_sync' => $lastSuccessful,
                'hours_since' => $lastSuccessful === null
                    ? null
                    : round(now()->diffInMinutes($lastSuccessful, true) / 60, 1),
                'signals_last_7_days' => ProblemSignal::where(
                    'signal_date', '>=', now()->subDays(7)->toDateString()
                )->count(),
            ],

            // §56 says "classification accuracy", which cannot be measured
            // without labelled ground truth — the §70 evaluation set is the only
            // labelled data in the project and it covers extraction, not
            // classification. Reporting coverage instead, and saying so, beats
            // reporting a number that sounds like accuracy and is not.
            'classification' => [
                'documents_normalized' => $normalized,
                'documents_classified' => $classified,
                'coverage_percent' => $normalized === 0 ? null : round($classified / $normalized * 100, 1),
                'accuracy_note' => 'Coverage, not accuracy. Accuracy needs labelled ground truth; '
                    .'the §70 evaluation set covers LLM extraction, not rule-based classification.',
            ],

            'duplicate_rate' => [
                'normalized_documents' => $normalized,
                'flagged_duplicates' => $duplicates,
                'percent' => $normalized === 0 ? null : round($duplicates / $normalized * 100, 1),
            ],

            'processing_cost' => [
                'total_usd' => round((float) AiUsage::sum('estimated_cost'), 6),
                'calls' => AiUsage::count(),
                'failed_calls' => AiUsage::where('succeeded', false)->count(),
                'documents_processed' => RawDocument::count(),
                'note' => 'Estimated from published per-token rates, not billed amounts.',
            ],

            'report_generation' => [
                'reports_stored' => Report::count(),
                'latest_period_end' => Report::max('period_end'),
                'alerts_pending_delivery' => Alert::whereNull('delivered_at')->count(),
                'alerts_failed_delivery' => Alert::whereNotNull('delivery_error')->whereNull('delivered_at')->count(),
            ],
        ];
    }

    /**
     * §56: opportunities investigated, interviews completed, problem
     * confirmation rate, proposal rate, paid pilot rate, repeat buyer rate.
     *
     * Every rate carries its numerator and denominator. A "40% confirmation
     * rate" from two interviews and a 40% rate from two hundred are different
     * facts, and a bare percentage makes them look identical.
     */
    private function business(): array
    {
        $investigated = Opportunity::where('status', '!=', 'observed')->count();
        $interviews = CustomerInterview::count();
        $confirmed = CustomerInterview::where('problem_confirmed', true)->count();

        $proposals = CommercialEvidence::where('evidence_type', 'proposal')->count();
        $paidPilots = CommercialEvidence::where('evidence_type', 'paid_pilot')->count();

        $payingBusinesses = CommercialEvidence::whereIn('evidence_type', CommercialEvidence::PAID_TYPES)
            ->whereNotNull('company_ref')
            ->distinct()
            ->count('company_ref');

        $repeatBuyers = CommercialEvidence::whereIn('evidence_type', CommercialEvidence::PAID_TYPES)
            ->whereNotNull('company_ref')
            ->select('company_ref')
            ->groupBy('company_ref')
            ->havingRaw('COUNT(*) > 1')
            ->get()
            ->count();

        return [
            'opportunities_investigated' => [
                'value' => $investigated,
                'of_total' => Opportunity::count(),
            ],
            'customer_interviews_completed' => ['value' => $interviews],
            'problem_confirmation_rate' => $this->rate($confirmed, $interviews, 'confirmed interviews'),
            'proposal_rate' => $this->rate($proposals, $investigated, 'proposals per investigated opportunity'),
            'paid_pilot_rate' => $this->rate($paidPilots, $investigated, 'paid pilots per investigated opportunity'),
            'repeat_buyer_rate' => $this->rate($repeatBuyers, $payingBusinesses, 'businesses that paid more than once'),
            'outcomes_concluded' => [
                'value' => OpportunityOutcome::count(),
                'positive' => OpportunityOutcome::whereIn('outcome', OpportunityOutcome::POSITIVE_OUTCOMES)->count(),
            ],
        ];
    }

    /** §56's ultimate KPI. */
    private function revenue(): array
    {
        $total = (float) OpportunityRevenue::sum('amount');

        return [
            'opportunity_generated_revenue' => round($total, 2),
            'currency' => 'MYR',
            'entries' => OpportunityRevenue::count(),
            'revenue_generating_opportunities' => OpportunityRevenue::distinct()->count('opportunity_id'),
            'paying_businesses' => OpportunityRevenue::whereNotNull('company_ref')
                ->distinct()->count('company_ref'),
            // §56's actual question, restated so nobody mistakes the number for
            // an answer to a different one.
            'answers' => 'Did the intelligence system actually help create revenue?',
        ];
    }

    /**
     * A rate with its own arithmetic attached.
     *
     * `null` rather than 0 when the denominator is zero: "no interviews yet" and
     * "interviews happened and none confirmed" are different facts, and a 0%
     * displayed for the first is a claim about work that has not been done.
     */
    private function rate(int $numerator, int $denominator, string $label): array
    {
        return [
            'numerator' => $numerator,
            'denominator' => $denominator,
            'percent' => $denominator === 0 ? null : round($numerator / $denominator * 100, 1),
            'label' => $label,
        ];
    }
}
