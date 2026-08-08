<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Keyword;
use App\Models\TrendMetric;
use Illuminate\Http\JsonResponse;
use Illuminate\Support\Facades\DB;

class TrendController extends Controller
{
    /**
     * Google Trends values are relative interest (0-100) scaled within a single
     * collection, never absolute search volume (PROJECT_SPEC.md §16). Every
     * response repeats this so a consumer cannot lose the caveat on the way to
     * a dashboard or report.
     */
    private const INTEREST_CAVEAT = 'Relative search interest (0-100), scaled within a collection batch. Not absolute search volume; comparable only within the same collection_batch.';

    /**
     * Latest reading per tracked keyword, most-rising first.
     */
    public function index(): JsonResponse
    {
        // Deliberately plain ANSI SQL rather than Postgres' DISTINCT ON: the test
        // suite runs on sqlite (see phpunit.xml), and an endpoint whose only
        // query cannot run under test is an endpoint nothing verifies. The
        // grouped-max join below is portable, and the (keyword_id, date, region)
        // unique index serves it well.
        $latestDates = DB::table('trend_metrics')
            ->select('keyword_id', 'region', DB::raw('MAX(date) as max_date'))
            ->groupBy('keyword_id', 'region');

        $rows = DB::table('trend_metrics')
            ->joinSub($latestDates, 'latest', function ($join) {
                $join->on('latest.keyword_id', '=', 'trend_metrics.keyword_id')
                    ->on('latest.region', '=', 'trend_metrics.region')
                    ->on('latest.max_date', '=', 'trend_metrics.date');
            })
            ->join('keywords', 'keywords.id', '=', 'trend_metrics.keyword_id')
            ->where('keywords.enabled', true)
            ->select([
                'keywords.keyword',
                'keywords.keyword_group',
                'keywords.language',
                'keywords.geo',
                'keywords.source',
                'trend_metrics.date',
                'trend_metrics.interest',
                'trend_metrics.rolling_7d',
                'trend_metrics.rolling_30d',
                'trend_metrics.baseline_90d',
                'trend_metrics.growth_7d',
                'trend_metrics.growth_30d',
                'trend_metrics.growth_score',
                'trend_metrics.z_score',
                'trend_metrics.collection_method',
                'trend_metrics.collection_batch',
            ])
            // "NULLS LAST" is not portable; ordering on the IS NULL flag first
            // achieves it identically on both engines.
            ->orderByRaw('(trend_metrics.growth_score IS NULL) ASC, trend_metrics.growth_score DESC')
            ->get();

        return response()->json([
            'data' => $rows,
            'meta' => [
                'interest_scale' => self::INTEREST_CAVEAT,
                'tracked_keywords' => Keyword::where('enabled', true)->count(),
            ],
        ]);
    }

    /**
     * Full stored series for one keyword — the "historical daily signals are
     * stored and visible" acceptance test for Milestone 3.
     */
    public function show(string $keyword): JsonResponse
    {
        $record = Keyword::where('keyword', $keyword)->first();

        if ($record === null) {
            return response()->json(['error' => "Unknown keyword '{$keyword}'"], 404);
        }

        $series = TrendMetric::where('keyword_id', $record->id)
            ->orderBy('date')
            ->get([
                'date',
                'interest',
                'rolling_7d',
                'rolling_30d',
                'baseline_90d',
                'growth_7d',
                'growth_30d',
                'growth_score',
                'z_score',
                'collection_method',
                'collection_batch',
            ]);

        return response()->json([
            'data' => [
                'keyword' => $record->keyword,
                'keyword_group' => $record->keyword_group,
                'language' => $record->language,
                'geo' => $record->geo,
                'source' => $record->source,
                'series' => $series,
            ],
            'meta' => [
                'interest_scale' => self::INTEREST_CAVEAT,
                'points' => $series->count(),
            ],
        ]);
    }
}
