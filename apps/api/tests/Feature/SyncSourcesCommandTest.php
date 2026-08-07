<?php

namespace Tests\Feature;

use App\Models\Source;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class SyncSourcesCommandTest extends TestCase
{
    use RefreshDatabase;

    public function test_it_upserts_sources_from_yaml(): void
    {
        $path = $this->writeRegistry(<<<'YAML'
        sources:
          - slug: test_source
            name: Test Source
            source_type: official_dataset
            base_url: "https://example.test"
            collector: test_collector
            config:
              dataset_id: widgets
            rate_limit: "1/minute"
            reliability_score: 80
            terms_status: reviewed
            personal_data_risk: none
            enabled: true
        YAML);

        $this->artisan('sources:sync', ['--path' => $path])->assertSuccessful();

        $source = Source::where('slug', 'test_source')->firstOrFail();

        $this->assertSame('Test Source', $source->name);
        $this->assertSame('test_collector', $source->collector);
        $this->assertSame(['dataset_id' => 'widgets'], $source->config);
        $this->assertTrue($source->enabled);
    }

    public function test_it_updates_existing_source_rather_than_duplicating(): void
    {
        $path = $this->writeRegistry(<<<'YAML'
        sources:
          - slug: test_source
            name: Original Name
            source_type: official_dataset
            collector: test_collector
            enabled: true
        YAML);

        $this->artisan('sources:sync', ['--path' => $path])->assertSuccessful();

        $path = $this->writeRegistry(<<<'YAML'
        sources:
          - slug: test_source
            name: Renamed
            source_type: official_dataset
            collector: test_collector
            enabled: true
        YAML);

        $this->artisan('sources:sync', ['--path' => $path])->assertSuccessful();

        $this->assertSame(1, Source::where('slug', 'test_source')->count());
        $this->assertSame('Renamed', Source::where('slug', 'test_source')->firstOrFail()->name);
    }

    public function test_it_disables_sources_removed_from_the_registry(): void
    {
        $path = $this->writeRegistry(<<<'YAML'
        sources:
          - slug: test_source
            name: Test Source
            source_type: official_dataset
            collector: test_collector
            enabled: true
        YAML);

        $this->artisan('sources:sync', ['--path' => $path])->assertSuccessful();

        $path = $this->writeRegistry(<<<'YAML'
        sources: []
        YAML);

        $this->artisan('sources:sync', ['--path' => $path])->assertSuccessful();

        $this->assertFalse(Source::where('slug', 'test_source')->firstOrFail()->enabled);
    }

    private function writeRegistry(string $yaml): string
    {
        $path = tempnam(sys_get_temp_dir(), 'sources').'.yaml';
        file_put_contents($path, $yaml);
        $this->beforeApplicationDestroyed(fn () => @unlink($path));

        return $path;
    }
}
