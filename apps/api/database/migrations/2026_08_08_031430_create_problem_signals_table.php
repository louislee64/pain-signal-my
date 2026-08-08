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
        Schema::create('problem_signals', function (Blueprint $table) {
            $table->id();
            $table->foreignId('document_id')->constrained('normalized_documents')->cascadeOnDelete();
            $table->foreignId('topic_id')->constrained('topics')->cascadeOnDelete();
            $table->date('signal_date');
            $table->string('region')->nullable();
            $table->foreignId('industry_id')->nullable();
            $table->unsignedTinyInteger('severity_score')->nullable();
            $table->unsignedTinyInteger('urgency_score')->nullable();
            $table->unsignedTinyInteger('economic_impact_score')->nullable();
            $table->string('frequency_hint')->nullable();
            $table->string('payer_type')->nullable();
            $table->jsonb('evidence_json')->nullable();
            $table->string('classification_method');
            $table->timestamps();

            $table->unique(['document_id', 'topic_id', 'classification_method']);
            $table->index('signal_date');
            $table->index('topic_id');
            $table->index('region');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('problem_signals');
    }
};
