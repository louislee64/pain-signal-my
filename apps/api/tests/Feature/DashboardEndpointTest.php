<?php

namespace Tests\Feature;

use App\Models\Opportunity;
use App\Models\Topic;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\Support\SeedsSignals;
use Tests\TestCase;

class DashboardEndpointTest extends TestCase
{
    use RefreshDatabase;
    use SeedsSignals;

    public function test_it_answers_the_question_spec_33_asks(): void
    {
        // §33: the dashboard must answer "What should I investigate or sell
        // this week?" and NOT "How much data did we scrape?". The shape of the
        // payload is the assertion — cards first, collection counts demoted to
        // a `system` block.
        $response = $this->getJson('/api/v1/dashboard');

        $response->assertOk();
        $this->assertArrayHasKey('cards', $response->json('data'));
        $this->assertArrayHasKey('system', $response->json('data'));
        $this->assertStringContainsString('investigate or sell', $response->json('meta.answers'));
    }

    public function test_all_five_spec_33_cards_are_present(): void
    {
        $cards = $this->getJson('/api/v1/dashboard')->json('data.cards');

        $this->assertSame([
            'top_opportunity',
            'fastest_rising',
            'strongest_buyer_evidence',
            'newest_emerging_problem',
            'highest_paid_validation',
        ], array_keys($cards));
    }

    public function test_top_opportunity_is_the_highest_scoring_one(): void
    {
        $this->opportunity('Middling', opportunityScore: 55);
        $this->opportunity('Best', opportunityScore: 91);

        $card = $this->getJson('/api/v1/dashboard')->json('data.cards.top_opportunity');

        $this->assertSame('Best', $card['title']);
        // A superlative without the number behind it is just an assertion.
        $this->assertSame('91.00', $card['opportunity_score']);
        $this->assertNotEmpty($card['because']);
    }

    public function test_top_opportunity_card_carries_confidence(): void
    {
        // §30 again: the card is the most prominent place a score appears, so
        // it is the place where omitting confidence does the most damage.
        $this->opportunity('Attractive but thin', opportunityScore: 84, confidenceScore: 42);

        $card = $this->getJson('/api/v1/dashboard')->json('data.cards.top_opportunity');

        $this->assertSame('42.00', $card['confidence_score']);
    }

    public function test_fastest_rising_ranks_on_the_stored_growth_dimension(): void
    {
        $this->opportunity('Flat', components: $this->componentsWithGrowth(2.0));
        $this->opportunity('Surging', components: $this->componentsWithGrowth(180.0));

        $card = $this->getJson('/api/v1/dashboard')->json('data.cards.fastest_rising');

        $this->assertSame('Surging', $card['title']);
        $this->assertEqualsWithDelta(180.0, $card['growth_percent'], 0.001);
    }

    public function test_fastest_rising_ignores_opportunities_with_no_growth_measurement(): void
    {
        // growth is null when there is no prior window to compare against.
        // Treating null as 0 would be a claim ("flat"); it must simply not rank.
        $this->opportunity('No prior window', components: $this->componentsWithGrowth(null));

        $this->assertNull($this->getJson('/api/v1/dashboard')->json('data.cards.fastest_rising'));
    }

    public function test_strongest_buyer_evidence_ranks_on_payer_clarity(): void
    {
        $this->opportunity('Vague buyer', components: $this->componentsWithPayerClarity(20.0));
        $this->opportunity('Clear buyer', components: $this->componentsWithPayerClarity(95.0));

        $card = $this->getJson('/api/v1/dashboard')->json('data.cards.strongest_buyer_evidence');

        $this->assertSame('Clear buyer', $card['title']);
        $this->assertEqualsWithDelta(95.0, $card['payer_clarity'], 0.001);
    }

    public function test_newest_emerging_ranks_on_first_seen_not_last_seen(): void
    {
        // "Newest" means newly appearing. Every actively-discussed topic has a
        // recent signal, so ranking on the latest date would just return the
        // busiest topic under a misleading label.
        $old = $this->opportunity('Long-running problem');
        $new = $this->opportunity('Just appeared');

        $this->signal($old->topic_id, '2026-01-01');
        $this->signal($old->topic_id, '2026-08-07');   // recent activity
        $this->signal($new->topic_id, '2026-07-20');   // first seen later

        $card = $this->getJson('/api/v1/dashboard')->json('data.cards.newest_emerging_problem');

        $this->assertSame('Just appeared', $card['title']);
    }

    public function test_paid_validation_card_declares_itself_unavailable_rather_than_vanishing(): void
    {
        $this->opportunity('Anything');

        $card = $this->getJson('/api/v1/dashboard')->json('data.cards.highest_paid_validation');

        // A card that silently disappears reads as "nothing has paid
        // validation", which is a claim about the data rather than the truth
        // ("we don't track this yet").
        $this->assertFalse($card['available']);
        $this->assertStringContainsString('Milestone 6', $card['reason']);
    }

    public function test_cards_are_null_on_an_empty_database_rather_than_erroring(): void
    {
        $cards = $this->getJson('/api/v1/dashboard')->assertOk()->json('data.cards');

        $this->assertNull($cards['top_opportunity']);
        $this->assertNull($cards['fastest_rising']);
        $this->assertNull($cards['newest_emerging_problem']);
    }

    public function test_system_block_reports_what_would_make_you_distrust_the_numbers(): void
    {
        $this->opportunity('Scored', opportunityScore: 70);

        $system = $this->getJson('/api/v1/dashboard')->json('data.system');

        $this->assertSame(1, $system['opportunities_scored']);
        foreach (['signals', 'sources_enabled', 'last_ingestion_at', 'unhealthy_sources'] as $key) {
            $this->assertArrayHasKey($key, $system);
        }
    }

    public function test_unhealthy_source_count_agrees_with_the_source_health_page(): void
    {
        // Both read Source::health(). A second "is this source ok" test written
        // for the dashboard would drift silently — the overview saying "0
        // problems" while /sources lists three is worse than either alone.
        $source = $this->source('quietly-broken');
        \App\Models\IngestionRun::create([
            'source_id' => $source->id,
            'status' => 'succeeded',
            'started_at' => now(),
            'finished_at' => now(),
            // Succeeded but empty: a "has it ever succeeded" check calls this
            // healthy, and it is not.
            'records_received' => 0,
        ]);

        $dashboard = $this->getJson('/api/v1/dashboard')->json('data.system.unhealthy_sources');
        $page = collect($this->getJson('/api/v1/sources')->json('data'))
            ->filter(fn (array $row) => $row['health']['status'] !== 'ok')
            ->count();

        $this->assertSame(1, $dashboard);
        $this->assertSame($page, $dashboard);
    }

    private function componentsWithGrowth(?float $growth): array
    {
        return [
            'pain_score' => [
                'score' => 50.0,
                'dimensions' => ['growth' => ['raw' => $growth, 'normalized' => 0.0, 'weight' => 0.25, 'contribution' => 0.0]],
                'notes' => [],
            ],
        ];
    }

    private function componentsWithPayerClarity(float $clarity): array
    {
        return [
            'commercial_score' => [
                'score' => 50.0,
                'dimensions' => ['payer_clarity' => ['raw' => 'business_owner', 'normalized' => $clarity, 'weight' => 0.25, 'contribution' => 0.0]],
                'notes' => [],
            ],
        ];
    }

    private function opportunity(
        string $title,
        ?float $opportunityScore = 50,
        ?float $confidenceScore = 50,
        ?array $components = null,
    ): Opportunity {
        $topic = Topic::create([
            'slug' => 'topic-'.str()->random(8),
            'name' => $title.' topic',
            'enabled' => true,
        ]);

        return Opportunity::create([
            'topic_id' => $topic->id,
            'title' => $title,
            'status' => 'observed',
            'recommendation' => 'WATCH',
            'pain_score' => 50,
            'commercial_score' => 50,
            'opportunity_score' => $opportunityScore,
            'confidence_score' => $confidenceScore,
            'target_buyer' => 'business_owner',
            'score_components' => $components ?? [],
            'scoring_config_version' => '1',
            'scored_at' => now(),
        ]);
    }
}
