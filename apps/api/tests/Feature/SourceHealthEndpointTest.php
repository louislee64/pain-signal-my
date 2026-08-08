<?php

namespace Tests\Feature;

use App\Models\IngestionRun;
use App\Models\Source;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\Support\SeedsSignals;
use Tests\TestCase;

class SourceHealthEndpointTest extends TestCase
{
    use RefreshDatabase;
    use SeedsSignals;

    public function test_a_healthy_source_reports_ok_with_no_reasons(): void
    {
        $source = $this->source('healthy');
        $this->ingestionRun($source, status: 'succeeded', received: 100);

        $row = $this->getJson('/api/v1/sources')->json('data.0');

        $this->assertSame('ok', $row['health']['status']);
        // `ok` with an empty reason list is the only healthy shape, so a check
        // added later cannot pass by accident.
        $this->assertSame([], $row['health']['reasons']);
    }

    public function test_a_failed_run_reports_failing(): void
    {
        $source = $this->source('broken');
        $this->ingestionRun($source, status: 'failed', received: 0, errors: 3);

        $health = $this->getJson('/api/v1/sources')->json('data.0.health');

        $this->assertSame('failing', $health['status']);
        $this->assertContains('Last run failed', $health['reasons']);
    }

    public function test_a_succeeded_but_empty_run_is_degraded_not_ok(): void
    {
        // The quiet failure this page exists for: nothing errors, the run is
        // green, and every score that depended on this source drains away.
        $source = $this->source('silent');
        $this->ingestionRun($source, status: 'succeeded', received: 0);

        $health = $this->getJson('/api/v1/sources')->json('data.0.health');

        $this->assertSame('degraded', $health['status']);
        $this->assertContains('Last run succeeded but received no records', $health['reasons']);
    }

    public function test_a_stale_source_is_flagged_even_though_its_last_run_succeeded(): void
    {
        $source = $this->source('forgotten');
        $this->ingestionRun($source, status: 'succeeded', received: 50, startedAt: now()->subDays(30));

        $health = $this->getJson('/api/v1/sources')->json('data.0.health');

        $this->assertSame('stale', $health['status']);
        $this->assertStringContainsString('No run in over', $health['reasons'][0]);
    }

    public function test_a_run_where_everything_was_rejected_is_failing(): void
    {
        $source = $this->source('rejecting');
        $this->ingestionRun($source, status: 'succeeded', received: 40, rejected: 40);

        $health = $this->getJson('/api/v1/sources')->json('data.0.health');

        $this->assertSame('failing', $health['status']);
        $this->assertContains('Every record in the last run was rejected', $health['reasons']);
    }

    public function test_multiple_problems_are_all_reported(): void
    {
        // Collapsing to whichever check ran first would hide half the problem.
        $source = $this->source('multi');
        $this->ingestionRun($source, status: 'succeeded', received: 0, errors: 2, startedAt: now()->subDays(20));

        $reasons = $this->getJson('/api/v1/sources')->json('data.0.health.reasons');

        $this->assertCount(3, $reasons);
    }

    public function test_a_source_that_never_ran_says_so(): void
    {
        $this->source('never-run');

        $health = $this->getJson('/api/v1/sources')->json('data.0.health');

        $this->assertSame('never_run', $health['status']);
    }

    public function test_disabled_sources_are_hidden_unless_asked_for(): void
    {
        $this->source('live');
        $this->source('retired', ['enabled' => false]);

        $this->getJson('/api/v1/sources')->assertJsonCount(1, 'data');

        $response = $this->getJson('/api/v1/sources?include_disabled=1');
        $response->assertJsonCount(2, 'data');
        $this->assertSame('disabled', collect($response->json('data'))
            ->firstWhere('slug', 'retired')['health']['status']);
    }

    public function test_compliance_posture_travels_with_the_source(): void
    {
        // §11/§42: whether the evidence is usable matters as much as whether it
        // arrived, so terms and personal-data risk are on the health row.
        $this->source('licensed', [
            'terms_status' => 'reviewed',
            'personal_data_risk' => 'low',
            'license' => 'CC-BY-4.0',
        ]);

        $row = $this->getJson('/api/v1/sources')->json('data.0');

        $this->assertSame('reviewed', $row['terms_status']);
        $this->assertSame('low', $row['personal_data_risk']);
        $this->assertSame('CC-BY-4.0', $row['license']);
    }

    public function test_document_counts_come_from_real_rows(): void
    {
        $source = $this->source('counted');
        $this->signal(
            \App\Models\Topic::create(['slug' => 't', 'name' => 'T', 'enabled' => true])->id,
            '2026-08-01',
            sourceSlug: 'counted'
        );

        $this->assertSame(1, $this->getJson('/api/v1/sources')->json('data.0.documents'));
    }

    public function test_ingestion_runs_are_listed_newest_first(): void
    {
        $source = $this->source('logged');
        $this->ingestionRun($source, status: 'succeeded', received: 10, startedAt: now()->subDays(2));
        $this->ingestionRun($source, status: 'failed', received: 0, startedAt: now());

        $runs = $this->getJson('/api/v1/ingestion-runs')->json('data');

        $this->assertSame('failed', $runs[0]['status']);
        $this->assertSame('succeeded', $runs[1]['status']);
        $this->assertSame('logged', $runs[0]['source']);
    }

    public function test_ingestion_runs_filter_by_source_and_status(): void
    {
        $a = $this->source('source-a');
        $b = $this->source('source-b');
        $this->ingestionRun($a, status: 'succeeded', received: 5);
        $this->ingestionRun($b, status: 'failed', received: 0);

        $this->getJson('/api/v1/ingestion-runs?source=source-b')
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.source', 'source-b');

        $this->getJson('/api/v1/ingestion-runs?status=succeeded')
            ->assertJsonCount(1, 'data')
            ->assertJsonPath('data.0.source', 'source-a');
    }

    public function test_ingestion_runs_report_duration(): void
    {
        $source = $this->source('timed');
        IngestionRun::create([
            'source_id' => $source->id,
            'status' => 'succeeded',
            'started_at' => now()->subSeconds(45),
            'finished_at' => now(),
            'records_received' => 10,
        ]);

        $this->assertSame(45, $this->getJson('/api/v1/ingestion-runs')->json('data.0.duration_seconds'));
    }

    private function ingestionRun(
        Source $source,
        string $status,
        int $received,
        int $rejected = 0,
        int $errors = 0,
        $startedAt = null,
    ): IngestionRun {
        $startedAt = $startedAt ?? now();

        return IngestionRun::create([
            'source_id' => $source->id,
            'status' => $status,
            'started_at' => $startedAt,
            'finished_at' => $startedAt,
            'records_received' => $received,
            'records_inserted' => max(0, $received - $rejected),
            'records_updated' => 0,
            'records_rejected' => $rejected,
            'error_count' => $errors,
        ]);
    }
}
