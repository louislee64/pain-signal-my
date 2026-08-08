<?php

namespace Tests\Feature;

use App\Models\Topic;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class SyncTopicsCommandTest extends TestCase
{
    use RefreshDatabase;

    public function test_it_creates_parent_and_child_topics(): void
    {
        $path = $this->writeRegistry(<<<'YAML'
        topics:
          - slug: billing_invoice
            name: Billing & Invoicing
            description: Test description
            subtopics:
              - slug: einvoice
                name: e-Invoice
        YAML);

        $this->artisan('topics:sync', ['--path' => $path])->assertSuccessful();

        $parent = Topic::where('slug', 'billing_invoice')->firstOrFail();
        $child = Topic::where('slug', 'einvoice')->firstOrFail();

        $this->assertNull($parent->parent_id);
        $this->assertSame($parent->id, $child->parent_id);
        $this->assertTrue($parent->enabled);
    }

    public function test_it_is_idempotent(): void
    {
        $path = $this->writeRegistry(<<<'YAML'
        topics:
          - slug: billing_invoice
            name: Billing & Invoicing
            subtopics:
              - slug: einvoice
                name: e-Invoice
        YAML);

        $this->artisan('topics:sync', ['--path' => $path])->assertSuccessful();
        $this->artisan('topics:sync', ['--path' => $path])->assertSuccessful();

        $this->assertSame(1, Topic::where('slug', 'billing_invoice')->count());
        $this->assertSame(1, Topic::where('slug', 'einvoice')->count());
    }

    public function test_it_disables_topics_removed_from_the_registry(): void
    {
        $path = $this->writeRegistry(<<<'YAML'
        topics:
          - slug: billing_invoice
            name: Billing & Invoicing
        YAML);

        $this->artisan('topics:sync', ['--path' => $path])->assertSuccessful();

        $path = $this->writeRegistry(<<<'YAML'
        topics: []
        YAML);

        $this->artisan('topics:sync', ['--path' => $path])->assertSuccessful();

        $this->assertFalse(Topic::where('slug', 'billing_invoice')->firstOrFail()->enabled);
    }

    private function writeRegistry(string $yaml): string
    {
        $path = tempnam(sys_get_temp_dir(), 'topics').'.yaml';
        file_put_contents($path, $yaml);
        $this->beforeApplicationDestroyed(fn () => @unlink($path));

        return $path;
    }
}
