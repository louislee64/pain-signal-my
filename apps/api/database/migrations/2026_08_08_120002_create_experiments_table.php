<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * PROJECT_SPEC.md §21 — the tests run against an opportunity.
     *
     * `hypothesis` and `success_metric` are NOT NULL, which is the whole point
     * of the table. An experiment without a stated hypothesis and a stated bar
     * for success cannot fail: whatever happens gets read as encouraging, and
     * the row becomes a record of effort rather than of evidence. Requiring both
     * up front is what makes a `failed` result mean something later.
     */
    public function up(): void
    {
        Schema::create('experiments', function (Blueprint $table) {
            $table->id();
            $table->foreignId('opportunity_id')->constrained('opportunities')->cascadeOnDelete();

            $table->text('hypothesis');
            $table->string('experiment_type');

            // What would count as success, written before the result is known.
            $table->text('success_metric');

            $table->string('status')->default('planned');

            // Nullable while running. A completed experiment with no result is
            // an inconsistency the model refuses rather than the schema, since
            // "completed" is set by the same request that supplies the result.
            $table->text('result')->nullable();
            $table->boolean('succeeded')->nullable();

            $table->timestamp('started_at')->nullable();
            $table->timestamp('completed_at')->nullable();
            $table->timestamps();

            $table->index('opportunity_id');
            $table->index('status');
        });

        if (Schema::getConnection()->getDriverName() === 'pgsql') {
            \DB::statement("
                ALTER TABLE experiments
                ADD CONSTRAINT experiments_type_check
                CHECK (experiment_type IN (
                    'landing_page', 'customer_interview', 'cold_outreach',
                    'manual_service', 'paid_report', 'paid_pilot', 'prototype'
                ))
            ");
            \DB::statement("
                ALTER TABLE experiments
                ADD CONSTRAINT experiments_status_check
                CHECK (status IN ('planned', 'running', 'completed', 'abandoned'))
            ");
        }
    }

    public function down(): void
    {
        Schema::dropIfExists('experiments');
    }
};
