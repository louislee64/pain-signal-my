<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\CommercialEvidence;
use App\Models\CustomerInterview;
use App\Models\Experiment;
use App\Models\Opportunity;
use App\Models\OpportunityStageTransition;
use App\Support\CommercialStage;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Validation\Rule;

/**
 * §36's write endpoints, and the stage promotion they feed.
 *
 * Milestone 6's acceptance criterion is that "a problem can move from internet
 * signal to paid-pilot tracking", so these are the only endpoints in the project
 * that write. Two rules apply to all of them:
 *
 *  1. **Personal data stays out** (§21, §7 Gate 2). No name, email, phone or
 *     company-name field is accepted, and `company_ref` is validated as a short
 *     pseudonymous label. A request that sends extra fields has them dropped by
 *     validation rather than silently stored.
 *  2. **The pipeline never promotes** (§52). Recording evidence updates
 *     `suggested_status`; only an explicit stage request moves `status`, and it
 *     is refused if the gate behind it is not satisfied.
 */
class CommercialValidationController extends Controller
{
    /** §7 Gate 2 — record a real conversation. */
    public function storeInterview(Request $request, int $id): JsonResponse
    {
        $opportunity = Opportunity::find($id);
        if ($opportunity === null) {
            return response()->json(['error' => "Unknown opportunity {$id}"], 404);
        }

        $data = $request->validate([
            // Pseudonymous by contract. Length-capped and pattern-restricted so
            // "Restoran Ali Sdn Bhd (ali@example.com)" cannot be passed off as a
            // reference — the whole personal-data posture of this table depends
            // on this field staying a label.
            'company_ref' => ['nullable', 'string', 'max:64', 'regex:/^[a-z0-9][a-z0-9_-]*$/i'],
            'industry' => ['nullable', 'string', 'max:100'],
            'company_size' => ['nullable', 'string', 'max:50'],
            'respondent_role' => ['nullable', 'string', 'max:100'],

            // Nullable, not defaulted false: "they said no" is a finding worth
            // recording and "we did not establish it" is not the same thing.
            'problem_confirmed' => ['nullable', 'boolean'],

            'frequency_score' => ['nullable', 'integer', 'min:0', 'max:100'],
            'severity_score' => ['nullable', 'integer', 'min:0', 'max:100'],
            'estimated_cost_score' => ['nullable', 'integer', 'min:0', 'max:100'],
            'urgency_score' => ['nullable', 'integer', 'min:0', 'max:100'],

            'existing_solution' => ['nullable', 'string', 'max:2000'],
            'current_workaround' => ['nullable', 'string', 'max:2000'],
            'current_spend_range' => ['nullable', 'string', 'max:100'],
            'existing_budget' => ['nullable', 'string', 'max:100'],
            'willingness_to_pay' => ['nullable', 'string', 'max:100'],
            'pilot_interest' => ['nullable', 'boolean'],
            'notes' => ['nullable', 'string', 'max:5000'],
            'interviewed_at' => ['required', 'date'],
        ]);

        $interview = $opportunity->interviews()->create($data);
        $this->refreshSuggestion($opportunity);

        return response()->json([
            'data' => $interview,
            'meta' => $this->stageMeta($opportunity->fresh()),
        ], 201);
    }

    /** §21 — record a discrete piece of commercial evidence. */
    public function storeEvidence(Request $request, int $id): JsonResponse
    {
        $opportunity = Opportunity::find($id);
        if ($opportunity === null) {
            return response()->json(['error' => "Unknown opportunity {$id}"], 404);
        }

        $data = $request->validate([
            // Enum-validated as well as CHECK-constrained in Postgres. An
            // unrecognised type would be ignored by the scoring engine while
            // looking like recorded evidence in the UI.
            'evidence_type' => ['required', Rule::in(CommercialEvidence::TYPES)],
            'strength' => ['nullable', Rule::in(CommercialEvidence::STRENGTHS)],
            'value' => ['nullable', 'numeric', 'min:0'],
            'currency' => ['nullable', 'string', 'size:3'],
            'company_ref' => ['nullable', 'string', 'max:64', 'regex:/^[a-z0-9][a-z0-9_-]*$/i'],
            'notes' => ['nullable', 'string', 'max:5000'],
            'occurred_at' => ['required', 'date'],
        ]);

        // Money changed hands but nobody said how much: allowed, but worth
        // saying so rather than silently recording a paid pilot with no value,
        // since §29's bonus and Gate 5's repeatability both read these rows.
        $warnings = [];
        if (in_array($data['evidence_type'], CommercialEvidence::PAID_TYPES, true)) {
            if (! isset($data['value'])) {
                $warnings[] = "No `value` recorded for a paid evidence type — the amount is part of the evidence.";
            }
            if (! isset($data['company_ref'])) {
                $warnings[] = 'No `company_ref` recorded — this payment cannot count toward Gate 5 repeatability.';
            }
        }

        $evidence = $opportunity->commercialEvidence()->create($data);
        $this->refreshSuggestion($opportunity);

        return response()->json([
            'data' => $evidence,
            'meta' => $this->stageMeta($opportunity->fresh()) + ['warnings' => $warnings],
        ], 201);
    }

    /** §21 — record an experiment. */
    public function storeExperiment(Request $request, int $id): JsonResponse
    {
        $opportunity = Opportunity::find($id);
        if ($opportunity === null) {
            return response()->json(['error' => "Unknown opportunity {$id}"], 404);
        }

        $data = $request->validate([
            // Both required: an experiment with no stated hypothesis and no
            // stated bar for success cannot fail, so it records effort rather
            // than evidence.
            'hypothesis' => ['required', 'string', 'max:2000'],
            'success_metric' => ['required', 'string', 'max:2000'],
            'experiment_type' => ['required', Rule::in(Experiment::TYPES)],
            'status' => ['nullable', Rule::in(Experiment::STATUSES)],
            'result' => ['nullable', 'string', 'max:5000'],
            'succeeded' => ['nullable', 'boolean'],
            'started_at' => ['nullable', 'date'],
            'completed_at' => ['nullable', 'date'],
        ]);

        // A completed experiment with no result is the shape that turns this
        // table into a to-do list. Refused here rather than in the schema,
        // because `completed` is set by the same request that supplies the
        // result and the check needs both.
        if (($data['status'] ?? 'planned') === 'completed' && blank($data['result'] ?? null)) {
            return response()->json([
                'error' => 'A completed experiment needs a `result`. Otherwise the row records effort, not evidence.',
            ], 422);
        }

        $experiment = $opportunity->experiments()->create($data);

        return response()->json([
            'data' => $experiment,
            'meta' => $this->stageMeta($opportunity->fresh()),
        ], 201);
    }

    /**
     * Update an experiment's outcome.
     *
     * Separate from creation because the useful sequence is plan → run →
     * conclude, and forcing the result to be known at creation time would push
     * people to create the row only afterwards — losing the hypothesis, which is
     * the part worth recording before you know the answer.
     */
    public function updateExperiment(Request $request, int $id, int $experimentId): JsonResponse
    {
        $experiment = Experiment::where('opportunity_id', $id)->find($experimentId);
        if ($experiment === null) {
            return response()->json(['error' => "Unknown experiment {$experimentId}"], 404);
        }

        $data = $request->validate([
            'status' => ['required', Rule::in(Experiment::STATUSES)],
            'result' => ['nullable', 'string', 'max:5000'],
            'succeeded' => ['nullable', 'boolean'],
            'completed_at' => ['nullable', 'date'],
        ]);

        if ($data['status'] === 'completed' && blank($data['result'] ?? $experiment->result)) {
            return response()->json([
                'error' => 'A completed experiment needs a `result`.',
            ], 422);
        }

        $experiment->update($data);

        return response()->json(['data' => $experiment->fresh()]);
    }

    /**
     * Move an opportunity through §3's funnel — §52's human approval step.
     *
     * The only way `status` ever changes. Advances are gate-checked; demotions
     * are not, because deciding something was over-promoted is exactly the
     * correction the funnel must permit, and making it hard would leave stale
     * optimistic stages in place.
     */
    public function updateStage(Request $request, int $id): JsonResponse
    {
        $opportunity = Opportunity::find($id);
        if ($opportunity === null) {
            return response()->json(['error' => "Unknown opportunity {$id}"], 404);
        }

        $data = $request->validate([
            'status' => ['required', Rule::in(CommercialStage::ORDER)],
            'note' => ['nullable', 'string', 'max:2000'],
            // An explicit override for the case where the evidence exists but
            // lives outside this system. Recorded as an override in the
            // transition log rather than silently allowed, so a later reader can
            // see the gate was bypassed and by whose say-so.
            'override_gate' => ['nullable', 'boolean'],
        ]);

        $from = $opportunity->status;
        $to = $data['status'];
        $evidence = $opportunity->evidenceSummary();

        if ($from === $to) {
            return response()->json([
                'error' => "Already at stage '{$to}'.",
            ], 422);
        }

        if (CommercialStage::isAdvance($from, $to)) {
            // Every gate between here and there, not just the destination's.
            // Skipping a stage would otherwise reach a state the engine's own
            // suggestion logic can never produce.
            [$allowed, $reason, $blockedAt] = CommercialStage::gateCheckPath($from, $to, $evidence);

            if (! $allowed && ! ($data['override_gate'] ?? false)) {
                $at = $blockedAt === $to ? '' : " (blocked at '{$blockedAt}')";

                return response()->json([
                    'error' => "Cannot advance to '{$to}'{$at}: {$reason}.",
                    'meta' => [
                        'gate' => $reason,
                        'blocked_at' => $blockedAt,
                        'evidence' => $evidence,
                        'suggested_status' => CommercialStage::suggestFrom($evidence),
                        'override' => 'Send override_gate=true if the evidence exists outside this system. It will be recorded as an override.',
                    ],
                ], 422);
            }

            $overridden = ! $allowed;
        } else {
            $overridden = false;
        }

        $suggested = CommercialStage::suggestFrom($evidence);

        OpportunityStageTransition::create([
            'opportunity_id' => $opportunity->id,
            'from_status' => $from,
            'to_status' => $to,
            'suggested_status_at_time' => $suggested,
            'note' => trim(($data['note'] ?? '').($overridden ? ' [gate overridden]' : '')) ?: null,
            // Frozen, not joined later: the underlying rows keep changing, and
            // the question this answers is "what did we know when we decided".
            'evidence_snapshot' => $evidence,
        ]);

        $opportunity->update([
            'status' => $to,
            'suggested_status' => $suggested,
            'status_changed_at' => now(),
            'status_note' => $data['note'] ?? null,
        ]);

        return response()->json([
            'data' => [
                'status' => $to,
                'previous_status' => $from,
                'gate_overridden' => $overridden,
            ],
            'meta' => $this->stageMeta($opportunity->fresh()),
        ]);
    }

    /**
     * The human-authored fields on an opportunity (§52).
     *
     * These exist because §7 Gate 1 is "record a buyer hypothesis", and nothing
     * else in the system can write one: the scoring engine deliberately never
     * touches these columns, and inferring `target_buyer` from signal payer_type
     * would make Gate 1 pass itself — which is the opposite of what a gate is
     * for. Without this endpoint Gate 1 is unreachable, which is exactly what
     * walking the funnel end to end revealed.
     */
    public function updateNarrative(Request $request, int $id): JsonResponse
    {
        $opportunity = Opportunity::find($id);
        if ($opportunity === null) {
            return response()->json(['error' => "Unknown opportunity {$id}"], 404);
        }

        $data = $request->validate([
            'title' => ['sometimes', 'string', 'max:255'],
            'target_buyer' => ['sometimes', 'nullable', 'string', 'max:100'],
            'problem_statement' => ['sometimes', 'nullable', 'string', 'max:5000'],
            'description' => ['sometimes', 'nullable', 'string', 'max:5000'],
            'existing_workaround' => ['sometimes', 'nullable', 'string', 'max:5000'],
            'possible_solution' => ['sometimes', 'nullable', 'string', 'max:5000'],
            'monetization_model' => ['sometimes', 'nullable', 'string', 'max:255'],
        ]);

        if ($data === []) {
            return response()->json(['error' => 'Nothing to update.'], 422);
        }

        $opportunity->update($data);
        // Recording a buyer hypothesis can satisfy Gate 1, so the suggestion has
        // to be recomputed here as well as on evidence writes.
        $this->refreshSuggestion($opportunity);

        return response()->json([
            'data' => $opportunity->fresh()->only(array_keys($data)),
            'meta' => $this->stageMeta($opportunity->fresh()),
        ]);
    }

    /**
     * Everything recorded against one opportunity, plus where the gates stand.
     *
     * Kept off the main opportunity endpoint: this is a working view for someone
     * doing customer discovery, and folding it into the ranked-list detail
     * response would make every dashboard page load carry it.
     */
    public function show(int $id): JsonResponse
    {
        $opportunity = Opportunity::with(['interviews', 'commercialEvidence', 'experiments', 'stageTransitions'])
            ->find($id);

        if ($opportunity === null) {
            return response()->json(['error' => "Unknown opportunity {$id}"], 404);
        }

        return response()->json([
            'data' => [
                'opportunity_id' => $opportunity->id,
                'title' => $opportunity->title,
                'interviews' => $opportunity->interviews->sortByDesc('interviewed_at')->values(),
                'commercial_evidence' => $opportunity->commercialEvidence->sortByDesc('occurred_at')->values(),
                'experiments' => $opportunity->experiments->sortByDesc('created_at')->values(),
                'transitions' => $opportunity->stageTransitions->sortByDesc('created_at')->values(),
            ],
            'meta' => $this->stageMeta($opportunity),
        ]);
    }

    /**
     * Where each gate stands, as data the UI can render without re-deriving it.
     *
     * Every gate is reported, satisfied or not, with the reason attached. A UI
     * that only received the passing ones could show progress but never show
     * what to go and do next.
     */
    private function stageMeta(Opportunity $opportunity): array
    {
        $evidence = $opportunity->evidenceSummary();
        $suggested = CommercialStage::suggestFrom($evidence);

        $gates = [];
        foreach (CommercialStage::GATED as $stage => $requirement) {
            [$satisfied, $reason] = CommercialStage::gateCheck($stage, $evidence);
            $gates[$stage] = [
                'satisfied' => $satisfied,
                'requirement' => $requirement,
                'blocking_reason' => $satisfied ? null : $reason,
            ];
        }

        return [
            'status' => $opportunity->status,
            'suggested_status' => $suggested,
            // §52 in one field: the engine can suggest ahead of the human, and
            // that gap is information rather than a state to auto-resolve.
            'suggestion_is_ahead' => CommercialStage::isAdvance($opportunity->status, $suggested),
            'stage_order' => CommercialStage::ORDER,
            'stage_labels' => CommercialStage::LABELS,
            'gates' => $gates,
            'evidence' => $evidence,
        ];
    }

    /**
     * Recompute the suggestion after evidence changes.
     *
     * Writes `suggested_status` and never `status`. This is the line §52 draws,
     * and it is the only place in the write path where it could be crossed.
     */
    private function refreshSuggestion(Opportunity $opportunity): void
    {
        $opportunity->update([
            'suggested_status' => $opportunity->fresh()->suggestedStage(),
        ]);
    }
}
