<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Alert;
use App\Models\Report;
use App\Notifications\Notifier;
use App\Services\ReportService;
use Carbon\CarbonImmutable;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

/**
 * §36's `GET /reports` and `POST /reports/generate`, plus §40's alert history.
 */
class ReportController extends Controller
{
    public function __construct(private readonly ReportService $reports) {}

    /**
     * Report history (§55).
     *
     * The list deliberately omits `markdown` and `sections`. A year of weekly
     * reports is a large amount of prose, and a list endpoint that returns every
     * word of it makes the history page slow at exactly the point it becomes
     * useful.
     */
    public function index(Request $request): JsonResponse
    {
        $reports = Report::query()
            ->when($request->filled('type'), fn ($q) => $q->where('report_type', $request->string('type')))
            ->orderByDesc('period_end')
            ->orderByDesc('id')
            ->limit((int) $request->integer('limit', 26))
            ->get();

        return response()->json([
            'data' => $reports->map(fn (Report $report) => [
                'id' => $report->id,
                'report_type' => $report->report_type,
                'title' => $report->title,
                'period_start' => $report->period_start->toDateString(),
                'period_end' => $report->period_end->toDateString(),
                'generated_at' => $report->generated_at?->toIso8601String(),
                'content_hash' => $report->content_hash,
                // Enough for a list row to be worth reading without the body.
                'headline_count' => count($report->sections['executive_summary']['findings'] ?? []),
                'quiet_period' => $report->sections['executive_summary']['quiet_period'] ?? false,
                'build_recommendations' => count($report->sections['build_recommendation']['recommended'] ?? []),
            ]),
            'meta' => ['count' => $reports->count()],
        ]);
    }

    public function show(int $id): JsonResponse
    {
        $report = Report::find($id);

        if ($report === null) {
            return response()->json(['error' => "Unknown report {$id}"], 404);
        }

        return response()->json([
            'data' => [
                'id' => $report->id,
                'report_type' => $report->report_type,
                'title' => $report->title,
                'period_start' => $report->period_start->toDateString(),
                'period_end' => $report->period_end->toDateString(),
                'generated_at' => $report->generated_at?->toIso8601String(),
                'content_hash' => $report->content_hash,
                'sections' => $report->sections,
                // Served as stored, never re-rendered. A report that changed
                // under the reader would be useless as a record of what was known
                // when a decision was made.
                'markdown' => $report->markdown,
                'inputs' => $report->inputs,
            ],
            'meta' => [
                'reproducibility' => "/api/v1/reports/{$report->id}/verify",
            ],
        ]);
    }

    /**
     * §36's `POST /reports/generate`.
     *
     * Notification is opt-in per request rather than automatic. Someone
     * regenerating a report to look at it should not thereby post it to a team
     * channel — the scheduled run is what notifies (§38).
     */
    public function generate(Request $request): JsonResponse
    {
        $data = $request->validate([
            'week_ending' => ['nullable', 'date'],
            'notify' => ['nullable', 'boolean'],
        ]);

        // Defaults to yesterday: a period still in progress would produce a
        // report that changes if regenerated an hour later, which is the one
        // thing the acceptance criterion forbids.
        $end = isset($data['week_ending'])
            ? CarbonImmutable::parse($data['week_ending'])
            : CarbonImmutable::yesterday();

        if ($end->isFuture()) {
            return response()->json([
                'error' => 'week_ending cannot be in the future — there is no stored data to report on.',
            ], 422);
        }

        $report = $this->reports->generateWeekly($end);

        $delivery = null;
        if ($data['notify'] ?? false) {
            $notifier = new Notifier();
            $delivery = [
                'channels' => $notifier->channelNames(),
                'results' => $notifier->send(
                    $report->title.' — '.$report->period_end->toDateString(),
                    $report->markdown,
                ),
            ];
        }

        return response()->json([
            'data' => [
                'id' => $report->id,
                'period_start' => $report->period_start->toDateString(),
                'period_end' => $report->period_end->toDateString(),
                'content_hash' => $report->content_hash,
            ],
            'meta' => ['delivery' => $delivery],
        ], 201);
    }

    /**
     * Rebuild the same period and report whether the findings matched.
     *
     * This is Milestone 7's acceptance criterion made checkable rather than
     * asserted. A mismatch is not necessarily a bug — new evidence for a past
     * week legitimately changes that week's report — so the response gives the
     * facts and leaves the judgement to a person.
     */
    public function verify(int $id): JsonResponse
    {
        $report = Report::find($id);

        if ($report === null) {
            return response()->json(['error' => "Unknown report {$id}"], 404);
        }

        $result = $this->reports->verifyReproducible($report);

        return response()->json([
            'data' => $result,
            'meta' => [
                'note' => $result['reproducible']
                    ? 'Rebuilding this period from stored data produced identical findings.'
                    : 'Findings differ. Either the underlying data changed since generation, or the builder is not deterministic.',
            ],
        ]);
    }

    /** §40's alert history. */
    public function alerts(Request $request): JsonResponse
    {
        $alerts = Alert::query()
            ->with('opportunity:id,title')
            // Baseline rows are bookkeeping, not news — they exist so a future
            // score rise is measurable and are never sent.
            ->where('delivered_via', '!=', 'suppressed:baseline')
            ->orWhereNull('delivered_via')
            ->when($request->filled('type'), fn ($q) => $q->where('alert_type', $request->string('type')))
            ->when($request->boolean('pending'), fn ($q) => $q->whereNull('delivered_at'))
            ->orderByDesc('detected_at')
            ->orderByDesc('id')
            ->limit((int) $request->integer('limit', 50))
            ->get();

        return response()->json([
            'data' => $alerts->map(fn (Alert $alert) => [
                'id' => $alert->id,
                'alert_type' => $alert->alert_type,
                'severity' => $alert->severity,
                'opportunity_id' => $alert->opportunity_id,
                'opportunity_title' => $alert->opportunity?->title,
                'title' => $alert->title,
                'body' => $alert->body,
                'context' => $alert->context,
                'detected_at' => $alert->detected_at?->toIso8601String(),
                'delivered_at' => $alert->delivered_at?->toIso8601String(),
                'delivered_via' => $alert->delivered_via,
                'delivery_error' => $alert->delivery_error,
            ]),
            'meta' => [
                'count' => $alerts->count(),
                'pending' => Alert::whereNull('delivered_at')->count(),
            ],
        ]);
    }
}
