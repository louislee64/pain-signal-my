<?php

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

    // Trend keyword monitoring (PROJECT_SPEC.md §15B/§16). Not in §36's
    // endpoint list, which predates the trend tables; /trends is the natural
    // REST resource for trend_metrics and §36 mandates REST rather than an
    // exhaustive route inventory.
    Route::get('/trends', [TrendController::class, 'index']);
    Route::get('/trends/{keyword}', [TrendController::class, 'show'])->where('keyword', '.*');
});
