<?php

namespace App\Notifications\Channels;

use Illuminate\Support\Facades\Log;

/**
 * The default channel: writes to the application log.
 *
 * Always available, costs nothing, and — importantly — makes "notifications are
 * off" observable. A no-op default would leave an operator unable to tell a
 * working pipeline with nothing to report from a broken one, whereas a log line
 * proves the report ran and says where the content went.
 */
class LogChannel implements NotificationChannel
{
    public function name(): string
    {
        return 'log';
    }

    public function checkAvailable(): void
    {
        // Nothing to check. This channel exists precisely so there is always one
        // that works.
    }

    public function send(string $subject, string $markdown): void
    {
        Log::info('[notification] '.$subject, [
            'channel' => 'log',
            'body_length' => strlen($markdown),
            'body' => $markdown,
        ]);
    }
}
