<?php

namespace Tests\Feature;

use App\Models\Keyword;
use App\Models\TrendMetric;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class TrendEndpointTest extends TestCase
{
    use RefreshDatabase;

    public function test_index_returns_the_latest_reading_per_keyword(): void
    {
        $keyword = $this->keyword('invoice software');
        $this->metric($keyword, '2026-03-01', 40);
        $this->metric($keyword, '2026-05-03', 100, growthScore: 1.68);

        $response = $this->getJson('/api/v1/trends');

        $response->assertOk();
        $this->assertCount(1, $response->json('data'), 'one row per keyword, not one per observation');
        $this->assertSame('2026-05-03', $response->json('data.0.date'));
        $this->assertSame(100, $response->json('data.0.interest'));
    }

    public function test_index_sorts_most_rising_first(): void
    {
        $flat = $this->keyword('stock count');
        $this->metric($flat, '2026-05-03', 11, growthScore: 1.02);

        $rising = $this->keyword('invoice software');
        $this->metric($rising, '2026-05-03', 100, growthScore: 1.68);

        $response = $this->getJson('/api/v1/trends');

        $this->assertSame('invoice software', $response->json('data.0.keyword'));
        $this->assertSame('stock count', $response->json('data.1.keyword'));
    }

    public function test_index_excludes_disabled_keywords(): void
    {
        $disabled = $this->keyword('retired keyword', enabled: false);
        $this->metric($disabled, '2026-05-03', 50);

        $this->getJson('/api/v1/trends')->assertOk()->assertJsonCount(0, 'data');
    }

    public function test_index_carries_the_relative_interest_caveat(): void
    {
        // PROJECT_SPEC.md §16 is emphatic that these are not absolute volumes;
        // the caveat must survive into anything built on this response.
        $response = $this->getJson('/api/v1/trends');

        $response->assertOk();
        $this->assertStringContainsString('Not absolute search volume', $response->json('meta.interest_scale'));
    }

    public function test_show_returns_the_full_series_in_date_order(): void
    {
        $keyword = $this->keyword('invoice software');
        $this->metric($keyword, '2026-05-03', 100);
        $this->metric($keyword, '2026-03-01', 40);

        $response = $this->getJson('/api/v1/trends/'.rawurlencode('invoice software'));

        $response->assertOk();
        $this->assertSame(2, $response->json('meta.points'));
        $this->assertSame(['2026-03-01', '2026-05-03'], array_column($response->json('data.series'), 'date'));
    }

    public function test_show_returns_404_for_an_unknown_keyword(): void
    {
        $this->getJson('/api/v1/trends/never-tracked')->assertNotFound();
    }

    public function test_show_handles_keywords_containing_spaces(): void
    {
        $this->keyword('e invoice malaysia');

        $this->getJson('/api/v1/trends/'.rawurlencode('e invoice malaysia'))
            ->assertOk()
            ->assertJsonPath('data.keyword', 'e invoice malaysia');
    }

    private function keyword(string $keyword, bool $enabled = true): Keyword
    {
        return Keyword::create([
            'keyword' => $keyword,
            'keyword_group' => 'test_group',
            'language' => 'en',
            'geo' => 'MY',
            'source' => Keyword::SOURCE_CONFIG,
            'enabled' => $enabled,
        ]);
    }

    private function metric(Keyword $keyword, string $date, int $interest, ?float $growthScore = null): TrendMetric
    {
        return TrendMetric::create([
            'keyword_id' => $keyword->id,
            'date' => $date,
            'country' => 'MY',
            'region' => '',
            'interest' => $interest,
            'growth_score' => $growthScore,
            'collection_method' => 'google_trends_csv',
            'collection_batch' => '01KZFS0XP94RG11JRNZK89729S',
        ]);
    }
}
