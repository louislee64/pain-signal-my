<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::create('trend_metrics', function (Blueprint $table) {
            $table->id();
            $table->date('date');
            $table->foreignId('keyword_id')->constrained('keywords')->cascadeOnDelete();
            $table->string('country')->default('MY');
            // Not nullable for the same reason as topic_daily_metrics.region:
            // Postgres treats NULL as distinct per row in a unique constraint,
            // which would allow unlimited duplicate "no sub-region" rows.
            // '' means national-level (no sub-region breakdown).
            $table->string('region')->default('');

            // Relative interest, 0-100, NEVER absolute search volume
            // (PROJECT_SPEC.md §16). Comparable only within one collection
            // batch for one keyword set — see docs/data-model.md.
            $table->unsignedSmallInteger('interest');

            $table->decimal('rolling_7d', 6, 2)->nullable();
            $table->decimal('rolling_30d', 6, 2)->nullable();
            $table->decimal('baseline_90d', 6, 2)->nullable();
            $table->decimal('growth_7d', 8, 2)->nullable();
            $table->decimal('growth_30d', 8, 2)->nullable();
            $table->decimal('growth_score', 8, 4)->nullable();
            $table->decimal('z_score', 8, 4)->nullable();

            // Provenance (PROJECT_SPEC.md §16/§41): which adapter produced this
            // row, and which single collection run it belonged to. Trends values
            // are only comparable within a batch, so this is not optional metadata.
            $table->string('collection_method');
            $table->string('collection_batch', 26);

            $table->timestamps();

            $table->unique(['keyword_id', 'date', 'region']);
            $table->index('date');
            $table->index('collection_batch');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('trend_metrics');
    }
};
