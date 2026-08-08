<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * PROJECT_SPEC.md §21 / §7 Gate 2 — real conversations with real businesses.
     *
     * §21: "Avoid collecting unnecessary personal information."
     * §7 Gate 2: "Do NOT necessarily store identifying personal information."
     *
     * Both are honoured by omission: there is no name, email, phone, or company
     * name column here, and adding one later should require arguing for it. What
     * the scoring model needs is *categories* — which industry, what size of
     * business, what role — and none of those identify a person.
     *
     * The one exception is `company_ref`, and it needs explaining. §7 Gate 3
     * requires "multiple independent businesses confirm the problem", which is a
     * count of distinct businesses — impossible against a schema that cannot
     * distinguish them, and two interviews at the same company are not
     * independent evidence. So `company_ref` is an opaque operator-chosen label
     * ("retailer-a", "kl-cafe-3") whose only job is to tell businesses apart.
     * It is documented as required-to-be-pseudonymous: a value like
     * "Restoran Ali Sdn Bhd" would defeat the point of every other decision in
     * this table.
     */
    public function up(): void
    {
        Schema::create('customer_interviews', function (Blueprint $table) {
            $table->id();
            $table->foreignId('opportunity_id')->constrained('opportunities')->cascadeOnDelete();

            // Pseudonymous business label. Nullable because an interview is
            // still evidence without one — it just cannot contribute to Gate 3's
            // independent-business count.
            $table->string('company_ref', 64)->nullable();

            $table->string('industry')->nullable();
            $table->string('company_size')->nullable();
            $table->string('respondent_role')->nullable();

            // The finding. Nullable is deliberate and distinct from false: "we
            // spoke and they did not have this problem" and "we have not
            // established it yet" are different outcomes, and only the first is
            // a negative result worth acting on.
            $table->boolean('problem_confirmed')->nullable();

            $table->unsignedTinyInteger('frequency_score')->nullable();
            $table->unsignedTinyInteger('severity_score')->nullable();
            $table->unsignedTinyInteger('estimated_cost_score')->nullable();
            $table->unsignedTinyInteger('urgency_score')->nullable();

            $table->text('existing_solution')->nullable();
            $table->text('current_workaround')->nullable();
            $table->string('current_spend_range')->nullable();
            $table->string('existing_budget')->nullable();

            // §7 Gate 3 counts willingness to run a paid pilot as a strong
            // commercial signal, so it is a column rather than buried in notes.
            $table->string('willingness_to_pay')->nullable();
            $table->boolean('pilot_interest')->nullable();

            $table->text('notes')->nullable();
            $table->timestamp('interviewed_at');
            $table->timestamps();

            $table->index('opportunity_id');
            $table->index('problem_confirmed');
            $table->index('interviewed_at');
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('customer_interviews');
    }
};
