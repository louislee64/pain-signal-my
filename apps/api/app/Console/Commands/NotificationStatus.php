<?php

namespace App\Console\Commands;

use App\Notifications\Notifier;
use Illuminate\Console\Command;

/**
 * Report which notification channels could deliver right now.
 *
 * Exists so an operator finds out before a report is due rather than by noticing
 * a missing message afterwards — the same reason `trends check` exists for
 * providers.
 */
class NotificationStatus extends Command
{
    protected $signature = 'notifications:status {--send-test : Send a test message through every available channel}';

    protected $description = 'Report which §40 notification channels are configured and able to deliver';

    public function handle(): int
    {
        $notifier = new Notifier();
        $status = $notifier->status();

        $this->table(
            ['Channel', 'Available', 'Why not'],
            collect($status)->map(fn (array $row) => [
                $row['channel'],
                $row['available'] ? 'yes' : 'no',
                $row['reason'] ?? '',
            ])->all()
        );

        if ($this->option('send-test')) {
            $results = $notifier->send(
                'Pain Radar test notification',
                "This is a test from `php artisan notifications:status --send-test`.\n\n"
                ."If you are reading this, the channel works.",
            );
            foreach ($results as $result) {
                $result['delivered']
                    ? $this->info("sent via {$result['channel']}")
                    : $this->error("{$result['channel']}: {$result['error']}");
            }
        }

        $unavailable = collect($status)->where('available', false)->count();

        // Non-zero when a configured channel cannot deliver: a scheduler or CI
        // step should be able to notice that without parsing the table.
        return $unavailable > 0 ? self::FAILURE : self::SUCCESS;
    }
}
