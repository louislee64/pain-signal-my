<?php

namespace Tests\Feature;

use App\Models\Alert;
use App\Models\Opportunity;
use App\Models\Topic;
use App\Notifications\Channels\NotificationChannel;
use App\Notifications\Notifier;
use App\Services\AlertDetector;
use Illuminate\Foundation\Testing\RefreshDatabase;
use RuntimeException;
use Tests\Support\SeedsSignals;
use Tests\TestCase;

class AlertingTest extends TestCase
{
    use RefreshDatabase;
    use SeedsSignals;

    // ------------------------------------------------------------------ dedup

    public function test_a_standing_condition_alerts_once_not_every_run(): void
    {
        // The hard part of §40: its conditions are standing facts, not events.
        // A naive scheduled evaluation re-fires everything still true, and a
        // channel that repeats itself daily gets muted within a week.
        $this->opportunity('Ready to sell', ['recommendation' => 'SELL_PILOT']);
        $detector = app(AlertDetector::class);

        $first = $detector->detect();
        $second = $detector->detect();
        $third = $detector->detect();

        $milestones = collect($first['detected'])->where('alert_type', 'recommendation_milestone');
        $this->assertCount(1, $milestones);
        $this->assertSame(
            0,
            collect($second['detected'])->where('alert_type', 'recommendation_milestone')->count()
        );
        $this->assertGreaterThan(0, $second['skipped_duplicates']);
        $this->assertSame([], collect($third['detected'])->where('alert_type', 'recommendation_milestone')->all());
    }

    public function test_reaching_a_further_milestone_alerts_again(): void
    {
        // Keyed on the recommendation as well as the opportunity, so PRODUCTIZE
        // is not suppressed by an earlier SELL_PILOT.
        $opportunity = $this->opportunity('Climbing', ['recommendation' => 'SELL_PILOT']);
        $detector = app(AlertDetector::class);
        $detector->detect();

        $opportunity->update(['recommendation' => 'PRODUCTIZE']);
        $result = $detector->detect();

        $this->assertSame(
            1,
            collect($result['detected'])->where('alert_type', 'recommendation_milestone')->count()
        );
    }

    // ------------------------------------------------------------------ rules

    public function test_a_first_run_records_a_baseline_rather_than_alerting_on_every_score(): void
    {
        // An opportunity that has always been at 80 must not alert as though it
        // just got there.
        $this->opportunity('Always high', ['opportunity_score' => 80]);

        $result = app(AlertDetector::class)->detect();

        $this->assertSame(0, collect($result['detected'])->where('alert_type', 'score_increase')->count());
        // The baseline is recorded so the *next* rise is measurable, and marked
        // delivered so it is never sent.
        $baseline = Alert::where('dedupe_key', 'like', '%:baseline')->first();
        $this->assertNotNull($baseline);
        $this->assertSame('suppressed:baseline', $baseline->delivered_via);
    }

    public function test_a_significant_score_increase_alerts(): void
    {
        $opportunity = $this->opportunity('Rising', ['opportunity_score' => 50]);
        $detector = app(AlertDetector::class);
        $detector->detect();   // records the baseline at 50

        $opportunity->update(['opportunity_score' => 72]);
        $result = $detector->detect();

        $alert = collect($result['detected'])->firstWhere('alert_type', 'score_increase');
        $this->assertNotNull($alert);
        // JSON round-trips 72.0 back as int 72, so compare numerically.
        $this->assertEqualsWithDelta(72.0, $alert->context['score'], 0.001);
        $this->assertEqualsWithDelta(50.0, $alert->context['previous_score'], 0.001);
    }

    public function test_a_small_score_increase_does_not_alert(): void
    {
        $opportunity = $this->opportunity('Drifting', ['opportunity_score' => 50]);
        $detector = app(AlertDetector::class);
        $detector->detect();

        $opportunity->update(['opportunity_score' => 55]);
        $result = $detector->detect();

        $this->assertSame(0, collect($result['detected'])->where('alert_type', 'score_increase')->count());
    }

    public function test_top10_entry_is_keyed_on_the_opportunity_not_the_rank(): void
    {
        // Shuffling from #7 to #6 is not news; including the rank in the key
        // would alert on every reordering.
        $a = $this->opportunity('First', ['opportunity_score' => 90]);
        $b = $this->opportunity('Second', ['opportunity_score' => 80]);
        $detector = app(AlertDetector::class);
        $detector->detect();

        $b->update(['opportunity_score' => 95]);
        $result = $detector->detect();

        $this->assertSame(0, collect($result['detected'])->where('alert_type', 'top10_entry')->count());
    }

    public function test_a_payment_alerts_at_critical_severity(): void
    {
        // §7 Gate 4 — money is the thing worth interrupting someone for.
        $opportunity = $this->opportunity('Paid');
        $opportunity->commercialEvidence()->create([
            'evidence_type' => 'paid_pilot',
            'strength' => 'strong',
            'company_ref' => 'retailer-a',
            'value' => 4500,
            'currency' => 'MYR',
            'occurred_at' => now(),
        ]);

        $result = app(AlertDetector::class)->detect();
        $alert = collect($result['detected'])->firstWhere('alert_type', 'commercial_evidence');

        $this->assertSame('critical', $alert->severity);
        $this->assertTrue($alert->context['is_paid']);
        $this->assertStringContainsString('79-point cap', $alert->body);
    }

    public function test_soft_evidence_alerts_at_info_severity(): void
    {
        $opportunity = $this->opportunity('Interested');
        $opportunity->commercialEvidence()->create([
            'evidence_type' => 'pilot_interest',
            'strength' => 'medium',
            'occurred_at' => now(),
        ]);

        $result = app(AlertDetector::class)->detect();
        $alert = collect($result['detected'])->firstWhere('alert_type', 'commercial_evidence');

        $this->assertSame('info', $alert->severity);
        $this->assertFalse($alert->context['is_paid']);
    }

    public function test_a_new_issue_needs_multiple_independent_sources(): void
    {
        // §31: one chatty forum is not corroboration. Counted by distinct
        // sources, not documents.
        $oneSource = $this->opportunity('Single source');
        $this->signal($oneSource->topic_id, now()->subDays(2)->toDateString(), sourceSlug: 'forum-a');
        $this->signal($oneSource->topic_id, now()->subDay()->toDateString(), sourceSlug: 'forum-a');

        $twoSources = $this->opportunity('Corroborated');
        $this->signal($twoSources->topic_id, now()->subDays(2)->toDateString(), sourceSlug: 'forum-a');
        $this->signal($twoSources->topic_id, now()->subDay()->toDateString(), sourceSlug: 'agency-b');

        $result = app(AlertDetector::class)->detect();
        $alerts = collect($result['detected'])->where('alert_type', 'corroborated_new_issue');

        $this->assertCount(1, $alerts);
        $this->assertSame('Corroborated', $alerts->first()->opportunity->title);
    }

    public function test_an_old_issue_does_not_alert_as_new(): void
    {
        $old = $this->opportunity('Long-standing');
        $this->signal($old->topic_id, now()->subMonths(6)->toDateString(), sourceSlug: 'forum-a');
        $this->signal($old->topic_id, now()->subDay()->toDateString(), sourceSlug: 'agency-b');

        $result = app(AlertDetector::class)->detect();

        $this->assertSame(
            0,
            collect($result['detected'])->where('alert_type', 'corroborated_new_issue')->count()
        );
    }

    // --------------------------------------------------------------- delivery

    public function test_detection_and_delivery_are_separate(): void
    {
        // An alert detected but not delivered must stay pending so the next run
        // retries — a delivery outage should not lose alerts.
        $this->opportunity('Ready', ['recommendation' => 'SELL_PILOT']);
        $detector = app(AlertDetector::class);
        $detector->detect();

        $this->assertGreaterThan(0, $detector->pending()->count());
    }

    public function test_pending_alerts_are_delivered_oldest_first(): void
    {
        // If delivery has been broken for a while the backlog should arrive in
        // the order it happened, not newest-first telling the story backwards.
        $this->opportunity('A', ['recommendation' => 'SELL_PILOT']);
        app(AlertDetector::class)->detect();
        Alert::query()->update(['detected_at' => now()->subDays(3)]);

        $this->opportunity('B', ['recommendation' => 'PRODUCTIZE']);
        app(AlertDetector::class)->detect();

        $pending = app(AlertDetector::class)->pending();

        $this->assertTrue(
            $pending->first()->detected_at->lessThan($pending->last()->detected_at)
        );
    }

    public function test_a_failing_channel_does_not_stop_the_others(): void
    {
        $sent = [];
        $notifier = new Notifier([
            new class implements NotificationChannel
            {
                public function name(): string
                {
                    return 'broken';
                }

                public function checkAvailable(): void {}

                public function send(string $subject, string $markdown): void
                {
                    throw new RuntimeException('webhook is down');
                }
            },
            new class($sent) implements NotificationChannel
            {
                public function __construct(private array &$sent) {}

                public function name(): string
                {
                    return 'working';
                }

                public function checkAvailable(): void {}

                public function send(string $subject, string $markdown): void
                {
                    $this->sent[] = $subject;
                }
            },
        ]);

        $results = $notifier->send('Test', 'Body');

        // Never throws: a notification failure must not abort a scheduled job
        // that has already done its real work.
        $this->assertFalse($results[0]['delivered']);
        $this->assertSame('webhook is down', $results[0]['error']);
        $this->assertTrue($results[1]['delivered']);
        $this->assertSame(['Test'], $sent);
    }

    public function test_the_default_channel_is_log_only(): void
    {
        // Nothing leaves the machine until an operator says so.
        config(['notifications.channels' => 'log']);

        $this->assertSame(['log'], (new Notifier())->channelNames());
    }

    public function test_an_unconfigured_channel_reports_why_it_cannot_deliver(): void
    {
        config([
            'notifications.channels' => 'discord',
            'notifications.discord_webhook_url' => null,
        ]);

        $status = (new Notifier())->status();

        $this->assertFalse($status[0]['available']);
        // "Why not" is the whole value of the check.
        $this->assertStringContainsString('DISCORD_WEBHOOK_URL', $status[0]['reason']);
    }

    public function test_an_unknown_channel_is_rejected_by_name(): void
    {
        config(['notifications.channels' => 'carrier_pigeon']);

        $this->expectException(\InvalidArgumentException::class);
        new Notifier();
    }

    // --------------------------------------------------------------- endpoint

    public function test_the_alerts_endpoint_hides_baseline_bookkeeping(): void
    {
        $this->opportunity('Anything', ['opportunity_score' => 60]);
        app(AlertDetector::class)->detect();

        $types = collect($this->getJson('/api/v1/alerts')->json('data'))->pluck('title');

        $this->assertFalse($types->contains(fn (string $t) => str_contains($t, 'Baseline recorded')));
    }

    public function test_the_alerts_endpoint_can_filter_to_pending(): void
    {
        $this->opportunity('Ready', ['recommendation' => 'SELL_PILOT']);
        app(AlertDetector::class)->detect();

        $response = $this->getJson('/api/v1/alerts?pending=1');

        $response->assertOk();
        $this->assertGreaterThan(0, $response->json('meta.pending'));
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
            'opportunity_score' => 60,
            'confidence_score' => 40,
            'recommendation' => 'WATCH',
            'score_components' => [],
        ], $attributes));
    }
}
