<?php

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
});
