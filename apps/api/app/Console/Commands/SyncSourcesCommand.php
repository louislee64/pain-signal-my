<?php

namespace App\Console\Commands;

use App\Models\Source;
use Illuminate\Console\Command;
use Symfony\Component\Yaml\Yaml;

class SyncSourcesCommand extends Command
{
    protected $signature = 'sources:sync {--path= : Override the sources.yaml path}';

    protected $description = 'Upsert config/sources.yaml into the sources table (source registry, PROJECT_SPEC.md §12)';

    public function handle(): int
    {
        $path = $this->option('path') ?: env('SOURCES_REGISTRY_PATH', '/config/sources.yaml');

        if (! is_file($path)) {
            $this->error("Sources registry not found at {$path}");

            return self::FAILURE;
        }

        $definitions = Yaml::parseFile($path)['sources'] ?? [];

        $seenSlugs = [];

        foreach ($definitions as $definition) {
            $slug = $definition['slug'];
            $seenSlugs[] = $slug;

            Source::updateOrCreate(
                ['slug' => $slug],
                [
                    'name' => $definition['name'],
                    'source_type' => $definition['source_type'],
                    'base_url' => $definition['base_url'] ?? null,
                    'collector' => $definition['collector'],
                    'config' => $definition['config'] ?? [],
                    'collection_method' => $definition['collection_method'] ?? null,
                    'rate_limit' => $definition['rate_limit'] ?? null,
                    'reliability_score' => $definition['reliability_score'] ?? null,
                    'license' => $definition['license'] ?? null,
                    'terms_url' => $definition['terms_url'] ?? null,
                    'terms_status' => $definition['terms_status'] ?? 'unreviewed',
                    'personal_data_risk' => $definition['personal_data_risk'] ?? 'unknown',
                    'enabled' => $definition['enabled'] ?? false,
                ]
            );

            $this->info("Synced source: {$slug}");
        }

        $disabled = Source::whereNotIn('slug', $seenSlugs)->where('enabled', true)->update(['enabled' => false]);

        if ($disabled > 0) {
            $this->warn("Disabled {$disabled} source(s) no longer present in the registry.");
        }

        return self::SUCCESS;
    }
}
