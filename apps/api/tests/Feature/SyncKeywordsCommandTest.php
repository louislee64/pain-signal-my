<?php

namespace Tests\Feature;

use App\Models\Keyword;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class SyncKeywordsCommandTest extends TestCase
{
    use RefreshDatabase;

    public function test_it_creates_keywords_grouped_by_cluster_and_language(): void
    {
        $path = $this->writeRegistry(<<<'YAML'
        groups:
          sme_finance:
            en:
              - invoice software
            ms:
              - sistem invois
            zh:
              - 会计软件
        YAML);

        $this->artisan('keywords:sync', ['--path' => $path])->assertSuccessful();

        $this->assertSame(3, Keyword::count());

        $english = Keyword::where('keyword', 'invoice software')->firstOrFail();
        $this->assertSame('sme_finance', $english->keyword_group);
        $this->assertSame('en', $english->language);
        $this->assertSame('MY', $english->geo);
        $this->assertSame(Keyword::SOURCE_CONFIG, $english->source);
        $this->assertTrue($english->enabled);

        $this->assertSame('zh', Keyword::where('keyword', '会计软件')->firstOrFail()->language);
    }

    public function test_it_is_idempotent(): void
    {
        $path = $this->writeRegistry(<<<'YAML'
        groups:
          inventory:
            en:
              - stock count
        YAML);

        $this->artisan('keywords:sync', ['--path' => $path])->assertSuccessful();
        $this->artisan('keywords:sync', ['--path' => $path])->assertSuccessful();

        $this->assertSame(1, Keyword::where('keyword', 'stock count')->count());
    }

    public function test_it_disables_config_keywords_removed_from_the_registry(): void
    {
        $path = $this->writeRegistry(<<<'YAML'
        groups:
          inventory:
            en:
              - stock count
        YAML);
        $this->artisan('keywords:sync', ['--path' => $path])->assertSuccessful();

        $path = $this->writeRegistry(<<<'YAML'
        groups: {}
        YAML);
        $this->artisan('keywords:sync', ['--path' => $path])->assertSuccessful();

        $this->assertFalse(Keyword::where('keyword', 'stock count')->firstOrFail()->enabled);
    }

    public function test_it_leaves_discovered_keywords_untouched(): void
    {
        Keyword::create([
            'keyword' => 'surfaced by discovery',
            'keyword_group' => 'discovered',
            'geo' => 'MY',
            'source' => Keyword::SOURCE_DISCOVERED,
            'enabled' => true,
        ]);

        $path = $this->writeRegistry(<<<'YAML'
        groups: {}
        YAML);
        $this->artisan('keywords:sync', ['--path' => $path])->assertSuccessful();

        $discovered = Keyword::where('keyword', 'surfaced by discovery')->firstOrFail();
        $this->assertTrue($discovered->enabled, 'keywords:sync must not disable discovered keywords');
    }

    private function writeRegistry(string $yaml): string
    {
        $path = tempnam(sys_get_temp_dir(), 'keywords').'.yaml';
        file_put_contents($path, $yaml);
        $this->beforeApplicationDestroyed(fn () => @unlink($path));

        return $path;
    }
}
