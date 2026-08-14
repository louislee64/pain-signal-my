<?php

namespace Tests\Feature;

use App\Models\Source;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Process;
use Tests\TestCase;

/**
 * §38's schedule must not name individual sources — see IngestSourcesCommand.
 */
class IngestSourcesCommandTest extends TestCase
{
    use RefreshDatabase;

    private function source(array $overrides = []): Source
    {
        return Source::create(array_merge([
            'slug' => 'test_feed',
            'name' => 'Test Feed',
            'source_type' => 'news_feed',
            'collector' => 'rss_feed',
            'config' => ['feed_url' => 'https://example.test/feed'],
            'terms_status' => 'unreviewed',
            'personal_data_risk' => 'low',
            'enabled' => true,
        ], $overrides));
    }

    public function test_it_runs_the_collector_for_every_enabled_source(): void
    {
        Process::fake();

        $this->source(['slug' => 'feed_one']);
        $this->source(['slug' => 'feed_two']);

        $this->artisan('sources:ingest')->assertSuccessful();

        Process::assertRan(fn ($process) => str_contains($process->command, 'ingest feed_one'));
        Process::assertRan(fn ($process) => str_contains($process->command, 'ingest feed_two'));
    }

    public function test_it_skips_disabled_sources(): void
    {
        Process::fake();

        $this->source(['slug' => 'live_feed']);
        $this->source(['slug' => 'off_feed', 'enabled' => false]);

        $this->artisan('sources:ingest')->assertSuccessful();

        Process::assertDidntRun(fn ($process) => str_contains($process->command, 'ingest off_feed'));
    }

    public function test_it_can_filter_by_source_type(): void
    {
        Process::fake();

        $this->source(['slug' => 'a_news_feed', 'source_type' => 'news_feed']);
        $this->source(['slug' => 'a_dataset', 'source_type' => 'official_dataset']);

        $this->artisan('sources:ingest --type=news_feed')->assertSuccessful();

        Process::assertRan(fn ($process) => str_contains($process->command, 'ingest a_news_feed'));
        Process::assertDidntRun(fn ($process) => str_contains($process->command, 'ingest a_dataset'));
    }

    public function test_a_filter_matching_nothing_warns_rather_than_claiming_success(): void
    {
        Process::fake();

        $this->source(['slug' => 'a_news_feed']);

        $this->artisan('sources:ingest --type=does_not_exist')
            ->expectsOutputToContain('No enabled sources matched')
            ->assertSuccessful();

        Process::assertNothingRan();
    }

    public function test_one_failing_source_does_not_stop_the_others(): void
    {
        Process::fake([
            '*ingest broken_feed' => Process::result(output: '{"status":"failed"}', exitCode: 1),
            '*' => Process::result(output: '{"status":"succeeded"}'),
        ]);

        $this->source(['slug' => 'broken_feed']);
        $this->source(['slug' => 'working_feed']);

        // Non-zero overall, because a silent partial failure is the thing §41
        // exists to prevent — but the healthy source still ran.
        $this->artisan('sources:ingest')->assertFailed();

        Process::assertRan(fn ($process) => str_contains($process->command, 'ingest working_feed'));
    }

    public function test_it_reports_which_sources_failed(): void
    {
        Process::fake([
            '*ingest broken_feed' => Process::result(output: '', exitCode: 1),
            '*' => Process::result(output: ''),
        ]);

        $this->source(['slug' => 'broken_feed']);

        $this->artisan('sources:ingest')
            ->expectsOutputToContain('broken_feed')
            ->assertFailed();
    }
}
