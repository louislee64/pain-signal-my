<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * §40's alerts, and the record of which have already been sent.
     *
     * The record is the point of the table. §40's conditions are standing facts
     * ("opportunity reaches SELL_PILOT"), not events — evaluate them on a
     * schedule and every run re-fires every alert that is still true. An alert
     * channel that repeats itself daily gets muted within a week, and then the
     * one alert that mattered goes unread.
     *
     * `dedupe_key` is what makes an alert fire once. It encodes the condition
     * plus whatever makes this instance distinct (which opportunity, which
     * threshold crossed), so "score crossed 70" and a later "score crossed 80"
     * are different alerts while the first one staying true is not.
     */
    public function up(): void
    {
        Schema::create('alerts', function (Blueprint $table) {
            $table->id();

            $table->string('alert_type');
            $table->string('severity')->default('info');

            $table->foreignId('opportunity_id')->nullable()
                ->constrained('opportunities')->nullOnDelete();

            $table->string('title');
            $table->text('body');

            // The figures behind the alert, so a reader can judge it without
            // going to look — and so a later reader can see what was true at
            // the time even if the score has since moved.
            $table->jsonb('context')->nullable();

            $table->string('dedupe_key');

            // Delivery is recorded separately from detection: an alert that was
            // detected but failed to send is a different state from one never
            // detected, and only the first should be retried.
            $table->timestamp('detected_at');
            $table->timestamp('delivered_at')->nullable();
            $table->string('delivered_via')->nullable();
            $table->text('delivery_error')->nullable();

            $table->timestamps();

            $table->unique('dedupe_key');
            $table->index('alert_type');
            $table->index('detected_at');
            $table->index('delivered_at');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('alerts');
    }
};
