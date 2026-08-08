<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Opportunity;
use App\Models\ProblemSignal;
use App\Models\TrendMetric;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

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

        // §33's filter list, restricted to the filters that have data behind
        // them. `industry` is omitted deliberately: `industry_id` exists on the
        // table but nothing populates it yet, and a control that silently
        // matches nothing is worse than an absent one — it reads as "no
        // opportunities in retail" rather than "we don't classify industry".
        // The same applies to `commercial stage` beyond `status`, whose
        // supporting CRM tables arrive in Milestone 6 (§21).
        foreach (['status', 'recommendation'] as $filter) {
            if ($request->filled($filter)) {
                $query->where($filter, $request->string($filter));
            }
        }

        if ($request->filled('topic')) {
            $query->whereHas('topic', fn ($q) => $q->where('slug', $request->string('topic')));
        }

        if ($request->filled('buyer')) {
            $query->where('target_buyer', $request->string('buyer'));
        }

        // Confidence floor rather than an exact match: §30's point is that a
        // score means little without its confidence, so the useful question is
        // "show me only what I can believe", not "confidence exactly 61".
        if ($request->filled('min_confidence')) {
            $query->where('confidence_score', '>=', $request->float('min_confidence'));
        }

        if ($request->filled('min_opportunity')) {
            $query->where('opportunity_score', '>=', $request->float('min_opportunity'));
        }

        // `state` and `source` describe the evidence, not the opportunity, so
        // they filter on whether any of the topic's signals came from there.
        if ($request->filled('state')) {
            $state = $request->string('state');
            $query->whereExists(
                fn ($q) => $q->select(DB::raw(1))
                    ->from('problem_signals')
                    ->whereColumn('problem_signals.topic_id', 'opportunities.topic_id')
                    ->where('problem_signals.region', $state)
            );
        }

        if ($request->filled('source')) {
            $source = $request->string('source');
            $query->whereExists(
                fn ($q) => $q->select(DB::raw(1))
                    ->from('problem_signals')
                    ->join('normalized_documents', 'normalized_documents.id', '=', 'problem_signals.document_id')
                    ->join('raw_documents', 'raw_documents.id', '=', 'normalized_documents.raw_document_id')
                    ->join('sources', 'sources.id', '=', 'raw_documents.source_id')
                    ->whereColumn('problem_signals.topic_id', 'opportunities.topic_id')
                    ->where('sources.slug', $source)
            );
        }

        if ($request->filled('since')) {
            $since = $request->date('since');
            $query->whereExists(
                fn ($q) => $q->select(DB::raw(1))
                    ->from('problem_signals')
                    ->whereColumn('problem_signals.topic_id', 'opportunities.topic_id')
                    ->where('problem_signals.signal_date', '>=', $since)
            );
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
                'filters_applied' => $this->appliedFilters($request),
                'filters_not_yet_available' => [
                    'industry' => 'industry_id is unpopulated — no industry classifier exists yet',
                    'commercial_stage' => 'pilots and paying customers arrive with the CRM tables in Milestone 6 (§21)',
                ],
            ],
        ]);
    }

    /**
     * One opportunity, with §34's sections and the full score breakdown that is
     * Milestone 4's acceptance criterion ("Each opportunity is explainable
     * through stored evidence").
     */
    public function show(int $id): JsonResponse
    {
        $opportunity = Opportunity::with('topic:id,slug,name,description')->find($id);

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
                'topic_description' => $opportunity->topic?->description,

                // Every weighted input behind every score, as stored at scoring
                // time — so a number stays explainable even after the weights
                // in config/scoring.yaml have since moved on.
                'score_components' => $opportunity->score_components,

                // §34's evidence sections, each computed from stored rows.
                'evidence' => $this->evidence($opportunity),
                'geography' => $this->geography($opportunity),
                'trend' => $this->trend($opportunity),
                'buyer_evidence' => $this->buyerEvidence($opportunity),
            ]),
            'meta' => [
                'scoring_config_version' => $opportunity->scoring_config_version,
                'scored_at' => $opportunity->scored_at?->toIso8601String(),
                'sections_not_yet_available' => [
                    'customer_interviews' => 'Milestone 6 (§21)',
                    'commercial_evidence' => 'Milestone 6 (§21)',
                    'experiments' => 'Milestone 6 (§21)',
                ],
            ],
        ]);
    }

    /**
     * §34's "Public-text examples", ordered by §31's evidence hierarchy — a
     * signal corroborated by more of its own dimensions ranks above a bare
     * mention. Each example carries its source and date so a reader can judge
     * the evidence rather than trust the score.
     */
    private function evidence(Opportunity $o): array
    {
        $signals = ProblemSignal::query()
            ->where('topic_id', $o->topic_id)
            ->join('normalized_documents', 'normalized_documents.id', '=', 'problem_signals.document_id')
            ->join('raw_documents', 'raw_documents.id', '=', 'normalized_documents.raw_document_id')
            ->join('sources', 'sources.id', '=', 'raw_documents.source_id')
            ->orderByDesc('problem_signals.severity_score')
            ->orderByDesc('problem_signals.signal_date')
            ->limit(10)
            ->get([
                'problem_signals.id',
                'problem_signals.signal_date',
                'problem_signals.severity_score',
                'problem_signals.urgency_score',
                'problem_signals.economic_impact_score',
                'problem_signals.frequency_hint',
                'problem_signals.payer_type',
                'problem_signals.evidence_json',
                'problem_signals.classification_method',
                'problem_signals.region',
                'sources.slug as source_slug',
                'sources.name as source_name',
                'sources.reliability_score',
                'raw_documents.url',
                'raw_documents.title',
                // Excerpt rather than the full body: enough to judge the
                // signal, not a re-publication of someone's post (§42).
                // SUBSTR, not LEFT — LEFT is absent from sqlite, which the test
                // suite runs on (the portability lesson from Milestone 3).
                DB::raw('SUBSTR(normalized_documents.cleaned_text, 1, 400) as excerpt'),
            ]);

        return [
            'signal_count' => ProblemSignal::where('topic_id', $o->topic_id)->count(),
            'distinct_sources' => ProblemSignal::query()
                ->where('topic_id', $o->topic_id)
                ->join('normalized_documents', 'normalized_documents.id', '=', 'problem_signals.document_id')
                ->join('raw_documents', 'raw_documents.id', '=', 'normalized_documents.raw_document_id')
                ->distinct()
                ->count('raw_documents.source_id'),
            'examples' => $signals->map(fn ($s) => [
                'id' => $s->id,
                'date' => $s->signal_date,
                'source' => $s->source_slug,
                'source_name' => $s->source_name,
                'source_reliability' => $s->reliability_score,
                'url' => $s->url,
                'title' => $s->title,
                'excerpt' => $s->excerpt,
                'region' => $s->region ?: null,
                'severity' => $s->severity_score,
                'urgency' => $s->urgency_score,
                'economic_impact' => $s->economic_impact_score,
                'frequency' => $s->frequency_hint,
                'payer_type' => $s->payer_type,
                // How this signal was produced — a keyword match and a model
                // reading the text are different grades of evidence, and §31
                // asks for evidence to be ranked, not blended.
                'method' => $s->classification_method,
                'extraction' => $s->evidence_json,
            ]),
        ];
    }

    /** §34's "Geography" — state distribution of the topic's signals. */
    private function geography(Opportunity $o): array
    {
        return ProblemSignal::query()
            ->where('topic_id', $o->topic_id)
            ->whereNotNull('region')
            ->where('region', '!=', '')
            ->groupBy('region')
            ->orderByDesc(DB::raw('COUNT(*)'))
            ->get(['region', DB::raw('COUNT(*) as signal_count')])
            ->mapWithKeys(fn ($row) => [$row->region => (int) $row->signal_count])
            ->all();
    }

    /**
     * §34's "Trend" — the 7/30/90-day graph, built from the topic's own daily
     * signal counts. Search-interest series live under /trends and are keyed by
     * keyword rather than topic, so they are linked from the topic page instead
     * of merged here; merging two differently-scaled series into one graph is
     * how a chart starts lying.
     */
    private function trend(Opportunity $o): array
    {
        $daily = ProblemSignal::query()
            ->where('topic_id', $o->topic_id)
            ->groupBy('signal_date')
            ->orderBy('signal_date')
            ->get([
                'signal_date',
                DB::raw('COUNT(*) as mentions'),
                DB::raw('AVG(severity_score) as avg_severity'),
            ]);

        return [
            'series' => $daily->map(fn ($row) => [
                'date' => $row->signal_date instanceof \DateTimeInterface
                    ? $row->signal_date->format('Y-m-d')
                    : (string) $row->signal_date,
                'mentions' => (int) $row->mentions,
                'avg_severity' => $row->avg_severity === null ? null : round((float) $row->avg_severity, 1),
            ]),
            'windows' => [
                'mentions_7d' => $this->mentionsWithin($o, 7),
                'mentions_30d' => $this->mentionsWithin($o, 30),
                'mentions_90d' => $this->mentionsWithin($o, 90),
            ],
            'search_interest_available' => TrendMetric::query()->exists(),
        ];
    }

    private function mentionsWithin(Opportunity $o, int $days): int
    {
        return ProblemSignal::query()
            ->where('topic_id', $o->topic_id)
            ->where('signal_date', '>=', now()->subDays($days)->toDateString())
            ->count();
    }

    /**
     * §34's "Buyer" section. §5's distinction matters here: the payer is often
     * not the person suffering the problem, so both are reported rather than
     * collapsed into one "who cares about this" figure.
     */
    private function buyerEvidence(Opportunity $o): array
    {
        $payers = ProblemSignal::query()
            ->where('topic_id', $o->topic_id)
            ->whereNotNull('payer_type')
            ->groupBy('payer_type')
            ->orderByDesc(DB::raw('COUNT(*)'))
            ->get(['payer_type', DB::raw('COUNT(*) as signal_count')])
            ->mapWithKeys(fn ($row) => [$row->payer_type => (int) $row->signal_count])
            ->all();

        return [
            'suggested_buyer' => $o->target_buyer ?? array_key_first($payers),
            'payer_types' => $payers,
            'affected_roles' => ProblemSignal::query()
                ->where('topic_id', $o->topic_id)
                ->whereNotNull('evidence_json')
                ->pluck('evidence_json')
                ->map(fn ($e) => is_array($e) ? ($e['affected_role'] ?? null) : null)
                ->filter()
                ->countBy()
                ->sortDesc()
                ->all(),
        ];
    }

    private function appliedFilters(Request $request): array
    {
        return collect(['status', 'recommendation', 'topic', 'buyer', 'state', 'source', 'since', 'min_confidence', 'min_opportunity'])
            ->filter(fn (string $key) => $request->filled($key))
            ->mapWithKeys(fn (string $key) => [$key => $request->string($key)->toString()])
            ->all();
    }

    private function summarize(Opportunity $o): array
    {
        return [
            'id' => $o->id,
            'title' => $o->title,
            'topic' => $o->topic?->slug,
            'topic_name' => $o->topic?->name,
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
