<?php

namespace Tests\Feature;

use App\Models\Opportunity;
use App\Models\Topic;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class OpportunityEndpointTest extends TestCase
{
    use RefreshDatabase;

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

    private function opportunity(
        string $title,
        ?float $opportunityScore = 50,
        ?float $confidenceScore = 50,
        string $recommendation = 'WATCH',
        string $status = 'observed',
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
            'status' => $status,
            'recommendation' => $recommendation,
            'pain_score' => 50,
            'commercial_score' => 50,
            'opportunity_score' => $opportunityScore,
            'confidence_score' => $confidenceScore,
            'score_components' => $components ?? [],
            'scoring_config_version' => '1',
            'scored_at' => now(),
        ]);
    }
}
