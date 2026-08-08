<?php

namespace App\Console\Commands;

use App\Models\Topic;
use Illuminate\Console\Command;
use Symfony\Component\Yaml\Yaml;

class SyncTopicsCommand extends Command
{
    protected $signature = 'topics:sync {--path= : Override the topics.yaml path}';

    protected $description = 'Upsert config/topics.yaml into the topics table (taxonomy, PROJECT_SPEC.md §4)';

    public function handle(): int
    {
        $path = $this->option('path') ?: env('TOPICS_REGISTRY_PATH', '/config/topics.yaml');

        if (! is_file($path)) {
            $this->error("Topics registry not found at {$path}");

            return self::FAILURE;
        }

        $definitions = Yaml::parseFile($path)['topics'] ?? [];

        $seenSlugs = [];

        foreach ($definitions as $definition) {
            $parent = $this->upsert($definition, null);
            $seenSlugs[] = $parent->slug;

            foreach ($definition['subtopics'] ?? [] as $subtopic) {
                $child = $this->upsert($subtopic, $parent->id);
                $seenSlugs[] = $child->slug;
            }
        }

        $disabled = Topic::whereNotIn('slug', $seenSlugs)->where('enabled', true)->update(['enabled' => false]);

        if ($disabled > 0) {
            $this->warn("Disabled {$disabled} topic(s) no longer present in the registry.");
        }

        $this->info('Synced '.count($seenSlugs).' topic(s).');

        return self::SUCCESS;
    }

    private function upsert(array $definition, ?int $parentId): Topic
    {
        return Topic::updateOrCreate(
            ['slug' => $definition['slug']],
            [
                'parent_id' => $parentId,
                'name' => $definition['name'],
                'description' => $definition['description'] ?? null,
                'enabled' => $definition['enabled'] ?? true,
            ]
        );
    }
}
