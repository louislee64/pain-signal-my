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
        Schema::create('document_topics', function (Blueprint $table) {
            $table->id();
            $table->foreignId('document_id')->constrained('normalized_documents')->cascadeOnDelete();
            $table->foreignId('topic_id')->constrained('topics')->cascadeOnDelete();
            $table->unsignedTinyInteger('confidence');
            $table->string('classification_method');
            $table->string('model_version')->nullable();
            $table->timestamps();

            $table->unique(['document_id', 'topic_id', 'classification_method']);
            $table->index('topic_id');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('document_topics');
    }
};
