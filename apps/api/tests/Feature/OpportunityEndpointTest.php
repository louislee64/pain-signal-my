<?php

namespace Tests\Feature;

use App\Models\Opportunity;
use App\Models\Topic;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\Support\SeedsSignals;
use Tests\TestCase;

class OpportunityEndpointTest extends TestCase
{
    use RefreshDatabase;
    use SeedsSignals;

    public function test_index_ranks_by_opportunity_score(): void
    {
        $this->opportunity('Low', opportunityScore: 40);
        $this->opportunity('High', opportunityScore: 88);

        $response = $this->getJson('/api/v1/opportunities');

        $response->assertOk();
        $this->assertSame('High', $response->json('data.0.title'));
        $this->assertSame('Low', $response->json('data.1.title'));
    }

    public function test_index_always_returns_confidence_beside_the_score(): void
    {
        // §30: a score without its confidence invites treating a guess as fact.
        $this->opportunity('Thin evidence', opportunityScore: 84, confidenceScore: 42);

        $row = $this->getJson('/api/v1/opportunities')->json('data.0');

        $this->assertArrayHasKey('opportunity_score', $row);
        $this->assertArrayHasKey('confidence_score', $row);
        $this->assertSame('42.00', $row['confidence_score']);
    }

    public function test_index_filters_by_recommendation(): void
    {
        $this->opportunity('Investigate me', recommendation: 'INVESTIGATE');
        $this->opportunity('Ignore me', recommendation: 'IGNORE');

        $response = $this->getJson('/api/v1/opportunities?recommendation=INVESTIGATE');

        $response->assertOk()->assertJsonCount(1, 'data');
        $this->assertSame('Investigate me', $response->json('data.0.title'));
    }

    public function test_index_filters_by_status(): void
    {
        $this->opportunity('Observed one', status: 'observed');
        $this->opportunity('Piloting', status: 'paid_pilot');

        $this->getJson('/api/v1/opportunities?status=paid_pilot')
            ->assertOk()
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.title', 'Piloting');
    }

    public function test_unscored_opportunities_sort_last_not_first(): void
    {
        $this->opportunity('Never scored', opportunityScore: null);
        $this->opportunity('Scored', opportunityScore: 10);

        $this->assertSame('Scored', $this->getJson('/api/v1/opportunities')->json('data.0.title'));
    }

    public function test_show_exposes_the_full_score_breakdown(): void
    {
        // Milestone 4's acceptance criterion.
        $components = [
            'pain_score' => [
                'score' => 61.5,
                'dimensions' => [
                    'mention_frequency' => ['raw' => 25, 'normalized' => 50.0, 'weight' => 0.3, 'contribution' => 15.0],
                ],
                'notes' => [],
            ],
        ];
        $opportunity = $this->opportunity('Explainable', components: $components);

        $response = $this->getJson("/api/v1/opportunities/{$opportunity->id}");

        $response->assertOk();
        $this->assertEqualsWithDelta(
            15.0,
            $response->json('data.score_components.pain_score.dimensions.mention_frequency.contribution'),
            0.001
        );
        $this->assertNotNull($response->json('meta.scoring_config_version'));
    }

    public function test_show_returns_404_for_an_unknown_opportunity(): void
    {
        $this->getJson('/api/v1/opportunities/99999')->assertNotFound();
    }

    public function test_index_filters_by_topic_slug(): void
    {
        $wanted = $this->opportunity('Wanted');
        $this->opportunity('Unwanted');
        $slug = $wanted->topic->slug;

        $this->getJson("/api/v1/opportunities?topic={$slug}")
            ->assertOk()
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.title', 'Wanted');
    }

    public function test_index_filters_by_target_buyer(): void
    {
        $this->opportunity('Owner buys', buyer: 'business_owner');
        $this->opportunity('Finance buys', buyer: 'finance_department');

        $this->getJson('/api/v1/opportunities?buyer=finance_department')
            ->assertOk()
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.title', 'Finance buys');
    }

    public function test_confidence_filter_is_a_floor_not_an_exact_match(): void
    {
        // §30: the useful question is "show me only what I can believe", not
        // "confidence exactly 61".
        $this->opportunity('Believable', confidenceScore: 80);
        $this->opportunity('Thin', confidenceScore: 20);

        $this->getJson('/api/v1/opportunities?min_confidence=50')
            ->assertOk()
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.title', 'Believable');
    }

    public function test_index_filters_by_minimum_opportunity_score(): void
    {
        $this->opportunity('Strong', opportunityScore: 75);
        $this->opportunity('Weak', opportunityScore: 30);

        $this->getJson('/api/v1/opportunities?min_opportunity=60')
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.title', 'Strong');
    }

    public function test_state_filter_matches_on_where_the_evidence_came_from(): void
    {
        $selangor = $this->opportunity('Selangor problem');
        $johor = $this->opportunity('Johor problem');
        $this->signal($selangor->topic_id, '2026-08-01', region: 'Selangor');
        $this->signal($johor->topic_id, '2026-08-01', region: 'Johor');

        $this->getJson('/api/v1/opportunities?state=Johor')
            ->assertOk()
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.title', 'Johor problem');
    }

    public function test_source_filter_matches_on_where_the_evidence_came_from(): void
    {
        $forum = $this->opportunity('From the forum');
        $official = $this->opportunity('From the agency');
        $this->signal($forum->topic_id, '2026-08-01', sourceSlug: 'a-forum');
        $this->signal($official->topic_id, '2026-08-01', sourceSlug: 'an-agency');

        $this->getJson('/api/v1/opportunities?source=an-agency')
            ->assertOk()
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.title', 'From the agency');
    }

    public function test_since_filter_excludes_topics_whose_evidence_is_all_older(): void
    {
        $recent = $this->opportunity('Still discussed');
        $stale = $this->opportunity('Went quiet');
        $this->signal($recent->topic_id, '2026-08-01');
        $this->signal($stale->topic_id, '2026-01-01');

        $this->getJson('/api/v1/opportunities?since=2026-07-01')
            ->assertOk()
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.title', 'Still discussed');
    }

    public function test_index_declares_which_spec_33_filters_have_no_data_yet(): void
    {
        // A control that silently matches nothing reads as "no opportunities in
        // retail" rather than "we do not classify industry". Saying so in meta
        // lets the dashboard omit the control instead of shipping a dead one.
        $meta = $this->getJson('/api/v1/opportunities')->json('meta');

        $this->assertArrayHasKey('industry', $meta['filters_not_yet_available']);
        // §33's "commercial stage" is `status` now that §3's funnel is live.
        $this->assertArrayNotHasKey('commercial_stage', $meta['filters_not_yet_available']);
        $this->assertSame('status', $meta['commercial_stage_filter']);
    }

    public function test_index_echoes_back_the_filters_it_applied(): void
    {
        $this->opportunity('Anything', recommendation: 'WATCH');

        $meta = $this->getJson('/api/v1/opportunities?recommendation=WATCH&min_confidence=10')->json('meta');

        $this->assertSame('WATCH', $meta['filters_applied']['recommendation']);
        $this->assertSame('10', $meta['filters_applied']['min_confidence']);
    }

    public function test_show_returns_public_text_examples_with_their_source(): void
    {
        $opportunity = $this->opportunity('Evidenced');
        $this->signal($opportunity->topic_id, '2026-08-01', severity: 80, sourceSlug: 'a-forum');

        $evidence = $this->getJson("/api/v1/opportunities/{$opportunity->id}")->json('data.evidence');

        $this->assertSame(1, $evidence['signal_count']);
        $this->assertSame(1, $evidence['distinct_sources']);
        $this->assertSame('a-forum', $evidence['examples'][0]['source']);
        $this->assertNotEmpty($evidence['examples'][0]['excerpt']);
        // §31: how a signal was produced is part of judging it.
        $this->assertSame('rule_based_keyword_v1', $evidence['examples'][0]['method']);
    }

    public function test_distinct_sources_counts_sources_not_documents(): void
    {
        // §31's evidence hierarchy turns on independent corroboration. Ten posts
        // on one forum must not read as ten independent sources.
        $opportunity = $this->opportunity('One noisy forum');
        foreach (range(1, 5) as $i) {
            $this->signal($opportunity->topic_id, '2026-08-01', sourceSlug: 'one-forum');
        }

        $evidence = $this->getJson("/api/v1/opportunities/{$opportunity->id}")->json('data.evidence');

        $this->assertSame(5, $evidence['signal_count']);
        $this->assertSame(1, $evidence['distinct_sources']);
    }

    public function test_show_returns_state_distribution(): void
    {
        $opportunity = $this->opportunity('Regional');
        $this->signal($opportunity->topic_id, '2026-08-01', region: 'Selangor');
        $this->signal($opportunity->topic_id, '2026-08-02', region: 'Selangor');
        $this->signal($opportunity->topic_id, '2026-08-03', region: 'Penang');

        $geography = $this->getJson("/api/v1/opportunities/{$opportunity->id}")->json('data.geography');

        $this->assertSame(['Selangor' => 2, 'Penang' => 1], $geography);
    }

    public function test_show_returns_a_trend_series_and_rolling_windows(): void
    {
        $opportunity = $this->opportunity('Trending');
        $this->signal($opportunity->topic_id, now()->subDays(2)->toDateString());
        $this->signal($opportunity->topic_id, now()->subDays(40)->toDateString());

        $trend = $this->getJson("/api/v1/opportunities/{$opportunity->id}")->json('data.trend');

        $this->assertCount(2, $trend['series']);
        $this->assertSame(1, $trend['windows']['mentions_7d']);
        $this->assertSame(2, $trend['windows']['mentions_90d']);
    }

    public function test_show_reports_payer_and_affected_role_separately(): void
    {
        // §5: the cashier suffers, the owner buys. Collapsing them would point
        // the commercial model at someone with no budget.
        $opportunity = $this->opportunity('Split incentive', buyer: 'business_owner');
        $this->signal(
            $opportunity->topic_id,
            '2026-08-01',
            payerType: 'business_owner',
            evidence: ['affected_role' => 'cashier'],
        );

        $buyer = $this->getJson("/api/v1/opportunities/{$opportunity->id}")->json('data.buyer_evidence');

        $this->assertSame('business_owner', $buyer['suggested_buyer']);
        $this->assertSame(1, $buyer['payer_types']['business_owner']);
        $this->assertSame(1, $buyer['affected_roles']['cashier']);
    }

    public function test_show_points_at_the_validation_endpoint(): void
    {
        $opportunity = $this->opportunity('Needs validating');

        $meta = $this->getJson("/api/v1/opportunities/{$opportunity->id}")->json('meta');

        // The §34 validation sections are a separate working view, not part of
        // every dashboard page load.
        $this->assertSame("/api/v1/opportunities/{$opportunity->id}/validation", $meta['validation_at']);
    }

    public function test_show_works_for_an_opportunity_with_no_evidence_at_all(): void
    {
        $opportunity = $this->opportunity('Bare');

        $response = $this->getJson("/api/v1/opportunities/{$opportunity->id}");

        $response->assertOk();
        $this->assertSame(0, $response->json('data.evidence.signal_count'));
        $this->assertSame([], $response->json('data.geography'));
        $this->assertSame([], $response->json('data.trend.series'));
    }

    private function opportunity(
        string $title,
        ?float $opportunityScore = 50,
        ?float $confidenceScore = 50,
        string $recommendation = 'WATCH',
        string $status = 'observed',
        ?array $components = null,
        ?string $buyer = 'business_owner',
    ): Opportunity {
        $topic = Topic::create([
            'slug' => 'topic-'.str()->random(8),
            'name' => $title.' topic',
            'enabled' => true,
        ]);

        $opportunity = Opportunity::create([
            'topic_id' => $topic->id,
            'title' => $title,
            'status' => $status,
            'recommendation' => $recommendation,
            'pain_score' => 50,
            'commercial_score' => 50,
            'opportunity_score' => $opportunityScore,
            'confidence_score' => $confidenceScore,
            'score_components' => $components ?? [],
            'target_buyer' => $buyer,
            'scoring_config_version' => '1',
            'scored_at' => now(),
        ]);

        return $opportunity->setRelation('topic', $topic);
    }
}
