<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Opportunity;
use App\Models\ProblemSignal;
use App\Models\Topic;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

class TopicController extends Controller
{
    /**
     * The configured taxonomy with its observed activity (PROJECT_SPEC.md §36).
     *
     * Every enabled topic appears, including those with zero signals. A topic
     * with no evidence is a real and useful answer — it says the taxonomy
     * covers something the sources are not talking about, which is either a
     * gap in collection or a problem that does not exist. Filtering them out
     * would hide both.
     */
    public function index(Request $request): JsonResponse
    {
        $query = Topic::query()->where('enabled', true)->with('parent:id,slug,name');

        if ($request->boolean('with_signals_only')) {
            $query->whereHas('problemSignals');
        }

        $topics = $query->orderBy('slug')->get();

        $counts = ProblemSignal::query()
            ->groupBy('topic_id')
            ->get([
                'topic_id',
                DB::raw('COUNT(*) as signal_count'),
                DB::raw('MAX(signal_date) as last_seen'),
            ])
            ->keyBy('topic_id');

        $opportunities = Opportunity::query()
            ->whereIn('topic_id', $topics->pluck('id'))
            ->get(['id', 'topic_id', 'opportunity_score', 'confidence_score', 'recommendation'])
            ->keyBy('topic_id');

        return response()->json([
            'data' => $topics->map(function (Topic $topic) use ($counts, $opportunities) {
                $count = $counts->get($topic->id);
                $opportunity = $opportunities->get($topic->id);

                return [
                    'slug' => $topic->slug,
                    'name' => $topic->name,
                    'description' => $topic->description,
                    'parent' => $topic->parent?->slug,
                    'signal_count' => (int) ($count->signal_count ?? 0),
                    'last_seen' => $count->last_seen ?? null,
                    'opportunity_id' => $opportunity?->id,
                    'opportunity_score' => $opportunity?->opportunity_score,
                    'confidence_score' => $opportunity?->confidence_score,
                    'recommendation' => $opportunity?->recommendation,
                ];
            }),
            'meta' => [
                'count' => $topics->count(),
                'topics_are_configured_in' => 'config/topics.yaml',
            ],
        ]);
    }

    /**
     * One topic's page (§55's "topic page").
     *
     * Keyed by slug rather than id: slugs are the stable identifier in
     * config/topics.yaml, and a URL a person can read and type is worth more
     * here than an autoincrement that changes if the taxonomy is resynced into
     * a fresh database.
     */
    public function show(string $slug): JsonResponse
    {
        $topic = Topic::with(['parent:id,slug,name', 'children:id,parent_id,slug,name'])
            ->where('slug', $slug)
            ->first();

        if ($topic === null) {
            return response()->json(['error' => "Unknown topic '{$slug}'"], 404);
        }

        $opportunity = Opportunity::where('topic_id', $topic->id)->first();

        return response()->json([
            'data' => [
                'slug' => $topic->slug,
                'name' => $topic->name,
                'description' => $topic->description,
                'parent' => $topic->parent ? [
                    'slug' => $topic->parent->slug,
                    'name' => $topic->parent->name,
                ] : null,
                'children' => $topic->children->map(fn (Topic $c) => [
                    'slug' => $c->slug,
                    'name' => $c->name,
                ]),

                'opportunity' => $opportunity === null ? null : [
                    'id' => $opportunity->id,
                    'opportunity_score' => $opportunity->opportunity_score,
                    'pain_score' => $opportunity->pain_score,
                    'commercial_score' => $opportunity->commercial_score,
                    'confidence_score' => $opportunity->confidence_score,
                    'recommendation' => $opportunity->recommendation,
                    'status' => $opportunity->status,
                ],

                'activity' => $this->activity($topic),
                'geography' => $this->geography($topic),
                'methods' => $this->methods($topic),
                'recent_signals' => $this->recentSignals($topic),
            ],
            'meta' => [
                'scores_are_explainable_at' => $opportunity
                    ? "/api/v1/opportunities/{$opportunity->id}"
                    : null,
                'scoring_note' => $opportunity === null
                    ? 'No opportunity row yet — run `intelligence score` after signals exist for this topic.'
                    : null,
            ],
        ]);
    }

    private function activity(Topic $topic): array
    {
        $daily = ProblemSignal::query()
            ->where('topic_id', $topic->id)
            ->groupBy('signal_date')
            ->orderBy('signal_date')
            ->get([
                'signal_date',
                DB::raw('COUNT(*) as mentions'),
                DB::raw('AVG(severity_score) as avg_severity'),
                DB::raw('AVG(urgency_score) as avg_urgency'),
            ]);

        return [
            'signal_count' => $daily->sum('mentions'),
            'series' => $daily->map(fn ($row) => [
                'date' => $row->signal_date instanceof \DateTimeInterface
                    ? $row->signal_date->format('Y-m-d')
                    : (string) $row->signal_date,
                'mentions' => (int) $row->mentions,
                'avg_severity' => $row->avg_severity === null ? null : round((float) $row->avg_severity, 1),
                'avg_urgency' => $row->avg_urgency === null ? null : round((float) $row->avg_urgency, 1),
            ]),
        ];
    }

    private function geography(Topic $topic): array
    {
        return ProblemSignal::query()
            ->where('topic_id', $topic->id)
            ->whereNotNull('region')
            ->where('region', '!=', '')
            ->groupBy('region')
            ->orderByDesc(DB::raw('COUNT(*)'))
            ->get(['region', DB::raw('COUNT(*) as signal_count')])
            ->mapWithKeys(fn ($row) => [$row->region => (int) $row->signal_count])
            ->all();
    }

    /**
     * How this topic's signals were produced. Rule-based keyword matching and
     * LLM extraction are different grades of evidence (§31), and a topic whose
     * whole case rests on keyword matches deserves to be read differently from
     * one a model confirmed by reading the text.
     */
    private function methods(Topic $topic): array
    {
        return ProblemSignal::query()
            ->where('topic_id', $topic->id)
            ->groupBy('classification_method')
            ->get(['classification_method', DB::raw('COUNT(*) as signal_count')])
            ->mapWithKeys(fn ($row) => [$row->classification_method => (int) $row->signal_count])
            ->all();
    }

    private function recentSignals(Topic $topic): array
    {
        return ProblemSignal::query()
            ->where('topic_id', $topic->id)
            ->join('normalized_documents', 'normalized_documents.id', '=', 'problem_signals.document_id')
            ->join('raw_documents', 'raw_documents.id', '=', 'normalized_documents.raw_document_id')
            ->join('sources', 'sources.id', '=', 'raw_documents.source_id')
            ->orderByDesc('problem_signals.signal_date')
            ->limit(20)
            ->get([
                'problem_signals.id',
                'problem_signals.signal_date',
                'problem_signals.severity_score',
                'problem_signals.region',
                'problem_signals.classification_method',
                'sources.slug as source_slug',
                'raw_documents.url',
                'raw_documents.title',
                DB::raw('SUBSTR(normalized_documents.cleaned_text, 1, 300) as excerpt'),
            ])
            ->map(fn ($s) => [
                'id' => $s->id,
                'date' => $s->signal_date,
                'source' => $s->source_slug,
                'url' => $s->url,
                'title' => $s->title,
                'excerpt' => $s->excerpt,
                'region' => $s->region ?: null,
                'severity' => $s->severity_score,
                'method' => $s->classification_method,
            ])
            ->all();
    }
}
