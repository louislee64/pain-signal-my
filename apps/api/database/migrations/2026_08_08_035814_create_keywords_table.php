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
        Schema::create('keywords', function (Blueprint $table) {
            $table->id();
            $table->string('keyword');
            $table->string('keyword_group');
            $table->string('language')->nullable();
            $table->string('geo')->default('MY');
            // 'config'     — declared in config/keywords.yaml, managed by keywords:sync
            // 'discovered' — surfaced by a discovery provider (PROJECT_SPEC.md §15A);
            //                keywords:sync must never touch these.
            $table->string('source')->default('config');
            $table->boolean('enabled')->default(true);
            $table->timestamps();

            $table->unique(['keyword', 'geo']);
            $table->index('keyword_group');
            $table->index('source');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('keywords');
    }
};
