<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\IngestionRun;
use App\Models\Source;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

class SourceController extends Controller
{
    /**
     * Source health (§55's "source health", §36's GET /sources).
     *
     * The question this page answers is "can I trust today's numbers?" — which
     * means it has to surface the ways a source can be quietly broken, not just
     * report a green tick per row. A collector that succeeded but returned zero
     * records, or one that has not run in a week, produces no error anywhere and
     * silently drains every score that depended on it.
     */
    public function index(Request $request): JsonResponse
    {
        $query = Source::query()->withCount('rawDocuments');

        if (! $request->boolean('include_disabled')) {
            $query->where('enabled', true);
        }

        $sources = $query->orderBy('slug')->get();

        $lastRuns = IngestionRun::query()
            ->whereIn('source_id', $sources->pluck('id'))
            ->orderByDesc('started_at')
            ->get()
            ->groupBy('source_id')
            ->map(fn ($runs) => $runs->first());

        return response()->json([
            'data' => $sources->map(function (Source $source) use ($lastRuns) {
                $last = $lastRuns->get($source->id);

                return [
                    'slug' => $source->slug,
                    'name' => $source->name,
                    'source_type' => $source->source_type,
                    'collector' => $source->collector,
                    'collection_method' => $source->collection_method,
                    'enabled' => $source->enabled,

                    // §11/§42 compliance posture travels with the source, so a
                    // reader can see whether the evidence is usable as well as
                    // whether it arrived.
                    'terms_status' => $source->terms_status,
                    'personal_data_risk' => $source->personal_data_risk,
                    'license' => $source->license,
                    'reliability_score' => $source->reliability_score,

                    'documents' => $source->raw_documents_count,
                    'last_run' => $last === null ? null : [
                        'status' => $last->status,
                        'started_at' => $last->started_at?->toIso8601String(),
                        'finished_at' => $last->finished_at?->toIso8601String(),
                        'received' => $last->records_received,
                        'inserted' => $last->records_inserted,
                        'updated' => $last->records_updated,
                        'rejected' => $last->records_rejected,
                        'errors' => $last->error_count,
                    ],
                    // Shared with the dashboard's collection block via the model,
                    // so the two pages can never disagree about a source.
                    'health' => $source->health($last),
                ];
            }),
            'meta' => [
                'count' => $sources->count(),
                'sources_are_configured_in' => 'config/sources.yaml',
            ],
        ]);
    }

    /**
     * Recent ingestion runs across all sources (§36's GET /ingestion-runs).
     *
     * The per-source view above answers "is this source healthy now"; this one
     * answers "what changed and when", which is the question you actually have
     * when a number moved and you need to know whether the data moved with it.
     */
    public function runs(Request $request): JsonResponse
    {
        $query = IngestionRun::query()->with('source:id,slug,name');

        if ($request->filled('source')) {
            $query->whereHas('source', fn ($q) => $q->where('slug', $request->string('source')));
        }

        if ($request->filled('status')) {
            $query->where('status', $request->string('status'));
        }

        $runs = $query
            ->orderByDesc('started_at')
            ->limit((int) $request->integer('limit', 50))
            ->get();

        return response()->json([
            'data' => $runs->map(fn (IngestionRun $run) => [
                'id' => $run->id,
                'source' => $run->source?->slug,
                'status' => $run->status,
                'started_at' => $run->started_at?->toIso8601String(),
                'finished_at' => $run->finished_at?->toIso8601String(),
                'duration_seconds' => $run->started_at && $run->finished_at
                    ? $run->finished_at->diffInSeconds($run->started_at, true)
                    : null,
                'received' => $run->records_received,
                'inserted' => $run->records_inserted,
                'updated' => $run->records_updated,
                'rejected' => $run->records_rejected,
                'errors' => $run->error_count,
                'metadata' => $run->metadata_json,
            ]),
            'meta' => ['count' => $runs->count()],
        ]);
    }

}
