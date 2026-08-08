<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Opportunity;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class OpportunityController extends Controller
{
    /**
     * Ranked opportunities (PROJECT_SPEC.md §33).
     *
     * The dashboard's question is "What should I investigate or sell this
     * week?", so the default ordering is by opportunity score and every row
     * carries its confidence beside it — §30 is explicit that a score without
     * its confidence invites treating a guess as a fact.
     */
    public function index(Request $request): JsonResponse
    {
        $query = Opportunity::query()->with('topic:id,slug,name');

        foreach (['status', 'recommendation'] as $filter) {
            if ($request->filled($filter)) {
                $query->where($filter, $request->string($filter));
            }
        }

        $opportunities = $query
            ->orderByRaw('(opportunity_score IS NULL) ASC, opportunity_score DESC')
            ->limit((int) $request->integer('limit', 50))
            ->get()
            ->map(fn (Opportunity $o) => $this->summarize($o));

        return response()->json([
            'data' => $opportunities,
            'meta' => [
                'count' => $opportunities->count(),
                'scores_are_explainable_at' => '/api/v1/opportunities/{id}',
            ],
        ]);
    }

    /**
     * One opportunity with its full score breakdown — Milestone 4's acceptance
     * criterion ("Each opportunity is explainable through stored evidence").
     */
    public function show(int $id): JsonResponse
    {
        $opportunity = Opportunity::with('topic:id,slug,name')->find($id);

        if ($opportunity === null) {
            return response()->json(['error' => "Unknown opportunity {$id}"], 404);
        }

        return response()->json([
            'data' => array_merge($this->summarize($opportunity), [
                'description' => $opportunity->description,
                'problem_statement' => $opportunity->problem_statement,
                'existing_workaround' => $opportunity->existing_workaround,
                'possible_solution' => $opportunity->possible_solution,
                'monetization_model' => $opportunity->monetization_model,
                'target_buyer' => $opportunity->target_buyer,

                // Every weighted input behind every score, as stored at scoring
                // time — so a number stays explainable even after the weights
                // in config/scoring.yaml have since moved on.
                'score_components' => $opportunity->score_components,
            ]),
            'meta' => [
                'scoring_config_version' => $opportunity->scoring_config_version,
                'scored_at' => $opportunity->scored_at?->toIso8601String(),
            ],
        ]);
    }

    private function summarize(Opportunity $o): array
    {
        return [
            'id' => $o->id,
            'title' => $o->title,
            'topic' => $o->topic?->slug,
            'status' => $o->status,
            'recommendation' => $o->recommendation,
            'pain_score' => $o->pain_score,
            'commercial_score' => $o->commercial_score,
            'opportunity_score' => $o->opportunity_score,
            // §30: confidence always travels with the score it qualifies.
            'confidence_score' => $o->confidence_score,
        ];
    }
}
