<?php

namespace Tests\Feature;

use App\Models\Opportunity;
use App\Models\Topic;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\Support\SeedsSignals;
use Tests\TestCase;

class TopicEndpointTest extends TestCase
{
    use RefreshDatabase;
    use SeedsSignals;

    public function test_index_lists_topics_with_no_signals(): void
    {
        // A topic with no evidence is a real answer: either collection has a
        // gap or the problem does not exist. Hiding it hides both.
        Topic::create(['slug' => 'quiet_topic', 'name' => 'Quiet', 'enabled' => true]);

        $response = $this->getJson('/api/v1/topics');

        $response->assertOk()->assertJsonCount(1, 'data');
        $this->assertSame(0, $response->json('data.0.signal_count'));
        $this->assertNull($response->json('data.0.opportunity_id'));
    }

    public function test_index_excludes_disabled_topics(): void
    {
        Topic::create(['slug' => 'live', 'name' => 'Live', 'enabled' => true]);
        Topic::create(['slug' => 'retired', 'name' => 'Retired', 'enabled' => false]);

        $this->getJson('/api/v1/topics')
            ->assertOk()
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.slug', 'live');
    }

    public function test_index_can_narrow_to_topics_with_signals(): void
    {
        $active = Topic::create(['slug' => 'active', 'name' => 'Active', 'enabled' => true]);
        Topic::create(['slug' => 'quiet', 'name' => 'Quiet', 'enabled' => true]);
        $this->signal($active->id, '2026-08-01');

        $this->getJson('/api/v1/topics?with_signals_only=1')
            ->assertOk()
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.slug', 'active');
    }

    public function test_index_carries_signal_counts_and_last_seen(): void
    {
        $topic = Topic::create(['slug' => 'busy', 'name' => 'Busy', 'enabled' => true]);
        $this->signal($topic->id, '2026-07-01');
        $this->signal($topic->id, '2026-08-05');

        $row = $this->getJson('/api/v1/topics')->json('data.0');

        $this->assertSame(2, $row['signal_count']);
        $this->assertStringStartsWith('2026-08-05', $row['last_seen']);
    }

    public function test_show_is_keyed_by_slug(): void
    {
        Topic::create(['slug' => 'billing_invoice', 'name' => 'Billing', 'enabled' => true]);

        $this->getJson('/api/v1/topics/billing_invoice')
            ->assertOk()
            ->assertJsonPath('data.slug', 'billing_invoice');
    }

    public function test_show_returns_404_for_an_unknown_slug(): void
    {
        $this->getJson('/api/v1/topics/no_such_topic')->assertNotFound();
    }

    public function test_show_reports_activity_as_a_dated_series(): void
    {
        $topic = Topic::create(['slug' => 'active', 'name' => 'Active', 'enabled' => true]);
        $this->signal($topic->id, '2026-08-01', severity: 40);
        $this->signal($topic->id, '2026-08-01', severity: 60);
        $this->signal($topic->id, '2026-08-03', severity: 80);

        $activity = $this->getJson('/api/v1/topics/active')->json('data.activity');

        $this->assertSame(3, $activity['signal_count']);
        $this->assertSame('2026-08-01', $activity['series'][0]['date']);
        $this->assertSame(2, $activity['series'][0]['mentions']);
        $this->assertEqualsWithDelta(50.0, $activity['series'][0]['avg_severity'], 0.001);
    }

    public function test_show_reports_state_distribution(): void
    {
        $topic = Topic::create(['slug' => 'regional', 'name' => 'Regional', 'enabled' => true]);
        $this->signal($topic->id, '2026-08-01', region: 'Selangor');
        $this->signal($topic->id, '2026-08-02', region: 'Selangor');
        $this->signal($topic->id, '2026-08-03', region: 'Johor');

        $geography = $this->getJson('/api/v1/topics/regional')->json('data.geography');

        $this->assertSame(['Selangor' => 2, 'Johor' => 1], $geography);
    }

    public function test_show_separates_signals_by_how_they_were_produced(): void
    {
        // §31: a keyword match and a model reading the text are different
        // grades of evidence. Blending them into one count would hide which.
        $topic = Topic::create(['slug' => 'mixed', 'name' => 'Mixed', 'enabled' => true]);
        $this->signal($topic->id, '2026-08-01', method: 'rule_based_keyword_v1');
        $this->signal($topic->id, '2026-08-02', method: 'llm_extract_problem_v1');
        $this->signal($topic->id, '2026-08-03', method: 'llm_extract_problem_v1');

        $methods = $this->getJson('/api/v1/topics/mixed')->json('data.methods');

        $this->assertSame(1, $methods['rule_based_keyword_v1']);
        $this->assertSame(2, $methods['llm_extract_problem_v1']);
    }

    public function test_show_links_to_the_explainable_score_when_one_exists(): void
    {
        $topic = Topic::create(['slug' => 'scored', 'name' => 'Scored', 'enabled' => true]);
        $opportunity = Opportunity::create([
            'topic_id' => $topic->id,
            'title' => 'Scored opportunity',
            'status' => 'observed',
            'recommendation' => 'INVESTIGATE',
            'opportunity_score' => 72,
            'confidence_score' => 55,
            'score_components' => [],
        ]);

        $response = $this->getJson('/api/v1/topics/scored');

        $response->assertOk();
        $this->assertSame($opportunity->id, $response->json('data.opportunity.id'));
        $this->assertSame(
            "/api/v1/opportunities/{$opportunity->id}",
            $response->json('meta.scores_are_explainable_at')
        );
    }

    public function test_show_says_what_to_do_when_a_topic_has_no_opportunity_row(): void
    {
        Topic::create(['slug' => 'unscored', 'name' => 'Unscored', 'enabled' => true]);

        $response = $this->getJson('/api/v1/topics/unscored');

        $this->assertNull($response->json('data.opportunity'));
        // An empty state that names the command is a usable answer; a bare null
        // leaves the reader guessing whether the system is broken.
        $this->assertStringContainsString('intelligence score', $response->json('meta.scoring_note'));
    }

    public function test_show_exposes_the_taxonomy_hierarchy(): void
    {
        $parent = Topic::create(['slug' => 'billing_invoice', 'name' => 'Billing', 'enabled' => true]);
        Topic::create(['slug' => 'einvoice', 'name' => 'e-Invoice', 'parent_id' => $parent->id, 'enabled' => true]);

        $response = $this->getJson('/api/v1/topics/billing_invoice');

        $this->assertSame('einvoice', $response->json('data.children.0.slug'));
        $this->assertNull($response->json('data.parent'));

        $child = $this->getJson('/api/v1/topics/einvoice');
        $this->assertSame('billing_invoice', $child->json('data.parent.slug'));
    }

    public function test_show_returns_recent_signals_with_their_source(): void
    {
        $topic = Topic::create(['slug' => 'evidenced', 'name' => 'Evidenced', 'enabled' => true]);
        $this->signal($topic->id, '2026-08-05');

        $signals = $this->getJson('/api/v1/topics/evidenced')->json('data.recent_signals');

        $this->assertCount(1, $signals);
        $this->assertSame('test-source', $signals[0]['source']);
        $this->assertNotEmpty($signals[0]['excerpt']);
    }
}
