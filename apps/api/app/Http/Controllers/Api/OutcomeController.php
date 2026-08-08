<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Opportunity;
use App\Models\OpportunityOutcome;
use App\Models\OpportunityRevenue;
use App\Services\CalibrationAnalyser;
use App\Services\SuccessMetrics;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;

/**
 * §56's revenue, §58's outcome dataset, and §57's calibration report.
 *
 * Milestone 8's work is mostly the developer's — going and talking to real
 * businesses — so this exists to make recording what they learn cheap enough
 * that it actually happens.
 */
class OutcomeController extends Controller
{
    /**
     * Conclude an opportunity (§58).
     *
     * The scores are snapshotted from the opportunity **at the moment of
     * conclusion** rather than supplied by the caller, and this is the decision
     * the whole dataset rests on. Letting a caller pass `initial_score` would
     * make the dataset unfalsifiable — someone reconstructing it later would
     * type in whatever the score is now, which has already been dragged toward
     * the answer by the evidence they recorded along the way.
     *
     * It is still an imperfect proxy: ideally the score would be frozen when the
     * developer first decided to investigate. That is what `--at-stage-change`
     * in the CLI approximates, and the honest limitation is documented.
     */
    public function storeOutcome(Request $request, int $id): JsonResponse
    {
        $opportunity = Opportunity::with('outcome')->find($id);
        if ($opportunity === null) {
            return response()->json(['error' => "Unknown opportunity {$id}"], 404);
        }

        $data = $request->validate([
            'outcome' => ['required', Rule::in(OpportunityOutcome::OUTCOMES)],
            // Required in practice though nullable in the schema: §58's nine
            // categories cannot hold the thing that actually happened, and a
            // year later the reason is the part worth reading.
            'reason' => ['required', 'string', 'max:2000'],
            'concluded_at' => ['required', 'date'],

            // Optional overrides for the counted fields. Defaulted from recorded
            // evidence below, because re-typing numbers the system already knows
            // is how they end up wrong.
            'buyer_interviews' => ['nullable', 'integer', 'min:0'],
            'confirmed_buyers' => ['nullable', 'integer', 'min:0'],
            'proposals_sent' => ['nullable', 'integer', 'min:0'],
            'paid_pilots' => ['nullable', 'integer', 'min:0'],
            'customers' => ['nullable', 'integer', 'min:0'],
        ]);

        $evidence = $opportunity->evidenceSummary();
        $recordedRevenue = OpportunityRevenue::where('opportunity_id', $opportunity->id)
            ->sum('amount');

        $attributes = [
            // Snapshotted, never joined later — see the note above.
            'initial_score' => $opportunity->opportunity_score,
            'initial_pain_score' => $opportunity->pain_score,
            'initial_commercial_score' => $opportunity->commercial_score,
            'initial_confidence_score' => $opportunity->confidence_score,
            'initial_score_components' => $opportunity->score_components,
            'scoring_config_version' => $opportunity->scoring_config_version,

            'buyer_interviews' => $data['buyer_interviews'] ?? $evidence['interview_count'],
            'confirmed_buyers' => $data['confirmed_buyers'] ?? $evidence['independent_confirmations'],
            'proposals_sent' => $data['proposals_sent'] ?? $opportunity->commercialEvidence
                ->where('evidence_type', 'proposal')->count(),
            'paid_pilots' => $data['paid_pilots'] ?? $evidence['paid_pilot_count'],
            'customers' => $data['customers'] ?? $evidence['paying_business_count'],
            'revenue' => $recordedRevenue,

            'outcome' => $data['outcome'],
            'reason' => $data['reason'],
            'concluded_at' => $data['concluded_at'],
        ];

        // One outcome per opportunity: concluding twice means the first
        // conclusion was wrong, which is an edit rather than a second row.
        $outcome = OpportunityOutcome::updateOrCreate(
            ['opportunity_id' => $opportunity->id],
            $attributes,
        );

        $warnings = [];
        if ($opportunity->opportunity_score === null) {
            $warnings[] = 'This opportunity has no score, so it contributes nothing to calibration. '
                .'Run `intelligence score` before concluding.';
        }
        if ($outcome->buyer_interviews === 0 && ! $outcome->isPositive()) {
            // A negative outcome with no conversations behind it says nothing
            // about the model — it says nobody tried.
            $warnings[] = 'No interviews recorded. A negative outcome with no customer contact '
                .'reflects effort, not the scoring model, and calibration ignores it.';
        }

        return response()->json([
            'data' => $outcome->fresh(),
            'meta' => ['warnings' => $warnings],
        ], 201);
    }

    /** §56 — record money actually received. */
    public function storeRevenue(Request $request, int $id): JsonResponse
    {
        $opportunity = Opportunity::find($id);
        if ($opportunity === null) {
            return response()->json(['error' => "Unknown opportunity {$id}"], 404);
        }

        $data = $request->validate([
            'revenue_type' => ['required', Rule::in(OpportunityRevenue::TYPES)],
            // Non-zero rather than positive: a refund or correction is a
            // negative row, and a zero row is only ever a mistake.
            'amount' => ['required', 'numeric', 'not_in:0'],
            'currency' => ['nullable', 'string', 'size:3'],
            'customer_type' => ['nullable', 'string', 'max:100'],
            // Pseudonymous, same contract as everywhere else (§21).
            'company_ref' => ['nullable', 'string', 'max:64', 'regex:/^[a-z0-9][a-z0-9_-]*$/i'],
            'notes' => ['nullable', 'string', 'max:2000'],
            'received_at' => ['required', 'date'],
        ]);

        $revenue = $opportunity->revenue()->create($data);

        // Revenue arriving after an outcome was concluded must update it, or the
        // dataset would permanently understate what the opportunity earned.
        $opportunity->outcome?->update([
            'revenue' => OpportunityRevenue::where('opportunity_id', $opportunity->id)->sum('amount'),
        ]);

        return response()->json([
            'data' => $revenue,
            'meta' => [
                'opportunity_total' => round(
                    (float) OpportunityRevenue::where('opportunity_id', $opportunity->id)->sum('amount'),
                    2
                ),
            ],
        ], 201);
    }

    /** §58's dataset, as recorded. */
    public function index(Request $request): JsonResponse
    {
        $outcomes = OpportunityOutcome::with('opportunity:id,title')
            ->when($request->filled('outcome'), fn ($q) => $q->where('outcome', $request->string('outcome')))
            ->orderByDesc('concluded_at')
            ->orderByDesc('id')
            ->get();

        return response()->json([
            'data' => $outcomes->map(fn (OpportunityOutcome $o) => [
                'opportunity_id' => $o->opportunity_id,
                'title' => $o->opportunity?->title,
                'initial_score' => $o->initial_score === null ? null : (float) $o->initial_score,
                'initial_commercial_score' => $o->initial_commercial_score === null ? null : (float) $o->initial_commercial_score,
                'outcome' => $o->outcome,
                'reason' => $o->reason,
                'buyer_interviews' => $o->buyer_interviews,
                'confirmed_buyers' => $o->confirmed_buyers,
                'proposals_sent' => $o->proposals_sent,
                'paid_pilots' => $o->paid_pilots,
                'customers' => $o->customers,
                'revenue' => (float) $o->revenue,
                'concluded_at' => $o->concluded_at?->toDateString(),
                'scoring_config_version' => $o->scoring_config_version,
            ]),
            'meta' => [
                'count' => $outcomes->count(),
                'outcomes' => OpportunityOutcome::OUTCOMES,
                'calibration_at' => '/api/v1/calibration',
            ],
        ]);
    }

    /** §57's feedback loop. */
    public function calibration(CalibrationAnalyser $analyser): JsonResponse
    {
        $report = $analyser->analyse();

        return response()->json([
            'data' => $report,
            'meta' => [
                // Stated in the response rather than only in the docs, because
                // an API consumer is exactly who would otherwise write the
                // auto-tuning loop this is designed to prevent.
                'note' => 'This report never edits config/scoring.yaml. §52 applies with more '
                    .'force here than anywhere: auto-tuning weights would let a handful of '
                    .'outcomes silently rewrite the model that ranks everything.',
            ],
        ]);
    }

    /** §56's success metrics. */
    public function metrics(SuccessMetrics $metrics): JsonResponse
    {
        return response()->json([
            'data' => $metrics->collect(),
            'meta' => ['ultimate_kpi' => 'opportunity_generated_revenue'],
        ]);
    }
}
