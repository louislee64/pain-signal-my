<?php

namespace Tests\Feature;

use App\Models\Opportunity;
use App\Models\OpportunityOutcome;
use App\Models\OpportunityRevenue;
use App\Models\Topic;
use App\Services\CalibrationAnalyser;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\TestCase;

class CalibrationTest extends TestCase
{
    use RefreshDatabase;

    // ------------------------------------------------------- sample-size honesty

    public function test_an_empty_dataset_says_so_rather_than_reporting_zeros(): void
    {
        $report = app(CalibrationAnalyser::class)->analyse();

        $this->assertSame(0, $report['sample']['outcomes_recorded']);
        $this->assertFalse($report['sample']['sufficient']);
        $this->assertStringContainsString('No outcomes recorded yet', $report['sample']['note']);
    }

    public function test_the_empty_report_has_the_same_shape_as_a_populated_one(): void
    {
        // A caller that has to handle two shapes will eventually handle one of
        // them wrong.
        $empty = app(CalibrationAnalyser::class)->analyse();

        $this->concluded($this->opportunity('Anything'), 'successful');
        $populated = app(CalibrationAnalyser::class)->analyse();

        $this->assertSame(array_keys($populated), array_keys($empty));
        $this->assertSame(array_keys($populated['revenue']), array_keys($empty['revenue']));
    }

    public function test_a_small_sample_refuses_to_conclude(): void
    {
        // §30's separation of score from confidence, applied to the system's
        // opinion of itself.
        foreach (range(1, 4) as $i) {
            $this->concluded($this->opportunity("Flop {$i}", 85), 'no_budget', interviews: 5);
        }

        $report = app(CalibrationAnalyser::class)->analyse();

        $this->assertFalse($report['sample']['sufficient']);
        $this->assertSame('insufficient_data', $report['suggestions'][0]['kind']);
        $this->assertStringContainsString('config/scoring.yaml', $report['suggestions'][0]['text']);
    }

    public function test_a_sufficient_sample_does_conclude(): void
    {
        foreach (range(1, 8) as $i) {
            $this->concluded($this->opportunity("Flop {$i}", 85), 'no_budget', interviews: 5);
        }

        $report = app(CalibrationAnalyser::class)->analyse();

        $this->assertTrue($report['sample']['sufficient']);
        $this->assertNotSame('insufficient_data', $report['suggestions'][0]['kind']);
    }

    // ------------------------------------------------------------ §57's examples

    public function test_spec_57_opportunity_a_is_flagged_as_overestimated(): void
    {
        // "score = 92, 10 interviews, 0 businesses willing to pay.
        //  Result: commercial assumptions were wrong."
        $opportunity = $this->opportunity('Opportunity A', 92);
        $this->concluded($opportunity, 'no_budget', interviews: 10, confirmed: 6);

        $report = app(CalibrationAnalyser::class)->analyse();

        $this->assertCount(1, $report['overestimated']);
        $this->assertSame('Opportunity A', $report['overestimated'][0]['title']);
        // The point of the flag is naming what to look at, not just that
        // something was wrong.
        $this->assertSame('commercial_score', $report['overestimated'][0]['implicates']);
    }

    public function test_spec_57_opportunity_b_is_flagged_as_underestimated(): void
    {
        // "score = 68, 3 interviews, 2 paid pilots.
        //  Result: system underestimated opportunity."
        //
        // Scored at 55 here rather than 68: the threshold for "the model was too
        // low" is §35's INVESTIGATE floor of 60, and 68 is above it — the model
        // told you to investigate and you did. That is not a miss.
        $opportunity = $this->opportunity('Opportunity B', 55);
        $this->concluded($opportunity, 'successful', interviews: 3, paidPilots: 2, revenue: 9000);

        $report = app(CalibrationAnalyser::class)->analyse();

        $this->assertCount(1, $report['underestimated']);
        $this->assertSame('Opportunity B', $report['underestimated'][0]['title']);
    }

    public function test_a_failure_with_no_interviews_is_not_blamed_on_the_model(): void
    {
        // A negative outcome with no customer contact reflects effort, not the
        // scoring model. Counting it would blame the model for work never done.
        $this->concluded($this->opportunity('Never pursued', 90), 'no_budget', interviews: 0);

        $report = app(CalibrationAnalyser::class)->analyse();

        $this->assertSame([], $report['overestimated']);
    }

    public function test_underestimation_keys_on_money_not_on_the_label(): void
    {
        // `successful` is a judgement someone typed; a paid pilot is a fact.
        $labelled = $this->opportunity('Called successful', 40);
        $this->concluded($labelled, 'successful', interviews: 2);   // no money

        $paid = $this->opportunity('Actually paid', 40);
        $this->concluded($paid, 'promising', interviews: 2, paidPilots: 1, revenue: 3000);

        $report = app(CalibrationAnalyser::class)->analyse();

        $titles = collect($report['underestimated'])->pluck('title');
        $this->assertContains('Actually paid', $titles);
        $this->assertNotContains('Called successful', $titles);
    }

    // ---------------------------------------------------------------- accuracy

    public function test_the_two_kinds_of_error_are_reported_separately(): void
    {
        // Wasted effort and missed opportunity cost different things and must
        // not average into one accuracy percentage.
        $this->concluded($this->opportunity('High and failed', 80), 'no_budget', interviews: 4);
        $this->concluded($this->opportunity('High and worked', 80), 'successful', interviews: 4);
        $this->concluded($this->opportunity('Low and worked', 30), 'successful', interviews: 2, paidPilots: 1);
        $this->concluded($this->opportunity('Low and failed', 30), 'poor_fit', interviews: 2);

        $accuracy = app(CalibrationAnalyser::class)->analyse()['accuracy'];

        $this->assertSame(1, $accuracy['scored_high_and_worked']);
        $this->assertSame(1, $accuracy['scored_high_and_failed']);
        $this->assertSame(1, $accuracy['scored_low_and_worked']);
        $this->assertSame(1, $accuracy['scored_low_and_failed']);
        $this->assertSame(1, $accuracy['wasted_effort']);
        $this->assertSame(1, $accuracy['missed']);
    }

    // ------------------------------------------------------ dimension signals

    public function test_a_dimension_that_scored_high_on_failures_is_flagged(): void
    {
        // The strongest signal available: a dimension high on things that
        // flopped and low on things that worked is doing the opposite of its job.
        foreach (range(1, 3) as $i) {
            $flop = $this->opportunity("Flop {$i}", 85, $this->components(payerClarity: 95));
            $this->concluded($flop, 'no_budget', interviews: 4);
        }
        foreach (range(1, 3) as $i) {
            $win = $this->opportunity("Win {$i}", 45, $this->components(payerClarity: 20));
            $this->concluded($win, 'successful', interviews: 3, paidPilots: 1, revenue: 4000);
        }

        $signals = app(CalibrationAnalyser::class)->analyse()['dimension_signals'];

        $this->assertSame('over_weighted', $signals['payer_clarity']['verdict']);
        $this->assertEqualsWithDelta(95.0, $signals['payer_clarity']['mean_in_overestimated'], 0.1);
        $this->assertEqualsWithDelta(20.0, $signals['payer_clarity']['mean_in_underestimated'], 0.1);
    }

    public function test_a_dimension_with_too_few_examples_gets_no_verdict(): void
    {
        // Two examples of anything is an anecdote.
        $flop = $this->opportunity('One flop', 85, $this->components(payerClarity: 95));
        $this->concluded($flop, 'no_budget', interviews: 4);

        $signals = app(CalibrationAnalyser::class)->analyse()['dimension_signals'];

        $this->assertNull($signals['payer_clarity']['verdict']);
        $this->assertStringContainsString('Too few examples', $signals['payer_clarity']['note']);
    }

    public function test_a_dimension_that_tracks_outcomes_correctly_is_not_flagged(): void
    {
        foreach (range(1, 3) as $i) {
            $flop = $this->opportunity("Flop {$i}", 85, $this->components(payerClarity: 30));
            $this->concluded($flop, 'no_budget', interviews: 4);
        }
        foreach (range(1, 3) as $i) {
            $win = $this->opportunity("Win {$i}", 45, $this->components(payerClarity: 35));
            $this->concluded($win, 'successful', interviews: 3, paidPilots: 1, revenue: 4000);
        }

        $signals = app(CalibrationAnalyser::class)->analyse()['dimension_signals'];

        $this->assertNull($signals['payer_clarity']['verdict']);
    }

    // ----------------------------------------------------------- §56's revenue

    public function test_revenue_is_summed_per_opportunity_and_in_total(): void
    {
        $a = $this->opportunity('Earner A');
        $b = $this->opportunity('Earner B');
        $this->revenue($a, 4500, 'retailer-a');
        $this->revenue($a, 4500, 'retailer-a');   // second month of the same pilot
        $this->revenue($b, 3000, 'retailer-b');

        $revenue = app(CalibrationAnalyser::class)->analyse()['revenue'];

        $this->assertEqualsWithDelta(12000.0, $revenue['total'], 0.01);
        $this->assertSame(2, $revenue['revenue_generating_opportunities']);
        $this->assertSame(3, $revenue['entries']);
    }

    public function test_a_refund_reduces_revenue(): void
    {
        // Recorded as a negative row rather than by deleting the original: the
        // original payment did happen, and erasing it would lose that.
        $opportunity = $this->opportunity('Refunded');
        $this->revenue($opportunity, 4500, 'retailer-a');
        $this->revenue($opportunity, -1500, 'retailer-a');

        $revenue = app(CalibrationAnalyser::class)->analyse()['revenue'];

        $this->assertEqualsWithDelta(3000.0, $revenue['total'], 0.01);
    }

    public function test_revenue_is_reported_without_any_concluded_outcome(): void
    {
        // Money can arrive from an opportunity nobody has written a conclusion
        // for. The KPI must not wait on paperwork.
        $opportunity = $this->opportunity('Earning, unconcluded');
        $this->revenue($opportunity, 5000, 'retailer-a');

        $report = app(CalibrationAnalyser::class)->analyse();

        $this->assertSame(0, $report['sample']['outcomes_recorded']);
        $this->assertEqualsWithDelta(5000.0, $report['revenue']['total'], 0.01);
    }

    // --------------------------------------------------------------- endpoints

    public function test_concluding_snapshots_the_score_rather_than_trusting_the_caller(): void
    {
        // The decision the whole dataset rests on. A caller-supplied
        // initial_score would be whatever the score is now, which has already
        // been dragged toward the answer.
        $opportunity = $this->opportunity('Snapshot me', 71);

        $this->postJson("/api/v1/opportunities/{$opportunity->id}/outcome", [
            'outcome' => 'no_budget',
            'reason' => 'Everyone agreed it was annoying; nobody had a budget line.',
            'concluded_at' => '2026-08-09',
            'initial_score' => 12,   // not in the allow-list, must be ignored
        ])->assertCreated();

        $this->assertSame('71.00', OpportunityOutcome::first()->initial_score);
    }

    public function test_concluding_defaults_the_counts_from_recorded_evidence(): void
    {
        // Re-typing numbers the system already knows is how they end up wrong.
        $opportunity = $this->opportunity('Has evidence', 70);
        $opportunity->interviews()->create([
            'company_ref' => 'retailer-a',
            'problem_confirmed' => true,
            'interviewed_at' => '2026-08-01',
        ]);
        $opportunity->commercialEvidence()->create([
            'evidence_type' => 'paid_pilot',
            'strength' => 'strong',
            'company_ref' => 'retailer-a',
            'value' => 4500,
            'currency' => 'MYR',
            'occurred_at' => '2026-08-05',
        ]);

        $this->postJson("/api/v1/opportunities/{$opportunity->id}/outcome", [
            'outcome' => 'successful',
            'reason' => 'Pilot signed and paid.',
            'concluded_at' => '2026-08-09',
        ])->assertCreated();

        $outcome = OpportunityOutcome::first();
        $this->assertSame(1, $outcome->buyer_interviews);
        $this->assertSame(1, $outcome->confirmed_buyers);
        $this->assertSame(1, $outcome->paid_pilots);
    }

    public function test_a_reason_is_required(): void
    {
        // §58's nine categories cannot hold what actually happened, and the
        // reason is the part worth reading a year later.
        $opportunity = $this->opportunity('No reason given');

        $this->postJson("/api/v1/opportunities/{$opportunity->id}/outcome", [
            'outcome' => 'no_budget',
            'concluded_at' => '2026-08-09',
        ])->assertStatus(422)->assertJsonValidationErrors('reason');
    }

    public function test_concluding_twice_edits_rather_than_appends(): void
    {
        $opportunity = $this->opportunity('Reconsidered', 70);

        foreach (['promising', 'no_budget'] as $outcome) {
            $this->postJson("/api/v1/opportunities/{$opportunity->id}/outcome", [
                'outcome' => $outcome,
                'reason' => 'Revised after the second conversation.',
                'concluded_at' => '2026-08-09',
            ])->assertCreated();
        }

        $this->assertSame(1, OpportunityOutcome::count());
        $this->assertSame('no_budget', OpportunityOutcome::first()->outcome);
    }

    public function test_concluding_an_unscored_opportunity_warns(): void
    {
        $opportunity = $this->opportunity('Never scored', null);

        $response = $this->postJson("/api/v1/opportunities/{$opportunity->id}/outcome", [
            'outcome' => 'false_signal',
            'reason' => 'Nobody recognised the problem.',
            'concluded_at' => '2026-08-09',
        ]);

        $this->assertStringContainsString(
            'contributes nothing to calibration',
            $response->json('meta.warnings.0')
        );
    }

    public function test_revenue_recorded_later_updates_a_concluded_outcome(): void
    {
        // Otherwise the dataset permanently understates what the opportunity
        // earned.
        $opportunity = $this->opportunity('Late payer', 60);
        $this->postJson("/api/v1/opportunities/{$opportunity->id}/outcome", [
            'outcome' => 'promising',
            'reason' => 'Pilot agreed, invoice not yet raised.',
            'concluded_at' => '2026-08-09',
        ])->assertCreated();

        $this->assertEqualsWithDelta(0.0, (float) OpportunityOutcome::first()->revenue, 0.01);

        $this->postJson("/api/v1/opportunities/{$opportunity->id}/revenue", [
            'revenue_type' => 'paid_pilot',
            'amount' => 4500,
            'company_ref' => 'retailer-a',
            'received_at' => '2026-08-20',
        ])->assertCreated();

        $this->assertEqualsWithDelta(4500.0, (float) OpportunityOutcome::first()->revenue, 0.01);
    }

    public function test_a_zero_revenue_row_is_refused(): void
    {
        $opportunity = $this->opportunity('Nothing received');

        $this->postJson("/api/v1/opportunities/{$opportunity->id}/revenue", [
            'revenue_type' => 'paid_pilot',
            'amount' => 0,
            'received_at' => '2026-08-09',
        ])->assertStatus(422);
    }

    public function test_revenue_company_ref_stays_pseudonymous(): void
    {
        $opportunity = $this->opportunity('Named customer');

        $this->postJson("/api/v1/opportunities/{$opportunity->id}/revenue", [
            'revenue_type' => 'paid_pilot',
            'amount' => 4500,
            'company_ref' => 'Restoran Ali Sdn Bhd',
            'received_at' => '2026-08-09',
        ])->assertStatus(422)->assertJsonValidationErrors('company_ref');
    }

    public function test_the_calibration_endpoint_says_it_never_edits_weights(): void
    {
        // Stated in the response, not only the docs: an API consumer is exactly
        // who would otherwise write the auto-tuning loop this prevents.
        $note = $this->getJson('/api/v1/calibration')->json('meta.note');

        $this->assertStringContainsString('never edits config/scoring.yaml', $note);
    }

    public function test_the_metrics_endpoint_separates_technical_from_business(): void
    {
        $data = $this->getJson('/api/v1/metrics')->json('data');

        // A green technical panel above an empty business panel is the most
        // important state this system can be in.
        $this->assertArrayHasKey('technical', $data);
        $this->assertArrayHasKey('business', $data);
        $this->assertSame('opportunity_generated_revenue', $this->getJson('/api/v1/metrics')->json('meta.ultimate_kpi'));
    }

    public function test_rates_carry_their_own_arithmetic(): void
    {
        // "40% from two interviews" and "40% from two hundred" are different
        // facts; a bare percentage makes them identical.
        $rate = $this->getJson('/api/v1/metrics')->json('data.business.problem_confirmation_rate');

        $this->assertArrayHasKey('numerator', $rate);
        $this->assertArrayHasKey('denominator', $rate);
        // Null, not 0: "no interviews yet" is not "none confirmed".
        $this->assertNull($rate['percent']);
    }

    public function test_classification_metric_does_not_claim_to_be_accuracy(): void
    {
        $classification = $this->getJson('/api/v1/metrics')->json('data.technical.classification');

        $this->assertArrayHasKey('coverage_percent', $classification);
        $this->assertStringContainsString('not accuracy', $classification['accuracy_note']);
    }

    // ---------------------------------------------------------------- helpers

    private function opportunity(string $title, ?float $score = 70, ?array $components = null): Opportunity
    {
        $topic = Topic::create([
            'slug' => 'topic-'.str()->random(8),
            'name' => $title,
            'enabled' => true,
        ]);

        return Opportunity::create([
            'topic_id' => $topic->id,
            'title' => $title,
            'status' => 'observed',
            'target_buyer' => 'business_owner',
            'pain_score' => 50,
            'commercial_score' => $score,
            'opportunity_score' => $score,
            'confidence_score' => 40,
            'recommendation' => 'WATCH',
            'score_components' => $components ?? [],
            'scoring_config_version' => '1',
        ]);
    }

    private function components(float $payerClarity): array
    {
        return [
            'commercial_score' => [
                'score' => 70.0,
                'dimensions' => [
                    'payer_clarity' => [
                        'raw' => 5,
                        'normalized' => $payerClarity,
                        'weight' => 0.25,
                        'contribution' => $payerClarity * 0.25,
                    ],
                ],
                'notes' => [],
            ],
        ];
    }

    private function concluded(
        Opportunity $opportunity,
        string $outcome,
        int $interviews = 0,
        int $confirmed = 0,
        int $paidPilots = 0,
        float $revenue = 0,
    ): OpportunityOutcome {
        return OpportunityOutcome::create([
            'opportunity_id' => $opportunity->id,
            'initial_score' => $opportunity->opportunity_score,
            'initial_pain_score' => $opportunity->pain_score,
            'initial_commercial_score' => $opportunity->commercial_score,
            'initial_confidence_score' => $opportunity->confidence_score,
            'initial_score_components' => $opportunity->score_components,
            'scoring_config_version' => '1',
            'buyer_interviews' => $interviews,
            'confirmed_buyers' => $confirmed,
            'paid_pilots' => $paidPilots,
            'customers' => $paidPilots,
            'revenue' => $revenue,
            'outcome' => $outcome,
            'reason' => 'Recorded by test.',
            'concluded_at' => '2026-08-09',
        ]);
    }

    private function revenue(Opportunity $opportunity, float $amount, string $companyRef): OpportunityRevenue
    {
        return $opportunity->revenue()->create([
            'revenue_type' => 'paid_pilot',
            'amount' => $amount,
            'currency' => 'MYR',
            'company_ref' => $companyRef,
            'received_at' => '2026-08-09',
        ]);
    }
}
