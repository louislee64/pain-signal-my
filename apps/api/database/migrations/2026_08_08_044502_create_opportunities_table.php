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
        Schema::create('opportunities', function (Blueprint $table) {
            $table->id();
            $table->foreignId('topic_id')->constrained('topics')->cascadeOnDelete();
            $table->string('title');
            $table->text('description')->nullable();
            $table->foreignId('industry_id')->nullable();
            $table->string('target_buyer')->nullable();

            // Commercial funnel stage (PROJECT_SPEC.md §3). Human-owned: §52 is
            // explicit that AI suggests and a human approves promotion, so
            // nothing in the scoring pipeline may advance this field.
            $table->string('status')->default('observed');

            $table->decimal('pain_score', 5, 2)->nullable();
            $table->decimal('commercial_score', 5, 2)->nullable();
            $table->decimal('opportunity_score', 5, 2)->nullable();

            // Not in §20's field list, but §30 requires confidence to be shown
            // beside opportunity score and §34 requires a recommendation — both
            // are meaningless if they aren't persisted with the scores they
            // describe.
            $table->decimal('confidence_score', 5, 2)->nullable();
            $table->string('recommendation')->nullable();

            // Milestone 4's acceptance criterion is "Each opportunity is
            // explainable through stored evidence." These hold every input
            // value, weight and weighted contribution behind the three scores,
            // so any displayed number can be decomposed without recomputing it
            // — and can still be explained later even after the weights in
            // config/scoring.yaml have moved on.
            $table->jsonb('score_components')->nullable();
            $table->string('scoring_config_version')->nullable();
            $table->timestamp('scored_at')->nullable();

            $table->text('problem_statement')->nullable();
            $table->text('existing_workaround')->nullable();
            $table->text('possible_solution')->nullable();
            $table->string('monetization_model')->nullable();

            $table->timestamps();

            // One opportunity per topic: the engine refreshes in place rather
            // than appending a new row every scoring run.
            $table->unique('topic_id');
            $table->index('status');
            $table->index('opportunity_score');
            $table->index('recommendation');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('opportunities');
    }
};
