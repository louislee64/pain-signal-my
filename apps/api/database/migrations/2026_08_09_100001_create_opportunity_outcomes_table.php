<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * §58's outcome dataset — "training data for future scoring improvements".
     *
     * The row that closes §57's loop. Everything else in this system measures
     * what the world said; this records what actually happened when the
     * developer went and tried to sell something, and whether the score was
     * right.
     *
     * `initial_score` is the single most important column and the one easiest to
     * get wrong. It is the score the system gave **at the moment the developer
     * decided to investigate** — frozen here, never read live. Reading it live
     * would destroy the dataset's entire purpose: the score moves as evidence
     * accumulates, so by the time an outcome is recorded the score has already
     * been dragged toward the answer, and comparing them would measure nothing.
     *
     * The counted fields (`buyer_interviews`, `paid_pilots`, …) are likewise
     * frozen rather than joined. Same reason: they are what was true when the
     * call was made.
     */
    public function up(): void
    {
        Schema::create('opportunity_outcomes', function (Blueprint $table) {
            $table->id();
            $table->foreignId('opportunity_id')->constrained('opportunities')->cascadeOnDelete();

            // What the system predicted, frozen.
            $table->decimal('initial_score', 5, 2)->nullable();
            $table->decimal('initial_pain_score', 5, 2)->nullable();
            $table->decimal('initial_commercial_score', 5, 2)->nullable();
            $table->decimal('initial_confidence_score', 5, 2)->nullable();

            // The dimension breakdown behind that score, so §57 can ask *which*
            // assumption was wrong rather than only *that* one was. Copied
            // rather than referenced: config/scoring.yaml's weights are expected
            // to change, and this must survive that.
            $table->jsonb('initial_score_components')->nullable();
            $table->string('scoring_config_version')->nullable();

            // §58's counted fields.
            $table->unsignedInteger('buyer_interviews')->default(0);
            $table->unsignedInteger('confirmed_buyers')->default(0);
            $table->unsignedInteger('proposals_sent')->default(0);
            $table->unsignedInteger('paid_pilots')->default(0);
            $table->unsignedInteger('customers')->default(0);
            $table->decimal('revenue', 12, 2)->default(0);
            $table->string('currency', 3)->default('MYR');

            $table->string('outcome');

            // Free text, and required by the model rather than the schema. §58
            // lists nine outcome categories; the reason is where the thing that
            // does not fit a category gets recorded, and that is usually the
            // part worth reading a year later.
            $table->text('reason')->nullable();

            $table->date('concluded_at');
            $table->timestamps();

            // One outcome per opportunity. Concluding twice means the first
            // conclusion was wrong, which is an edit rather than a second row.
            $table->unique('opportunity_id');
            $table->index('outcome');
            $table->index('concluded_at');
        });

        if (Schema::getConnection()->getDriverName() === 'pgsql') {
            \DB::statement("
                ALTER TABLE opportunity_outcomes
                ADD CONSTRAINT opportunity_outcomes_outcome_check
                CHECK (outcome IN (
                    'successful', 'promising', 'no_budget', 'low_urgency',
                    'already_solved', 'poor_fit', 'too_complex', 'regulatory',
                    'false_signal'
                ))
            ");
        }
    }

    public function down(): void
    {
        Schema::dropIfExists('opportunity_outcomes');
    }
};
