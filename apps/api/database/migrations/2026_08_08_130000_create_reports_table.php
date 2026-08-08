<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * §39's weekly report, and §55's "report history".
     *
     * Milestone 7's acceptance criterion is that generation is "automatic and
     * reproducible from stored data", and this table is where reproducible gets
     * decided.
     *
     * The report is stored three ways, and each one is load-bearing:
     *
     *  - `sections` (JSONB) — the structured findings, so the web UI and any
     *    future consumer read the same data rather than parsing prose.
     *  - `markdown` — the rendered document, frozen. A report that re-rendered
     *    from live data on every view would change under the reader, which
     *    makes it useless as a record of what was decided and when.
     *  - `inputs` — the config versions and row counts the report was built
     *    from. Without them "reproducible" is unfalsifiable: you cannot tell a
     *    genuine regeneration from a coincidence.
     *
     * `content_hash` is over the structured sections, so regenerating the same
     * period can be *proved* to have produced the same answer rather than
     * assumed to.
     */
    public function up(): void
    {
        Schema::create('reports', function (Blueprint $table) {
            $table->id();

            $table->string('report_type')->default('weekly');

            // The window is closed and explicit. Every query in the builder is
            // bounded by these dates rather than by "now", which is the whole
            // mechanism behind reproducibility — a report for last week must not
            // change because this week's data arrived.
            $table->date('period_start');
            $table->date('period_end');

            $table->string('title');
            $table->jsonb('sections');
            $table->longText('markdown');

            // What the report was built from: scoring config version, engine
            // versions, and the counts of each input table inside the window.
            $table->jsonb('inputs')->nullable();

            $table->string('content_hash', 64);

            $table->timestamp('generated_at');
            $table->timestamps();

            // One report per type per period. Regenerating replaces in place
            // rather than appending, so "report history" is a history of
            // periods, not of attempts.
            $table->unique(['report_type', 'period_start', 'period_end'], 'reports_type_period_unique');
            $table->index('period_start');
            $table->index('generated_at');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('reports');
    }
};
