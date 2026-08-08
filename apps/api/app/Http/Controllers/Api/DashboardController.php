<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\IngestionRun;
use App\Models\Opportunity;
use App\Models\ProblemSignal;
use App\Models\Source;
use Illuminate\Http\JsonResponse;

class DashboardController extends Controller
{
    /**
     * Dashboard summary (PROJECT_SPEC.md §33, §36).
     *
     * §33 is blunt about what this must answer — "What should I investigate or
     * sell this week?" and explicitly NOT "How much data did we scrape?". So
     * the five cards are the payload and the collection counts are a small
     * `system` block at the end, not the headline.
     *
     * Each card is one opportunity plus the figure that earned it its place, so
     * the dashboard never shows a superlative without the number behind it.
     */
    public function index(): JsonResponse
    {
        return response()->json([
            'data' => [
                'cards' => [
                    'top_opportunity' => $this->topOpportunity(),
                    'fastest_rising' => $this->fastestRising(),
                    'strongest_buyer_evidence' => $this->strongestBuyerEvidence(),
                    'newest_emerging_problem' => $this->newestEmerging(),
                    'highest_paid_validation' => $this->highestPaidValidation(),
                ],
                'system' => $this->systemHealth(),
            ],
            'meta' => [
                'answers' => 'What should I investigate or sell this week?',
                'scores_are_explainable_at' => '/api/v1/opportunities/{id}',
            ],
        ]);
    }

    private function topOpportunity(): ?array
    {
        $opportunity = Opportunity::query()
            ->with('topic:id,slug,name')
            ->whereNotNull('opportunity_score')
            ->orderByDesc('opportunity_score')
            ->first();

        return $this->card($opportunity, 'Highest blended opportunity score');
    }

    /**
     * §33's "Fastest Rising". Ranked on the stored `growth` dimension rather
     * than on a fresh calculation, so the card and the detail page can never
     * disagree about the same number.
     */
    private function fastestRising(): ?array
    {
        $ranked = Opportunity::query()
            ->with('topic:id,slug,name')
            ->whereNotNull('score_components')
            ->get()
            ->map(fn (Opportunity $o) => [
                'opportunity' => $o,
                'growth' => data_get($o->score_components, 'pain_score.dimensions.growth.raw'),
            ])
            ->filter(fn (array $row) => is_numeric($row['growth']))
            ->sortByDesc('growth')
            ->first();

        if ($ranked === null) {
            return null;
        }

        return $this->card(
            $ranked['opportunity'],
            'Mention growth vs the previous window',
            ['growth_percent' => round((float) $ranked['growth'], 1)],
        );
    }

    /**
     * §33's "Strongest Buyer Evidence" — payer clarity, which §27 weights
     * highest of the six commercial dimensions precisely because knowing who
     * pays is the difference between a problem and a business.
     */
    private function strongestBuyerEvidence(): ?array
    {
        $ranked = Opportunity::query()
            ->with('topic:id,slug,name')
            ->whereNotNull('score_components')
            ->get()
            ->map(fn (Opportunity $o) => [
                'opportunity' => $o,
                'payer_clarity' => data_get($o->score_components, 'commercial_score.dimensions.payer_clarity.normalized'),
            ])
            ->filter(fn (array $row) => is_numeric($row['payer_clarity']) && $row['payer_clarity'] > 0)
            ->sortByDesc('payer_clarity')
            ->first();

        if ($ranked === null) {
            return null;
        }

        return $this->card(
            $ranked['opportunity'],
            'Clarity of who would pay to fix this',
            [
                'payer_clarity' => round((float) $ranked['payer_clarity'], 1),
                'target_buyer' => $ranked['opportunity']->target_buyer,
            ],
        );
    }

    /**
     * §33's "Newest Emerging Problem". Deliberately ranked on when a topic's
     * FIRST signal arrived, not on its most recent one: "newest" means newly
     * appearing, and every actively-discussed topic has a recent signal.
     */
    private function newestEmerging(): ?array
    {
        $newest = ProblemSignal::query()
            ->selectRaw('topic_id, MIN(signal_date) as first_seen, COUNT(*) as signal_count')
            ->groupBy('topic_id')
            ->orderByDesc('first_seen')
            ->first();

        if ($newest === null) {
            return null;
        }

        $opportunity = Opportunity::with('topic:id,slug,name')
            ->where('topic_id', $newest->topic_id)
            ->first();

        if ($opportunity === null) {
            return null;
        }

        return $this->card($opportunity, 'First observed most recently', [
            'first_seen' => $newest->first_seen,
            'signal_count' => (int) $newest->signal_count,
        ]);
    }

    /**
     * §33's "Highest Paid Validation".
     *
     * The commercial CRM tables (§21) that record pilots and paying customers
     * arrive in Milestone 6, so there is nothing to rank yet. This returns a
     * declared-empty card rather than being omitted: a card that silently
     * disappears reads as "no opportunities have paid validation", which is a
     * claim about the data. "We do not track this yet" is the truth.
     */
    private function highestPaidValidation(): array
    {
        return [
            'available' => false,
            'reason' => 'Paid pilots and paying customers are recorded from Milestone 6 (§21).',
        ];
    }

    private function card(?Opportunity $o, string $because, array $extra = []): ?array
    {
        if ($o === null) {
            return null;
        }

        return array_merge([
            'available' => true,
            'id' => $o->id,
            'title' => $o->title,
            'topic' => $o->topic?->slug,
            'topic_name' => $o->topic?->name,
            'opportunity_score' => $o->opportunity_score,
            'confidence_score' => $o->confidence_score,
            'recommendation' => $o->recommendation,
            'because' => $because,
        ], $extra);
    }

    /**
     * §33 says the dashboard must not lead with scrape volume. It still has to
     * be somewhere — a dashboard that hides a dead collector is worse than one
     * that buries the counts — so it lives here, last, and only reports what
     * would make you distrust the numbers above it.
     */
    private function systemHealth(): array
    {
        $lastRun = IngestionRun::query()->orderByDesc('started_at')->first();

        $sources = Source::where('enabled', true)->get();
        $lastRuns = IngestionRun::query()
            ->whereIn('source_id', $sources->pluck('id'))
            ->orderByDesc('started_at')
            ->get()
            ->groupBy('source_id')
            ->map(fn ($runs) => $runs->first());

        // Uses Source::health(), the same method the source page uses. An
        // "is this source ok" test written a second time here would drift, and
        // silently: the overview would read "0 problems" while /sources listed
        // three. A source that succeeded but returned nothing is the case that
        // a naive "has it ever succeeded" check gets wrong.
        $unhealthy = $sources
            ->filter(fn (Source $source) => $source->health($lastRuns->get($source->id))['status'] !== 'ok')
            ->count();

        return [
            'opportunities_scored' => Opportunity::whereNotNull('opportunity_score')->count(),
            'signals' => ProblemSignal::count(),
            'sources_enabled' => $sources->count(),
            'last_ingestion_at' => $lastRun?->started_at?->toIso8601String(),
            'last_ingestion_status' => $lastRun?->status,
            'unhealthy_sources' => $unhealthy,
        ];
    }
}
