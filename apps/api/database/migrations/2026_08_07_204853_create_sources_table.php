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
        Schema::create('sources', function (Blueprint $table) {
            $table->id();
            $table->string('name');
            $table->string('slug')->unique();
            $table->string('source_type');
            $table->string('base_url')->nullable();
            $table->string('collector');
            $table->jsonb('config')->nullable();
            $table->string('collection_method')->nullable();
            $table->string('rate_limit')->nullable();
            $table->unsignedTinyInteger('reliability_score')->nullable();
            $table->string('license')->nullable();
            $table->string('terms_url')->nullable();
            $table->string('terms_status')->default('unreviewed');
            $table->string('personal_data_risk')->default('unknown');
            $table->boolean('enabled')->default(false);
            $table->timestamp('last_synced_at')->nullable();
            $table->timestamp('last_dataset_updated_at')->nullable();
            $table->timestamps();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('sources');
    }
};
