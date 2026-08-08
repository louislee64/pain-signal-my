<?php

namespace Tests\Feature;

use App\Models\CommercialEvidence;
use App\Models\CustomerInterview;
use App\Models\Experiment;
use App\Models\Opportunity;
use App\Models\Report;
use App\Models\Topic;
use App\Services\ReportBuilder;
use App\Services\ReportRenderer;
use App\Services\ReportService;
use Carbon\CarbonImmutable;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Tests\Support\SeedsSignals;
use Tests\TestCase;

class ReportGenerationTest extends TestCase
{
    use RefreshDatabase;
    use SeedsSignals;

    private CarbonImmutable $weekEnd;

    protected function setUp(): void
    {
        parent::setUp();
        $this->weekEnd = CarbonImmutable::parse('2026-08-08');
    }

    // ------------------------------------------------------- reproducibility

    public function test_the_same_period_generates_an_identical_hash_twice(): void
    {
        // Milestone 7's acceptance criterion: "reproducible from stored data".
        $this->seedRichWeek();
        $service = app(ReportService::class);

        $first = $service->generateWeekly($this->weekEnd);
        $firstHash = $first->content_hash;
        $firstMarkdown = $first->markdown;

        $second = $service->generateWeekly($this->weekEnd);

        $this->assertSame($firstHash, $second->content_hash);
        $this->assertSame($firstMarkdown, $second->markdown);
    }

    public function test_regenerating_replaces_in_place_rather_than_appending(): void
    {
        // §55 asks for "report history", which is a history of periods. Nine
        // near-identical Tuesday reports would be a log, not a history.
        $this->seedRichWeek();
        $service = app(ReportService::class);

        $service->generateWeekly($this->weekEnd);
        $service->generateWeekly($this->weekEnd);

        $this->assertSame(1, Report::count());
    }

    public function test_generated_at_does_not_affect_the_hash(): void
    {
        // Otherwise every report would be trivially unique and the
        // reproducibility check would be a tautology.
        $this->seedRichWeek();
        $service = app(ReportService::class);

        $first = $service->generateWeekly($this->weekEnd, CarbonImmutable::parse('2026-08-09 06:00'));
        $hash = $first->content_hash;

        $second = $service->generateWeekly($this->weekEnd, CarbonImmutable::parse('2026-09-01 23:00'));

        $this->assertSame($hash, $second->content_hash);
        $this->assertNotSame(
            $first->generated_at->toDateTimeString(),
            $second->generated_at->toDateTimeString()
        );
    }

    public function test_verify_reports_reproducible_when_nothing_changed(): void
    {
        $this->seedRichWeek();
        $service = app(ReportService::class);
        $report = $service->generateWeekly($this->weekEnd);

        $result = $service->verifyReproducible($report);

        $this->assertTrue($result['reproducible']);
        $this->assertTrue($result['markdown_identical']);
    }

    public function test_verify_reports_a_difference_when_the_underlying_data_changed(): void
    {
        // Not a bug — new evidence for a past week legitimately changes that
        // week's report. The check exists to make the change visible rather than
        // to forbid it.
        $this->seedRichWeek();
        $service = app(ReportService::class);
        $report = $service->generateWeekly($this->weekEnd);

        $opportunity = Opportunity::first();
        $opportunity->commercialEvidence()->create([
            'evidence_type' => 'paid_pilot',
            'strength' => 'strong',
            'company_ref' => 'retailer-z',
            'value' => 9000,
            'currency' => 'MYR',
            'occurred_at' => $this->weekEnd->subDay(),
        ]);

        $result = $service->verifyReproducible($report);

        $this->assertFalse($result['reproducible']);
        $this->assertNotSame($result['stored_hash'], $result['rebuilt_hash']);
    }

    public function test_data_outside_the_window_does_not_change_the_report(): void
    {
        // The mechanism behind reproducibility: every query is bounded by the
        // period, not by "now". A single `now()->subDays(7)` anywhere in the
        // builder would break this for the section that used it.
        $this->seedRichWeek();
        $service = app(ReportService::class);
        $hash = $service->generateWeekly($this->weekEnd)->content_hash;

        $opportunity = Opportunity::first();
        // Two months after the reporting period.
        $opportunity->interviews()->create([
            'company_ref' => 'retailer-future',
            'problem_confirmed' => true,
            'interviewed_at' => $this->weekEnd->addMonths(2),
        ]);
        $this->signal($opportunity->topic_id, $this->weekEnd->addMonths(2)->toDateString());

        $rebuilt = ReportBuilder::forWeekEnding($this->weekEnd)->build();
        $this->assertSame($hash, app(ReportService::class)
            ->generateWeekly($this->weekEnd)->content_hash);
        $this->assertNotEmpty($rebuilt);
    }

    public function test_the_window_is_exactly_seven_inclusive_days(): void
    {
        // subDays(6), not subWeek(): consecutive weekly reports must neither
        // overlap by a day nor skip one.
        $built = ReportBuilder::forWeekEnding($this->weekEnd)->build();

        $this->assertSame('2026-08-02', $built['period_start']);
        $this->assertSame('2026-08-08', $built['period_end']);
    }

    // --------------------------------------------------------------- sections

    public function test_all_eight_spec_39_sections_are_present(): void
    {
        $built = ReportBuilder::forWeekEnding($this->weekEnd)->build();

        $this->assertSame([
            'executive_summary',
            'rising_problems',
            'commercial_opportunities',
            'new_signals',
            'buyer_evidence',
            'opportunities_to_ignore',
            'suggested_experiments',
            'build_recommendation',
        ], array_keys($built['sections']));
    }

    public function test_the_title_is_spec_39s_title(): void
    {
        $built = ReportBuilder::forWeekEnding($this->weekEnd)->build();

        $this->assertSame('Malaysia SME Opportunity Intelligence', $built['title']);
    }

    public function test_an_empty_database_produces_a_report_that_says_so(): void
    {
        $built = ReportBuilder::forWeekEnding($this->weekEnd)->build();
        $markdown = (new ReportRenderer())->render($built);

        $this->assertTrue($built['sections']['executive_summary']['quiet_period']);
        // A quiet week is a finding, not a formatting problem.
        $this->assertStringContainsString('Nothing of commercial significance', $markdown);
    }

    public function test_rising_problems_only_lists_topics_that_actually_rose(): void
    {
        $rose = $this->opportunity('Accelerating');
        $flat = $this->opportunity('Steady');

        // Two mentions in the prior window, three in this one.
        $this->signal($rose->topic_id, '2026-07-27');
        $this->signal($rose->topic_id, '2026-08-03');
        $this->signal($rose->topic_id, '2026-08-04');
        // Same count in both windows.
        $this->signal($flat->topic_id, '2026-07-28');
        $this->signal($flat->topic_id, '2026-08-05');

        $rising = ReportBuilder::forWeekEnding($this->weekEnd)->build()['sections']['rising_problems'];

        $this->assertCount(1, $rising);
        $this->assertSame('Accelerating', $rising[0]['title']);
    }

    public function test_a_topic_with_no_prior_window_is_new_not_infinite_growth(): void
    {
        // Growth from zero has no finite percentage. Returning a large number
        // would let a topic's first two mentions outrank a genuine surge.
        $fresh = $this->opportunity('Brand new');
        $this->signal($fresh->topic_id, '2026-08-05');

        $rising = ReportBuilder::forWeekEnding($this->weekEnd)->build()['sections']['rising_problems'];

        $this->assertNull($rising[0]['change_percent']);
        $this->assertSame('new this period', $rising[0]['change_label']);
    }

    public function test_new_signals_ranks_on_first_seen_not_recent_activity(): void
    {
        $old = $this->opportunity('Long-running');
        $new = $this->opportunity('Just appeared');

        $this->signal($old->topic_id, '2026-01-01');
        $this->signal($old->topic_id, '2026-08-07');   // busiest, but not new
        $this->signal($new->topic_id, '2026-08-04');

        $newSignals = ReportBuilder::forWeekEnding($this->weekEnd)->build()['sections']['new_signals'];

        $this->assertCount(1, $newSignals);
        $this->assertSame('Just appeared', $newSignals[0]['title']);
    }

    public function test_buyer_evidence_separates_money_from_everything_else(): void
    {
        // §7 Gate 4: a payment is a different grade of evidence, and burying it
        // in a list of nine types is how a report fails to say what mattered.
        $opportunity = $this->opportunity('Has evidence');
        $this->evidence($opportunity, 'pilot_interest', '2026-08-03');
        $this->evidence($opportunity, 'paid_pilot', '2026-08-05', 4500);

        $buyer = ReportBuilder::forWeekEnding($this->weekEnd)->build()['sections']['buyer_evidence'];

        $this->assertCount(2, $buyer['evidence']);
        $this->assertCount(1, $buyer['paid_evidence']);
        $this->assertSame('paid_pilot', $buyer['paid_evidence'][0]['evidence_type']);
    }

    public function test_buyer_evidence_carries_no_identifying_information(): void
    {
        // §21's posture has to survive into the report — a document that gets
        // emailed and posted to Discord is the worst place for it to leak.
        $opportunity = $this->opportunity('Interviewed');
        $opportunity->interviews()->create([
            'company_ref' => 'retailer-a',
            'industry' => 'retail',
            'respondent_role' => 'owner',
            'problem_confirmed' => true,
            'notes' => 'Spoke at length.',
            'interviewed_at' => '2026-08-04',
        ]);

        $markdown = (new ReportRenderer())->render(
            ReportBuilder::forWeekEnding($this->weekEnd)->build()
        );

        $this->assertStringContainsString('retailer-a', $markdown);
        // Notes are deliberately not rendered: they are free text an operator
        // typed, and free text is where a name ends up.
        $this->assertStringNotContainsString('Spoke at length', $markdown);
    }

    public function test_build_recommendation_is_capped_at_two(): void
    {
        // §39: "Do not recommend building 10 products simultaneously."
        foreach (range(1, 5) as $i) {
            $this->opportunity("Candidate {$i}", ['recommendation' => 'SELL_PILOT', 'opportunity_score' => 70 + $i]);
        }

        $build = ReportBuilder::forWeekEnding($this->weekEnd)->build()['sections']['build_recommendation'];

        $this->assertCount(2, $build['recommended']);
        // The cap is visible as a choice rather than looking like the whole
        // picture.
        $this->assertCount(3, $build['deferred_by_cap']);
    }

    public function test_productize_outranks_sell_pilot_regardless_of_score(): void
    {
        // §7 Gate 5 makes repeatability the thing that licenses real investment,
        // so a lower-scoring PRODUCTIZE leads a higher-scoring SELL_PILOT.
        $this->opportunity('Higher scoring pilot', ['recommendation' => 'SELL_PILOT', 'opportunity_score' => 95]);
        $this->opportunity('Repeatable', ['recommendation' => 'PRODUCTIZE', 'opportunity_score' => 72]);

        $build = ReportBuilder::forWeekEnding($this->weekEnd)->build()['sections']['build_recommendation'];

        $this->assertSame('Repeatable', $build['recommended'][0]['title']);
    }

    public function test_build_recommendation_says_nothing_qualifies_when_nothing_does(): void
    {
        $this->opportunity('Not ready', ['recommendation' => 'WATCH', 'opportunity_score' => 60]);

        $build = ReportBuilder::forWeekEnding($this->weekEnd)->build()['sections']['build_recommendation'];

        $this->assertSame([], $build['recommended']);
        $this->assertStringContainsString('valid answer', $build['note']);
    }

    public function test_suggested_experiments_name_the_next_unmet_gate(): void
    {
        $opportunity = $this->opportunity('Needs a buyer', [
            'opportunity_score' => 70,
            'target_buyer' => null,
        ]);

        $experiments = ReportBuilder::forWeekEnding($this->weekEnd)
            ->build()['sections']['suggested_experiments'];

        $this->assertSame('buyer_identified', $experiments['suggested'][0]['next_gate']);
        $this->assertStringContainsString('Gate 1', $experiments['suggested'][0]['blocked_by']);
    }

    public function test_experiments_already_running_are_not_re_suggested(): void
    {
        $opportunity = $this->opportunity('Being tested', ['opportunity_score' => 80]);
        Experiment::create([
            'opportunity_id' => $opportunity->id,
            'hypothesis' => 'They will pay',
            'success_metric' => '3 pilots',
            'experiment_type' => 'cold_outreach',
            'status' => 'running',
        ]);

        $experiments = ReportBuilder::forWeekEnding($this->weekEnd)
            ->build()['sections']['suggested_experiments'];

        $this->assertSame([], $experiments['suggested']);
        $this->assertCount(1, $experiments['in_progress']);
    }

    public function test_opportunities_to_ignore_needs_attention_and_weak_commerce(): void
    {
        // High attention with a weak commercial case is the §39 population.
        $noisy = $this->opportunity('Loud but unmonetizable', ['commercial_score' => 20]);
        $this->signal($noisy->topic_id, '2026-08-03');
        $this->signal($noisy->topic_id, '2026-08-04');
        $this->signal($noisy->topic_id, '2026-08-05');

        // Weak commerce but nobody is talking about it — not "high attention".
        $quiet = $this->opportunity('Quiet and unmonetizable', ['commercial_score' => 20]);
        $this->signal($quiet->topic_id, '2026-08-03');

        $ignore = ReportBuilder::forWeekEnding($this->weekEnd)
            ->build()['sections']['opportunities_to_ignore'];

        $this->assertCount(1, $ignore['poorly_monetizable']);
        $this->assertSame('Loud but unmonetizable', $ignore['poorly_monetizable'][0]['title']);
    }

    public function test_executive_summary_holds_at_most_three_findings(): void
    {
        // §39: "Top 3 findings."
        $this->seedRichWeek();

        $summary = ReportBuilder::forWeekEnding($this->weekEnd)
            ->build()['sections']['executive_summary'];

        $this->assertLessThanOrEqual(3, count($summary['findings']));
    }

    public function test_executive_summary_leads_with_money_when_money_exists(): void
    {
        // Ordered by how much a finding should change behaviour, not by score.
        $this->seedRichWeek();

        $summary = ReportBuilder::forWeekEnding($this->weekEnd)
            ->build()['sections']['executive_summary'];

        $this->assertSame('commercial', $summary['findings'][0]['kind']);
    }

    public function test_the_report_records_which_scoring_weights_produced_it(): void
    {
        // The same window under different weights is genuinely a different
        // report; a reader comparing two needs to see that rather than conclude
        // the data changed.
        $this->opportunity('Scored', ['scoring_config_version' => '1']);

        $inputs = ReportBuilder::forWeekEnding($this->weekEnd)->build()['inputs'];

        $this->assertSame(['1'], $inputs['scoring_config_versions']);
        $this->assertSame('report_weekly_v1', $inputs['builder_version']);
    }

    // -------------------------------------------------------------- endpoints

    public function test_the_generate_endpoint_stores_a_report(): void
    {
        $this->seedRichWeek();

        $response = $this->postJson('/api/v1/reports/generate', ['week_ending' => '2026-08-08']);

        $response->assertCreated();
        $this->assertSame(1, Report::count());
        $this->assertNotEmpty($response->json('data.content_hash'));
    }

    public function test_the_generate_endpoint_refuses_a_future_period(): void
    {
        $this->postJson('/api/v1/reports/generate', [
            'week_ending' => now()->addMonth()->toDateString(),
        ])->assertStatus(422);
    }

    public function test_the_generate_endpoint_does_not_notify_unless_asked(): void
    {
        // Someone regenerating a report to look at it must not thereby post it
        // to a team channel.
        $this->seedRichWeek();

        $response = $this->postJson('/api/v1/reports/generate', ['week_ending' => '2026-08-08']);

        $this->assertNull($response->json('meta.delivery'));
    }

    public function test_the_list_endpoint_omits_the_body(): void
    {
        // A year of weekly reports is a lot of prose; a list that returns every
        // word is slow at exactly the point the history becomes useful.
        $this->seedRichWeek();
        app(ReportService::class)->generateWeekly($this->weekEnd);

        $row = $this->getJson('/api/v1/reports')->json('data.0');

        $this->assertArrayNotHasKey('markdown', $row);
        $this->assertArrayNotHasKey('sections', $row);
        $this->assertArrayHasKey('content_hash', $row);
    }

    public function test_the_show_endpoint_serves_the_stored_markdown(): void
    {
        $this->seedRichWeek();
        $report = app(ReportService::class)->generateWeekly($this->weekEnd);

        $response = $this->getJson("/api/v1/reports/{$report->id}");

        $response->assertOk();
        // Served as stored, never re-rendered: a report that changed under the
        // reader would be useless as a record.
        $this->assertSame($report->markdown, $response->json('data.markdown'));
    }

    public function test_the_verify_endpoint_confirms_reproducibility(): void
    {
        $this->seedRichWeek();
        $report = app(ReportService::class)->generateWeekly($this->weekEnd);

        $this->getJson("/api/v1/reports/{$report->id}/verify")
            ->assertOk()
            ->assertJsonPath('data.reproducible', true);
    }

    public function test_show_returns_404_for_an_unknown_report(): void
    {
        $this->getJson('/api/v1/reports/9999')->assertNotFound();
    }

    // ---------------------------------------------------------------- helpers

    private function opportunity(string $title, array $attributes = []): Opportunity
    {
        $topic = Topic::create([
            'slug' => 'topic-'.str()->random(8),
            'name' => $title,
            'enabled' => true,
        ]);

        return Opportunity::create(array_merge([
            'topic_id' => $topic->id,
            'title' => $title,
            'status' => 'observed',
            'target_buyer' => 'business_owner',
            'pain_score' => 50,
            'commercial_score' => 60,
            'opportunity_score' => 55,
            'confidence_score' => 40,
            'recommendation' => 'WATCH',
            'score_components' => [],
            'scoring_config_version' => '1',
        ], $attributes));
    }

    private function evidence(Opportunity $o, string $type, string $date, ?float $value = null): CommercialEvidence
    {
        return $o->commercialEvidence()->create([
            'evidence_type' => $type,
            'strength' => 'medium',
            'company_ref' => 'retailer-a',
            'value' => $value,
            'currency' => 'MYR',
            'occurred_at' => $date,
        ]);
    }

    /** A week with something in every section, so the summary has real inputs. */
    private function seedRichWeek(): void
    {
        $opportunity = $this->opportunity('Reconciliation', [
            'opportunity_score' => 75,
            'recommendation' => 'SELL_PILOT',
            'status' => 'paid_pilot',
        ]);

        $this->signal($opportunity->topic_id, '2026-07-28');
        $this->signal($opportunity->topic_id, '2026-08-03');
        $this->signal($opportunity->topic_id, '2026-08-04');
        $this->signal($opportunity->topic_id, '2026-08-05');

        CustomerInterview::create([
            'opportunity_id' => $opportunity->id,
            'company_ref' => 'retailer-a',
            'industry' => 'retail',
            'respondent_role' => 'owner',
            'problem_confirmed' => true,
            'interviewed_at' => '2026-08-04',
        ]);

        $this->evidence($opportunity, 'proposal', '2026-08-05', 6000);
        $this->evidence($opportunity, 'paid_pilot', '2026-08-07', 4500);

        $opportunity->stageTransitions()->create([
            'from_status' => 'commercially_validated',
            'to_status' => 'paid_pilot',
            'suggested_status_at_time' => 'paid_pilot',
            'note' => 'Pilot paid',
            'evidence_snapshot' => ['paid_pilot_count' => 1],
            'created_at' => '2026-08-07 10:00:00',
        ]);
    }
}
