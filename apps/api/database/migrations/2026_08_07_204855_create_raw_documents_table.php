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
        Schema::create('raw_documents', function (Blueprint $table) {
            $table->ulid('id')->primary();
            $table->foreignId('source_id')->constrained('sources')->cascadeOnDelete();
            $table->string('external_id');
            $table->text('url')->nullable();
            $table->text('title')->nullable();
            $table->longText('body')->nullable();
            $table->timestamp('published_at')->nullable();
            $table->timestamp('collected_at');
            $table->string('content_hash', 64);
            $table->string('language_raw')->nullable();
            $table->string('region_raw')->nullable();
            $table->jsonb('metadata_json')->nullable();
            $table->timestamp('created_at')->useCurrent();

            $table->unique(['source_id', 'external_id']);
            $table->index('content_hash');
            $table->index('published_at');
            $table->index('collected_at');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('raw_documents');
    }
};
