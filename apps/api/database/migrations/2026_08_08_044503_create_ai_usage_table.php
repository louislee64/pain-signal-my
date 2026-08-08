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
        // PROJECT_SPEC.md §44. Every LLM call is recorded here before its result
        // is used, so spend is always answerable per source, document, provider
        // and model — and so the daily/monthly budget guard has something real
        // to check rather than an estimate.
        Schema::create('ai_usage', function (Blueprint $table) {
            $table->id();
            $table->string('provider');
            $table->string('model');
            $table->string('operation');
            $table->unsignedInteger('input_tokens')->default(0);
            $table->unsignedInteger('output_tokens')->default(0);

            // 6 decimal places: per-document calls on cheap models cost
            // fractions of a cent, and rounding them to 2dp would floor a real
            // bill to zero.
            $table->decimal('estimated_cost', 12, 6)->default(0);
            $table->string('currency', 3)->default('USD');

            $table->ulid('document_id')->nullable();
            $table->foreign('document_id')->references('id')->on('raw_documents')->nullOnDelete();

            // Which prompt and pipeline version produced this (§70), so a
            // regression can be traced to the change that caused it.
            $table->string('prompt_version')->nullable();
            $table->string('processing_version')->nullable();

            $table->boolean('succeeded')->default(true);
            $table->text('error')->nullable();

            $table->timestamp('created_at')->useCurrent();

            $table->index('created_at');
            $table->index(['provider', 'model']);
            $table->index('operation');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('ai_usage');
    }
};
