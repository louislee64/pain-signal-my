<?php

use App\Http\Controllers\Api\DashboardController;
use App\Http\Controllers\Api\OpportunityController;
use App\Http\Controllers\Api\SourceController;
use App\Http\Controllers\Api\TopicController;
use App\Http\Controllers\Api\TrendController;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Route;

Route::prefix('v1')->group(function () {
    Route::get('/health', function () {
        $databaseOk = true;

        try {
            DB::connection()->getPdo();
        } catch (\Throwable $e) {
            $databaseOk = false;
        }

        $healthy = $databaseOk;

        return response()->json([
            'status' => $healthy ? 'ok' : 'degraded',
            'service' => 'my-pain-radar-api',
            'checks' => [
                'app' => true,
                'database' => $databaseOk,
            ],
            'timestamp' => now()->toIso8601String(),
        ], $healthy ? 200 : 503);
    });

    // Dashboard summary — §33's five cards (PROJECT_SPEC.md §36).
    Route::get('/dashboard', [DashboardController::class, 'index']);

    // Ranked opportunities (PROJECT_SPEC.md §36).
    Route::get('/opportunities', [OpportunityController::class, 'index']);
    Route::get('/opportunities/{id}', [OpportunityController::class, 'show'])->whereNumber('id');

    // Topic pages. Keyed by slug — the stable identifier in config/topics.yaml.
    Route::get('/topics', [TopicController::class, 'index']);
    Route::get('/topics/{slug}', [TopicController::class, 'show']);

    // Source health and ingestion history (PROJECT_SPEC.md §36).
    // `POST /sources/{id}/run` is in §36's list but deliberately absent: it
    // would give the API write access to the collector pipeline, which the
    // Python service owns. Triggering a run is a scheduler concern (§38,
    // Milestone 7), not a dashboard button that hides a long-running job.
    Route::get('/sources', [SourceController::class, 'index']);
    Route::get('/ingestion-runs', [SourceController::class, 'runs']);

    // Trend keyword monitoring (PROJECT_SPEC.md §15B/§16). Not in §36's
    // endpoint list, which predates the trend tables; /trends is the natural
    // REST resource for trend_metrics and §36 mandates REST rather than an
    // exhaustive route inventory.
    Route::get('/trends', [TrendController::class, 'index']);
    Route::get('/trends/{keyword}', [TrendController::class, 'show'])->where('keyword', '.*');
});
