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
        Schema::create('topic_daily_metrics', function (Blueprint $table) {
            $table->id();
            $table->date('date');
            $table->foreignId('topic_id')->constrained('topics')->cascadeOnDelete();
            // Not nullable: Postgres unique constraints treat NULL as distinct
            // per-row, which would let unlimited "no region" rows through for
            // the same date+topic. '' means "no region breakdown" (national).
            $table->string('region')->default('');
            $table->foreignId('industry_id')->nullable();
            $table->unsignedInteger('mention_count')->default(0);
            $table->unsignedInteger('source_count')->default(0);
            $table->decimal('avg_severity', 5, 2)->nullable();
            $table->decimal('avg_urgency', 5, 2)->nullable();
            $table->decimal('trend_score', 5, 2)->nullable();
            $table->decimal('official_score', 5, 2)->nullable();
            $table->decimal('pain_score', 5, 2)->nullable();
            $table->decimal('commercial_score', 5, 2)->nullable();
            $table->decimal('opportunity_score', 5, 2)->nullable();
            $table->timestamps();

            $table->unique(['date', 'topic_id', 'region'], 'topic_daily_metrics_date_topic_region_unique');
            $table->index('date');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('topic_daily_metrics');
    }
};
