<?php

namespace App\Console\Commands;

use App\Models\Keyword;
use Illuminate\Console\Command;
use Symfony\Component\Yaml\Yaml;

class SyncKeywordsCommand extends Command
{
    protected $signature = 'keywords:sync {--path= : Override the keywords.yaml path}';

    protected $description = 'Upsert config/keywords.yaml into the keywords table (PROJECT_SPEC.md §15B)';

    public function handle(): int
    {
        $path = $this->option('path') ?: env('KEYWORDS_REGISTRY_PATH', '/config/keywords.yaml');

        if (! is_file($path)) {
            $this->error("Keywords registry not found at {$path}");

            return self::FAILURE;
        }

        $groups = Yaml::parseFile($path)['groups'] ?? [];
        $geo = 'MY';
        $seen = [];

        foreach ($groups as $groupName => $byLanguage) {
            foreach ($byLanguage as $language => $keywords) {
                foreach ($keywords as $keyword) {
                    Keyword::updateOrCreate(
                        ['keyword' => $keyword, 'geo' => $geo],
                        [
                            'keyword_group' => $groupName,
                            'language' => $language,
                            'source' => Keyword::SOURCE_CONFIG,
                            'enabled' => true,
                        ]
                    );

                    $seen[] = $keyword;
                }
            }
        }

        // Only config-sourced keywords are managed here. Keywords surfaced by a
        // discovery provider (§15A) are deliberately left alone — they were never
        // in this file, so their absence from it means nothing.
        $disabled = Keyword::where('source', Keyword::SOURCE_CONFIG)
            ->where('enabled', true)
            ->whereNotIn('keyword', $seen)
            ->update(['enabled' => false]);

        if ($disabled > 0) {
            $this->warn("Disabled {$disabled} keyword(s) no longer present in the registry.");
        }

        $this->info('Synced '.count($seen).' keyword(s) across '.count($groups).' group(s).');

        return self::SUCCESS;
    }
}
