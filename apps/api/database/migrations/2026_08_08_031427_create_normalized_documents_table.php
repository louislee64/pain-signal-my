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
        Schema::create('normalized_documents', function (Blueprint $table) {
            $table->id();
            $table->ulid('raw_document_id')->unique();
            $table->foreign('raw_document_id')->references('id')->on('raw_documents')->cascadeOnDelete();
            $table->longText('cleaned_text')->nullable();
            $table->string('language')->nullable();
            $table->string('country')->nullable();
            $table->string('state')->nullable();
            $table->string('city')->nullable();
            $table->foreignId('industry_id')->nullable();
            $table->string('normalized_content_hash', 64)->nullable();
            $table->foreignId('duplicate_of_normalized_document_id')->nullable()
                ->constrained('normalized_documents')->nullOnDelete();
            $table->timestamp('processed_at');

            $table->index('language');
            $table->index('state');
            $table->index('normalized_content_hash');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('normalized_documents');
    }
};
