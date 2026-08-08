<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * §3's commercial funnel and §52's human-in-the-loop rule, as two columns.
     *
     * `status` already existed and stays exactly as it was: human-owned, never
     * written by the scoring pipeline. §52 is unambiguous — "AI suggests. Human
     * approves." A pipeline that promoted an opportunity to PAID_PILOT because
     * the gates happened to pass would be making a commercial decision, and §3
     * says commercial validation requires human evidence.
     *
     * `suggested_status` is what the engine computes from §7's gates. Storing it
     * separately is what makes the suggestion useful without making it
     * authoritative: the dashboard can show "you are at INVESTIGATING; the
     * evidence now supports PROBLEM_VALIDATED" and leave the promotion to a
     * person. Collapsing the two into one column would force a choice between
     * an invisible suggestion and an automatic promotion, and both are wrong.
     *
     * The transition log exists because a funnel with no history cannot answer
     * "when did we decide this, and on what evidence" — which is the question
     * §57 needs answered to recalibrate the weights against real outcomes.
     */
    public function up(): void
    {
        Schema::table('opportunities', function (Blueprint $table) {
            $table->string('suggested_status')->nullable()->after('status');
            $table->timestamp('status_changed_at')->nullable()->after('suggested_status');

            // Why the human promoted (or declined to). Free text on purpose: the
            // reason a call was made is rarely one of five enum values.
            $table->text('status_note')->nullable()->after('status_changed_at');

            $table->index('suggested_status');
        });

        Schema::create('opportunity_stage_transitions', function (Blueprint $table) {
            $table->id();
            $table->foreignId('opportunity_id')->constrained('opportunities')->cascadeOnDelete();

            $table->string('from_status')->nullable();
            $table->string('to_status');

            // What the engine was suggesting at the moment of the decision, so a
            // later reader can see whether the human agreed with it, overrode it,
            // or moved without one.
            $table->string('suggested_status_at_time')->nullable();

            $table->text('note')->nullable();

            // Evidence counts frozen at transition time. Denormalised on purpose:
            // the underlying rows keep changing, and the question this answers is
            // "what did we know when we decided", which a live join can never
            // reconstruct.
            $table->jsonb('evidence_snapshot')->nullable();

            $table->timestamp('created_at')->useCurrent();

            $table->index('opportunity_id');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('opportunity_stage_transitions');

        Schema::table('opportunities', function (Blueprint $table) {
            $table->dropIndex(['suggested_status']);
            $table->dropColumn(['suggested_status', 'status_changed_at', 'status_note']);
        });
    }
};
