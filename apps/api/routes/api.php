<?php

use App\Http\Controllers\Api\CommercialValidationController;
use App\Http\Controllers\Api\DashboardController;
use App\Http\Controllers\Api\OpportunityController;
use App\Http\Controllers\Api\OutcomeController;
use App\Http\Controllers\Api\ReportController;
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

    // Commercial validation (PROJECT_SPEC.md §21, §36). The only write endpoints
    // in the project. §52's line is enforced here: recording evidence updates
    // `suggested_status`; only PATCH /stage moves `status`, and only a human
    // calls it.
    Route::prefix('/opportunities/{id}')->whereNumber('id')->group(function () {
        Route::get('/validation', [CommercialValidationController::class, 'show']);
        Route::post('/interviews', [CommercialValidationController::class, 'storeInterview']);
        Route::post('/evidence', [CommercialValidationController::class, 'storeEvidence']);
        Route::post('/experiments', [CommercialValidationController::class, 'storeExperiment']);
        Route::patch('/experiments/{experimentId}', [CommercialValidationController::class, 'updateExperiment'])
            ->whereNumber('experimentId');
        Route::patch('/stage', [CommercialValidationController::class, 'updateStage']);

        // §56's ultimate KPI and §58's outcome dataset. These close §57's loop:
        // everything else measures what the world said; these record what
        // happened when someone went and tried to sell something.
        Route::post('/revenue', [OutcomeController::class, 'storeRevenue']);
        Route::post('/outcome', [OutcomeController::class, 'storeOutcome']);
        // Human-authored fields (§52). The only writer of target_buyer, which
        // §7 Gate 1 requires — the scoring engine never touches these columns.
        Route::patch('/', [CommercialValidationController::class, 'updateNarrative']);
    });

    // Topic pages. Keyed by slug — the stable identifier in config/topics.yaml.
    Route::get('/topics', [TopicController::class, 'index']);
    Route::get('/topics/{slug}', [TopicController::class, 'show']);

    // §58's dataset, §57's feedback loop, §56's metrics.
    Route::get('/outcomes', [OutcomeController::class, 'index']);
    Route::get('/calibration', [OutcomeController::class, 'calibration']);
    Route::get('/metrics', [OutcomeController::class, 'metrics']);

    // Reports and alerts (PROJECT_SPEC.md §36, §39, §40).
    Route::get('/reports', [ReportController::class, 'index']);
    Route::get('/reports/{id}', [ReportController::class, 'show'])->whereNumber('id');
    Route::post('/reports/generate', [ReportController::class, 'generate']);
    // Makes Milestone 7's acceptance criterion checkable rather than asserted.
    Route::get('/reports/{id}/verify', [ReportController::class, 'verify'])->whereNumber('id');
    Route::get('/alerts', [ReportController::class, 'alerts']);

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
