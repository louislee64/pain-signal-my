<?php

namespace App\Console\Commands;

use App\Models\Alert;
use App\Notifications\Notifier;
use App\Services\AlertDetector;
use Illuminate\Console\Command;

/**
 * §40's alerting.
 *
 * Detection and delivery are separate passes over separate state, so a delivery
 * outage does not lose alerts: they stay pending and go out on the next run, in
 * the order they happened.
 */
class CheckAlerts extends Command
{
    protected $signature = 'alerts:check
        {--notify : Deliver pending alerts via the configured channels}
        {--limit=20 : Maximum alerts to deliver in one run}';

    protected $description = 'Evaluate §40 alert conditions and optionally deliver what is newly true';

    public function handle(AlertDetector $detector): int
    {
        $result = $detector->detect();

        $this->info(sprintf(
            '%d new alert(s), %d already reported.',
            count($result['detected']),
            $result['skipped_duplicates'],
        ));

        foreach ($result['detected'] as $alert) {
            $this->line("  [{$alert->severity}] {$alert->title}");
        }

        if (! $this->option('notify')) {
            $pending = $detector->pending()->count();
            if ($pending > 0) {
                $this->comment("{$pending} alert(s) pending delivery. Re-run with --notify to send.");
            }

            return self::SUCCESS;
        }

        $notifier = new Notifier();
        $this->line('Channels: '.implode(', ', $notifier->channelNames()));

        $pending = $detector->pending()->take((int) $this->option('limit'));

        if ($pending->isEmpty()) {
            $this->info('Nothing pending delivery.');

            return self::SUCCESS;
        }

        foreach ($pending as $alert) {
            $results = $notifier->send(
                "[{$alert->severity}] {$alert->title}",
                $alert->body."\n\n*Detected ".$alert->detected_at->toDateTimeString().'*',
            );

            $delivered = collect($results)->where('delivered', true);

            if ($delivered->isNotEmpty()) {
                $alert->update([
                    'delivered_at' => now(),
                    'delivered_via' => $delivered->pluck('channel')->implode(','),
                    'delivery_error' => null,
                ]);
                $this->info("  sent: {$alert->title}");
            } else {
                // Left pending on purpose so the next run retries. The error is
                // recorded so a persistent failure is visible rather than looking
                // like nothing ever happened.
                $alert->update([
                    'delivery_error' => collect($results)->pluck('error')->filter()->implode('; '),
                ]);
                $this->error("  failed: {$alert->title} — {$alert->delivery_error}");
            }
        }

        return self::SUCCESS;
    }
}
