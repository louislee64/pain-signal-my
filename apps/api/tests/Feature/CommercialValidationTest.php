<?php

namespace Tests\Feature;

use App\Models\CommercialEvidence;
use App\Models\CustomerInterview;
use App\Models\Experiment;
use App\Models\Opportunity;
use App\Models\Topic;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class CommercialValidationTest extends TestCase
{
    use RefreshDatabase;

    // ---------------------------------------------------------------- personal data

    public function test_the_interviews_table_holds_no_identifying_columns(): void
    {
        // §21: "Avoid collecting unnecessary personal information."
        // §7 Gate 2: "Do NOT necessarily store identifying personal information."
        //
        // Asserted against the schema rather than trusted to review, because a
        // column added in a hurry is exactly how this posture gets lost.
        $columns = \Schema::getColumnListing('customer_interviews');

        foreach (['name', 'email', 'phone', 'company_name', 'contact', 'address'] as $forbidden) {
            $this->assertNotContains($forbidden, $columns, "customer_interviews must not store {$forbidden}");
        }
    }

    public function test_company_ref_rejects_anything_that_looks_like_an_identity(): void
    {
        $opportunity = $this->opportunity();

        // The pseudonymity of this field is what the rest of the table's
        // personal-data posture rests on.
        $this->postJson("/api/v1/opportunities/{$opportunity->id}/interviews", [
            'company_ref' => 'Restoran Ali Sdn Bhd (ali@example.com)',
            'interviewed_at' => '2026-08-01',
        ])->assertStatus(422)->assertJsonValidationErrors('company_ref');
    }

    public function test_company_ref_accepts_a_pseudonymous_label(): void
    {
        $opportunity = $this->opportunity();

        $this->postJson("/api/v1/opportunities/{$opportunity->id}/interviews", [
            'company_ref' => 'retailer-a',
            'interviewed_at' => '2026-08-01',
        ])->assertCreated();
    }

    // ---------------------------------------------------------------- interviews

    public function test_recording_an_interview_never_moves_the_stage(): void
    {
        // §52: "AI suggests. Human approves." Evidence arriving must update the
        // suggestion and nothing else.
        $opportunity = $this->opportunity(['status' => 'observed']);

        $response = $this->postJson("/api/v1/opportunities/{$opportunity->id}/interviews", [
            'company_ref' => 'retailer-a',
            'problem_confirmed' => true,
            'interviewed_at' => '2026-08-01',
        ]);

        $response->assertCreated();
        $this->assertSame('observed', $opportunity->fresh()->status);
        $this->assertSame('problem_validated', $opportunity->fresh()->suggested_status);
        $this->assertTrue($response->json('meta.suggestion_is_ahead'));
    }

    public function test_a_declined_problem_is_recorded_as_a_finding_not_a_blank(): void
    {
        $opportunity = $this->opportunity();

        $this->postJson("/api/v1/opportunities/{$opportunity->id}/interviews", [
            'company_ref' => 'retailer-a',
            'problem_confirmed' => false,
            'interviewed_at' => '2026-08-01',
        ])->assertCreated();

        $summary = $opportunity->fresh()->evidenceSummary();

        // "They said no" and "we have not asked" must not collapse into each
        // other: only the first is a negative result worth acting on.
        $this->assertSame(1, $summary['interview_count']);
        $this->assertSame(0, $summary['problem_confirmed_count']);
        $this->assertSame(1, $summary['problem_denied_count']);
    }

    public function test_interviewed_at_is_required(): void
    {
        $opportunity = $this->opportunity();

        $this->postJson("/api/v1/opportunities/{$opportunity->id}/interviews", [
            'problem_confirmed' => true,
        ])->assertStatus(422)->assertJsonValidationErrors('interviewed_at');
    }

    // ------------------------------------------------- independent businesses

    public function test_two_interviews_at_one_company_are_one_independent_confirmation(): void
    {
        // §7 Gate 3 asks for independent *businesses*. Two conversations at the
        // same company are one company's opinion, and counting them as two would
        // let a single enthusiastic customer clear the gate alone.
        $opportunity = $this->opportunity();
        $this->confirmInterview($opportunity, 'retailer-a');
        $this->confirmInterview($opportunity, 'retailer-a');

        $summary = $opportunity->fresh()->evidenceSummary();

        $this->assertSame(2, $summary['problem_confirmed_count']);
        $this->assertSame(1, $summary['independent_confirmations']);
    }

    public function test_an_interview_without_a_company_ref_cannot_prove_independence(): void
    {
        $opportunity = $this->opportunity();
        $this->confirmInterview($opportunity, null);
        $this->confirmInterview($opportunity, null);

        $summary = $opportunity->fresh()->evidenceSummary();

        // Still evidence for Gate 2, which needs one confirmation. Not evidence
        // of independence, which is what Gate 3 counts.
        $this->assertSame(2, $summary['problem_confirmed_count']);
        $this->assertSame(0, $summary['independent_confirmations']);
    }

    // ---------------------------------------------------------------- evidence

    public function test_evidence_type_must_be_one_of_spec_21s_nine(): void
    {
        $opportunity = $this->opportunity();

        // An unrecognised type would be ignored by the scoring engine while
        // looking like recorded evidence in the UI — the worst of both.
        $this->postJson("/api/v1/opportunities/{$opportunity->id}/evidence", [
            'evidence_type' => 'they_seemed_keen',
            'occurred_at' => '2026-08-01',
        ])->assertStatus(422)->assertJsonValidationErrors('evidence_type');
    }

    public function test_paid_evidence_without_a_value_or_company_warns(): void
    {
        $opportunity = $this->opportunity();

        $response = $this->postJson("/api/v1/opportunities/{$opportunity->id}/evidence", [
            'evidence_type' => 'paid_pilot',
            'occurred_at' => '2026-08-01',
        ]);

        $response->assertCreated();
        // Allowed, because refusing would lose the fact that a payment happened.
        // Warned, because §29's bonus and Gate 5 both read these rows.
        $warnings = $response->json('meta.warnings');
        $this->assertCount(2, $warnings);
    }

    public function test_pilot_interest_is_not_a_strong_commercial_signal(): void
    {
        // §7 Gate 4: a customer paying is "considerably more valuable than
        // 'I would probably use this'".
        $opportunity = $this->opportunity();
        $this->evidence($opportunity, 'pilot_interest');

        $this->assertFalse($opportunity->fresh()->evidenceSummary()['has_strong_commercial_signal']);

        $this->evidence($opportunity, 'proposal');
        $this->assertTrue($opportunity->fresh()->evidenceSummary()['has_strong_commercial_signal']);
    }

    public function test_paying_businesses_are_counted_distinctly(): void
    {
        // §7 Gate 5 wants a second paying business. Two pilots with the same
        // customer prove retention, not repeatability.
        $opportunity = $this->opportunity();
        $this->evidence($opportunity, 'paid_pilot', 'retailer-a');
        $this->evidence($opportunity, 'paid_pilot', 'retailer-a');

        $summary = $opportunity->fresh()->evidenceSummary();
        $this->assertSame(2, $summary['paid_pilot_count']);
        $this->assertSame(1, $summary['paying_business_count']);

        $this->evidence($opportunity, 'paid_pilot', 'retailer-b');
        $this->assertSame(2, $opportunity->fresh()->evidenceSummary()['paying_business_count']);
    }

    // ---------------------------------------------------------------- experiments

    public function test_an_experiment_requires_a_hypothesis_and_a_success_metric(): void
    {
        // An experiment with no stated bar for success cannot fail, so the row
        // records effort rather than evidence.
        $opportunity = $this->opportunity();

        $this->postJson("/api/v1/opportunities/{$opportunity->id}/experiments", [
            'experiment_type' => 'landing_page',
        ])->assertStatus(422)->assertJsonValidationErrors(['hypothesis', 'success_metric']);
    }

    public function test_a_completed_experiment_requires_a_result(): void
    {
        $opportunity = $this->opportunity();

        $this->postJson("/api/v1/opportunities/{$opportunity->id}/experiments", [
            'hypothesis' => 'SMEs will sign up for a reconciliation tool',
            'success_metric' => '10 signups in 2 weeks',
            'experiment_type' => 'landing_page',
            'status' => 'completed',
        ])->assertStatus(422);
    }

    public function test_an_experiment_can_be_planned_then_concluded(): void
    {
        // The useful sequence is plan → run → conclude. Requiring the result up
        // front would push people to create the row afterwards, losing the
        // hypothesis — the part worth recording before you know the answer.
        $opportunity = $this->opportunity();

        $created = $this->postJson("/api/v1/opportunities/{$opportunity->id}/experiments", [
            'hypothesis' => 'SMEs will pay for a reconciliation tool',
            'success_metric' => '3 paid pilots in a month',
            'experiment_type' => 'cold_outreach',
            'status' => 'running',
            'started_at' => '2026-08-01',
        ])->assertCreated();

        $id = $created->json('data.id');

        $this->patchJson("/api/v1/opportunities/{$opportunity->id}/experiments/{$id}", [
            'status' => 'completed',
            'result' => '1 paid pilot, 2 declined on price',
            'succeeded' => false,
            'completed_at' => '2026-08-20',
        ])->assertOk()->assertJsonPath('data.succeeded', false);
    }

    // ---------------------------------------------------------------- gates

    public function test_gate_1_needs_a_recorded_buyer_hypothesis(): void
    {
        $opportunity = $this->opportunity(['target_buyer' => null]);

        $blocked = $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'buyer_identified',
        ]);

        $blocked->assertStatus(422);
        // The reason matters more than the refusal: it tells someone what to do.
        $this->assertStringContainsString('Gate 1', $blocked->json('error'));

        $opportunity->update(['target_buyer' => 'business_owner']);
        $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'buyer_identified',
        ])->assertOk();
    }

    public function test_gate_2_needs_one_confirming_interview(): void
    {
        $opportunity = $this->opportunity();

        $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'problem_validated',
        ])->assertStatus(422);

        $this->confirmInterview($opportunity, 'retailer-a');

        $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'problem_validated',
        ])->assertOk();
    }

    public function test_gate_3_needs_both_halves_not_either(): void
    {
        // §7 Gate 3: multiple independent businesses AND one strong commercial
        // signal. "Several people agree it is annoying" without a single
        // commercial signal is exactly what this gate exists to stop.
        $opportunity = $this->opportunity();
        $this->confirmInterview($opportunity, 'retailer-a');
        $this->confirmInterview($opportunity, 'retailer-b');

        $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'commercially_validated',
        ])->assertStatus(422);

        $this->evidence($opportunity, 'proposal', 'retailer-a');

        $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'commercially_validated',
        ])->assertOk();
    }

    public function test_gate_4_needs_money_and_nothing_substitutes(): void
    {
        $opportunity = $this->opportunity();
        $this->confirmInterview($opportunity, 'retailer-a');
        $this->confirmInterview($opportunity, 'retailer-b');
        // Every soft signal available, and still not Gate 4.
        $this->evidence($opportunity, 'pilot_interest', 'retailer-a');
        $this->evidence($opportunity, 'proposal', 'retailer-a');
        $this->evidence($opportunity, 'customer_request', 'retailer-b');

        $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'paid_pilot',
        ])->assertStatus(422);

        $this->evidence($opportunity, 'paid_pilot', 'retailer-a', 4500);

        $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'paid_pilot',
        ])->assertOk();
    }

    public function test_gate_5_needs_a_second_paying_business(): void
    {
        // Starts at paid_pilot so this asserts Gate 5 alone. Advancing from
        // `observed` would also have to clear Gates 1-4 on the way, which is
        // correct but would test four things at once.
        $opportunity = $this->opportunity(['status' => 'paid_pilot']);
        $this->evidence($opportunity, 'paid_pilot', 'retailer-a', 4500);
        $this->evidence($opportunity, 'repeat_customer', 'retailer-a', 9000);

        // Two payments, one business: retention, not repeatability.
        $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'repeatable_solution',
        ])->assertStatus(422);

        $this->evidence($opportunity, 'paid_pilot', 'retailer-b', 3800);

        $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'repeatable_solution',
        ])->assertOk();
    }

    public function test_every_gate_is_reported_whether_satisfied_or_not(): void
    {
        // A UI that only received the passing gates could show progress but
        // never show what to do next. All five are always present, each with the
        // requirement behind it and — when unmet — the reason.
        $opportunity = $this->opportunity(['target_buyer' => 'business_owner']);

        $gates = $this->getJson("/api/v1/opportunities/{$opportunity->id}/validation")->json('meta.gates');

        $this->assertSame([
            'buyer_identified',
            'problem_validated',
            'commercially_validated',
            'paid_pilot',
            'repeatable_solution',
        ], array_keys($gates));

        // Gate 1 is met by target_buyer alone; the other four are not.
        $this->assertTrue($gates['buyer_identified']['satisfied']);
        $this->assertNull($gates['buyer_identified']['blocking_reason']);

        foreach (['problem_validated', 'commercially_validated', 'paid_pilot', 'repeatable_solution'] as $stage) {
            $this->assertFalse($gates[$stage]['satisfied'], $stage);
            $this->assertNotEmpty($gates[$stage]['blocking_reason'], $stage);
            $this->assertNotEmpty($gates[$stage]['requirement'], $stage);
        }
    }

    public function test_advancing_cannot_skip_a_stage_whose_gate_is_unmet(): void
    {
        // Found by walking the funnel end to end: checking only the destination
        // gate let `problem_validated` be reached with no buyer hypothesis
        // recorded — a state suggestFrom() can never produce, since it stops at
        // the first failing gate. The API and the engine must agree on what the
        // funnel contains.
        $opportunity = $this->opportunity(['status' => 'investigating', 'target_buyer' => null]);
        $this->confirmInterview($opportunity, 'retailer-a');

        $blocked = $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'problem_validated',
        ]);

        $blocked->assertStatus(422);
        // Names the stage it stalled at, not just the one asked for.
        $this->assertSame('buyer_identified', $blocked->json('meta.blocked_at'));
        $this->assertStringContainsString('Gate 1', $blocked->json('error'));

        $opportunity->update(['target_buyer' => 'business_owner']);
        $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'problem_validated',
        ])->assertOk();
    }

    public function test_a_multi_stage_advance_is_allowed_when_every_gate_on_the_way_is_met(): void
    {
        $opportunity = $this->opportunity(['status' => 'observed', 'target_buyer' => 'business_owner']);
        $this->confirmInterview($opportunity, 'retailer-a');
        $this->confirmInterview($opportunity, 'retailer-b');
        $this->evidence($opportunity, 'proposal', 'retailer-a');
        $this->evidence($opportunity, 'paid_pilot', 'retailer-a', 4500);

        // observed → paid_pilot in one move, because every gate between is met.
        $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'paid_pilot',
        ])->assertOk();
    }

    // ------------------------------------------------------- buyer hypothesis

    public function test_gate_1_can_actually_be_satisfied_through_the_api(): void
    {
        // Also found by walking the funnel: nothing could write target_buyer, so
        // Gate 1 was unreachable. The scoring engine deliberately never touches
        // it — inferring a buyer from signal payer_type would make the gate pass
        // itself, which is the opposite of what a gate is for.
        $opportunity = $this->opportunity(['status' => 'observed', 'target_buyer' => null]);

        $this->patchJson("/api/v1/opportunities/{$opportunity->id}", [
            'target_buyer' => 'business_owner',
            'problem_statement' => 'Month-end reconciliation costs three admin days.',
        ])->assertOk();

        $this->assertTrue($opportunity->fresh()->evidenceSummary()['has_buyer_hypothesis']);
        $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'buyer_identified',
        ])->assertOk();
    }

    public function test_the_narrative_endpoint_never_touches_scores_or_stage(): void
    {
        // §52 keeps narrative human-authored and stage human-approved. This
        // endpoint writes the first and must not touch the second.
        $opportunity = $this->opportunity(['status' => 'observed', 'opportunity_score' => 61]);

        $this->patchJson("/api/v1/opportunities/{$opportunity->id}", [
            'problem_statement' => 'Rewritten by a person.',
            // Sent but not in the allow-list, so silently dropped rather than
            // applied.
            'opportunity_score' => 99,
            'status' => 'paid_pilot',
        ])->assertOk();

        $fresh = $opportunity->fresh();
        $this->assertSame('Rewritten by a person.', $fresh->problem_statement);
        $this->assertSame('61.00', $fresh->opportunity_score);
        $this->assertSame('observed', $fresh->status);
    }

    public function test_an_empty_narrative_update_is_refused(): void
    {
        $opportunity = $this->opportunity();

        $this->patchJson("/api/v1/opportunities/{$opportunity->id}", [])->assertStatus(422);
    }

    // ---------------------------------------------------------------- transitions

    public function test_a_demotion_is_never_gate_checked(): void
    {
        // Deciding something was over-promoted is exactly the correction the
        // funnel must allow; making it hard leaves stale optimistic stages.
        $opportunity = $this->opportunity(['status' => 'commercially_validated']);

        $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'investigating',
            'note' => 'Both confirmations were the same franchise group.',
        ])->assertOk();

        $this->assertSame('investigating', $opportunity->fresh()->status);
    }

    public function test_a_gate_can_be_overridden_but_the_override_is_recorded(): void
    {
        $opportunity = $this->opportunity();

        $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'paid_pilot',
            'note' => 'Invoice raised in the accounting system, not yet mirrored here.',
            'override_gate' => true,
        ])->assertOk()->assertJsonPath('data.gate_overridden', true);

        $transition = $opportunity->fresh()->stageTransitions()->first();
        // A bypassed gate that leaves no trace is indistinguishable from a
        // satisfied one to anyone reading later.
        $this->assertStringContainsString('[gate overridden]', $transition->note);
    }

    public function test_a_transition_freezes_the_evidence_it_was_decided_on(): void
    {
        $opportunity = $this->opportunity();
        $this->confirmInterview($opportunity, 'retailer-a');

        $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'problem_validated',
        ])->assertOk();

        // More evidence arrives afterwards.
        $this->confirmInterview($opportunity, 'retailer-b');

        $snapshot = $opportunity->fresh()->stageTransitions()->first()->evidence_snapshot;

        // The snapshot answers "what did we know when we decided", which a live
        // join can never reconstruct — §57 needs that to recalibrate weights.
        $this->assertSame(1, $snapshot['problem_confirmed_count']);
        $this->assertSame(2, $opportunity->fresh()->evidenceSummary()['problem_confirmed_count']);
    }

    public function test_a_transition_records_what_the_engine_was_suggesting(): void
    {
        $opportunity = $this->opportunity();
        $this->confirmInterview($opportunity, 'retailer-a');

        $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'investigating',
        ])->assertOk();

        $transition = $opportunity->fresh()->stageTransitions()->first();

        // So a later reader can see whether the human agreed with the engine,
        // overrode it, or moved without one.
        $this->assertSame('problem_validated', $transition->suggested_status_at_time);
        $this->assertSame('investigating', $transition->to_status);
        $this->assertSame('observed', $transition->from_status);
    }

    public function test_moving_to_the_current_stage_is_refused(): void
    {
        $opportunity = $this->opportunity(['status' => 'investigating']);

        $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'investigating',
        ])->assertStatus(422);
    }

    public function test_an_unknown_stage_is_refused(): void
    {
        $opportunity = $this->opportunity();

        $this->patchJson("/api/v1/opportunities/{$opportunity->id}/stage", [
            'status' => 'definitely_a_winner',
        ])->assertStatus(422)->assertJsonValidationErrors('status');
    }

    // ---------------------------------------------------------------- suggestion

    public function test_the_suggestion_never_skips_an_unsatisfied_gate(): void
    {
        // Two paying businesses but no recorded interviews. Gate 5 passes in
        // isolation, but suggesting `repeatable_solution` would describe a state
        // the funnel does not contain.
        $opportunity = $this->opportunity(['target_buyer' => null]);
        $this->evidence($opportunity, 'paid_pilot', 'retailer-a', 4000);
        $this->evidence($opportunity, 'paid_pilot', 'retailer-b', 4000);

        // Stops at `investigating`: Gate 1 has no buyer hypothesis recorded.
        $this->assertSame('investigating', $opportunity->fresh()->suggestedStage());
    }

    public function test_the_suggestion_walks_the_full_funnel_when_every_gate_passes(): void
    {
        $opportunity = $this->opportunity(['target_buyer' => 'business_owner']);
        $this->confirmInterview($opportunity, 'retailer-a');
        $this->confirmInterview($opportunity, 'retailer-b');
        $this->evidence($opportunity, 'proposal', 'retailer-a');
        $this->evidence($opportunity, 'paid_pilot', 'retailer-a', 4500);
        $this->evidence($opportunity, 'paid_pilot', 'retailer-b', 3800);

        $this->assertSame('repeatable_solution', $opportunity->fresh()->suggestedStage());
    }

    public function test_the_engine_never_suggests_a_build_decision(): void
    {
        // §7 Gate 5: "Only now should major SaaS investment begin." Beyond
        // repeatable_solution the funnel stops being about evidence, and the
        // engine has no business suggesting those stages.
        $opportunity = $this->opportunity(['target_buyer' => 'business_owner']);
        $this->confirmInterview($opportunity, 'retailer-a');
        $this->confirmInterview($opportunity, 'retailer-b');
        $this->evidence($opportunity, 'proposal', 'retailer-a');
        $this->evidence($opportunity, 'paid_pilot', 'retailer-a', 4500);
        $this->evidence($opportunity, 'paid_pilot', 'retailer-b', 3800);
        $this->evidence($opportunity, 'repeat_customer', 'retailer-c', 12000);

        $this->assertNotSame('product_candidate', $opportunity->fresh()->suggestedStage());
        $this->assertNotSame('saas_or_managed_service', $opportunity->fresh()->suggestedStage());
    }

    public function test_a_topic_with_no_human_contact_is_suggested_nothing(): void
    {
        $opportunity = $this->opportunity();

        $this->assertSame('observed', $opportunity->fresh()->suggestedStage());
    }

    // ---------------------------------------------------------------- the milestone

    public function test_a_problem_can_move_from_internet_signal_to_paid_pilot(): void
    {
        // Milestone 6's acceptance criterion, as one sequence.
        $opportunity = $this->opportunity(['status' => 'observed', 'target_buyer' => null]);

        $stage = fn (string $to, array $extra = []) => $this->patchJson(
            "/api/v1/opportunities/{$opportunity->id}/stage",
            ['status' => $to] + $extra
        );

        $stage('investigating')->assertOk();

        // Gate 1 through the API, the way an operator would.
        $this->patchJson("/api/v1/opportunities/{$opportunity->id}", [
            'target_buyer' => 'business_owner',
        ])->assertOk();
        $stage('buyer_identified')->assertOk();

        $this->confirmInterview($opportunity, 'retailer-a');
        $stage('problem_validated')->assertOk();

        $this->confirmInterview($opportunity, 'retailer-b');
        $this->evidence($opportunity, 'proposal', 'retailer-a', 6000);
        $stage('commercially_validated')->assertOk();

        $this->evidence($opportunity, 'paid_pilot', 'retailer-a', 4500);
        $stage('paid_pilot')->assertOk();

        $fresh = $opportunity->fresh();
        $this->assertSame('paid_pilot', $fresh->status);
        // Every step is on the record, in order.
        $this->assertSame(
            ['investigating', 'buyer_identified', 'problem_validated', 'commercially_validated', 'paid_pilot'],
            $fresh->stageTransitions()->orderBy('id')->pluck('to_status')->all()
        );
    }

    // ---------------------------------------------------------------- helpers

    private function opportunity(array $attributes = []): Opportunity
    {
        $topic = Topic::create([
            'slug' => 'topic-'.str()->random(8),
            'name' => 'Test topic',
            'enabled' => true,
        ]);

        return Opportunity::create(array_merge([
            'topic_id' => $topic->id,
            'title' => 'Test opportunity',
            'status' => 'observed',
            'target_buyer' => 'business_owner',
            'opportunity_score' => 60,
            'confidence_score' => 40,
            'score_components' => [],
        ], $attributes));
    }

    private function confirmInterview(Opportunity $opportunity, ?string $companyRef): CustomerInterview
    {
        return $opportunity->interviews()->create([
            'company_ref' => $companyRef,
            'problem_confirmed' => true,
            'interviewed_at' => now(),
        ]);
    }

    private function evidence(
        Opportunity $opportunity,
        string $type,
        ?string $companyRef = null,
        ?float $value = null,
    ): CommercialEvidence {
        return $opportunity->commercialEvidence()->create([
            'evidence_type' => $type,
            'strength' => 'medium',
            'company_ref' => $companyRef,
            'value' => $value,
            'currency' => 'MYR',
            'occurred_at' => now(),
        ]);
    }
}
