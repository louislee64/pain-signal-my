<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * PROJECT_SPEC.md §21 — every discrete piece of human commercial evidence.
     *
     * This is the table §29's cap exists to wait for. Until a row lands here,
     * an opportunity's score is capped at 79 however good the inferred signals
     * look, because "the internet complains about this" and "someone paid for
     * this" are not the same claim.
     *
     * `evidence_type` is constrained to §21's nine types by a CHECK constraint
     * rather than by application validation alone. The scoring engine weights
     * these types differently (§31's hierarchy: money outranks intent outranks
     * opinion), so an unrecognised type would be silently ignored by the engine
     * while looking like recorded evidence in the UI — the worst of both.
     */
    public function up(): void
    {
        Schema::create('commercial_evidence', function (Blueprint $table) {
            $table->id();
            $table->foreignId('opportunity_id')->constrained('opportunities')->cascadeOnDelete();

            $table->string('evidence_type');

            // §31 ranks evidence rather than counting it. `strength` lets a
            // reader record that this particular proposal was weak without
            // having to reclassify its type.
            $table->string('strength')->default('medium');

            // Money, where money is involved. Nullable because most types have
            // no amount — a customer request is evidence with no value attached,
            // and storing 0 would read as "worth nothing" rather than "n/a".
            $table->decimal('value', 12, 2)->nullable();
            $table->string('currency', 3)->default('MYR');

            // Which business this came from, pseudonymous for the same reason as
            // customer_interviews.company_ref. §7 Gate 5 (repeatability) needs
            // to know a second business paid, not who they are.
            $table->string('company_ref', 64)->nullable();

            $table->text('notes')->nullable();
            $table->timestamp('occurred_at');
            $table->timestamps();

            $table->index('opportunity_id');
            $table->index('evidence_type');
            $table->index('occurred_at');
        });

        // Postgres-only; the sqlite test database ignores it, which is why the
        // model also validates. Belt and braces on purpose: this constraint is
        // what stops a typo from becoming invisible evidence.
        if (Schema::getConnection()->getDriverName() === 'pgsql') {
            \DB::statement("
                ALTER TABLE commercial_evidence
                ADD CONSTRAINT commercial_evidence_type_check
                CHECK (evidence_type IN (
                    'interview', 'proposal', 'pilot_interest', 'paid_pilot',
                    'deposit', 'purchase_order', 'existing_spend',
                    'customer_request', 'repeat_customer'
                ))
            ");
            \DB::statement("
                ALTER TABLE commercial_evidence
                ADD CONSTRAINT commercial_evidence_strength_check
                CHECK (strength IN ('weak', 'medium', 'strong'))
            ");
        }
    }

    public function down(): void
    {
        Schema::dropIfExists('commercial_evidence');
    }
};
