<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * §56's ultimate KPI — Opportunity-Generated Revenue.
     *
     * > "This allows answering later: Did the intelligence system actually help
     * > create revenue?"
     *
     * Separate from `commercial_evidence` even though both carry a `value`, and
     * the separation is the point. Evidence records *that something happened*
     * (a proposal was signed, a deposit arrived) as a signal about how real an
     * opportunity is. This records *money received*, as an accounting fact. One
     * proposal worth RM6,000 is one piece of evidence and zero revenue until it
     * is paid; a RM4,500 pilot invoiced monthly is one piece of evidence and
     * many revenue rows.
     *
     * Merging them would make the KPI unanswerable: summing `commercial_evidence
     * .value` counts proposals that never converted, and counts a single pilot
     * once no matter how long it ran.
     */
    public function up(): void
    {
        Schema::create('opportunity_revenue', function (Blueprint $table) {
            $table->id();
            $table->foreignId('opportunity_id')->constrained('opportunities')->cascadeOnDelete();

            $table->string('revenue_type');

            // Money received. Not nullable — a revenue row with no amount is not
            // revenue, it is an intention, and those belong in commercial_evidence.
            $table->decimal('amount', 12, 2);
            $table->string('currency', 3)->default('MYR');

            // §56's field. A category, never a company name — the same
            // personal-data posture as customer_interviews (§21).
            $table->string('customer_type')->nullable();

            // Pseudonymous, so "revenue from how many distinct businesses" is
            // answerable without naming any of them.
            $table->string('company_ref', 64)->nullable();

            $table->text('notes')->nullable();

            // §56 calls this `date`. Named `received_at` because `date` is a
            // reserved word in several engines and reads ambiguously beside
            // `created_at` — is it when it happened or when we typed it in?
            $table->date('received_at');

            $table->timestamps();

            $table->index('opportunity_id');
            $table->index('received_at');
            $table->index('revenue_type');
        });

        if (Schema::getConnection()->getDriverName() === 'pgsql') {
            \DB::statement("
                ALTER TABLE opportunity_revenue
                ADD CONSTRAINT opportunity_revenue_type_check
                CHECK (revenue_type IN (
                    'paid_pilot', 'subscription', 'one_off_project',
                    'retainer', 'paid_report', 'licence', 'other'
                ))
            ");
            // Refunds and corrections are recorded as negative rows, so the
            // constraint is non-zero rather than positive. A zero-amount row is
            // meaningless and would only ever be a mistake.
            \DB::statement('
                ALTER TABLE opportunity_revenue
                ADD CONSTRAINT opportunity_revenue_amount_check
                CHECK (amount <> 0)
            ');
        }
    }

    public function down(): void
    {
        Schema::dropIfExists('opportunity_revenue');
    }
};
