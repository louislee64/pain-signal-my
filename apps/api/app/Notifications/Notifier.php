<?php

namespace App\Notifications;

use App\Notifications\Channels\DiscordChannel;
use App\Notifications\Channels\EmailChannel;
use App\Notifications\Channels\LogChannel;
use App\Notifications\Channels\NotificationChannel;
use Illuminate\Support\Facades\Log;
use InvalidArgumentException;

/**
 * Delivery across §40's configured channels.
 *
 * Defaults to `log` only. Nothing leaves this machine until an operator names a
 * channel in config — the same posture as LLM extraction in Milestone 4, and for
 * the same reason: a system that emails or posts to Discord as a side effect of
 * someone running a command is a system that has surprised its operator, and
 * this one posts commercial findings.
 *
 * Failures are per-channel. A broken Discord webhook must not stop the email, and
 * neither must stop the report being stored — the report is the deliverable and
 * the notification is a courtesy.
 */
class Notifier
{
    /** @var list<NotificationChannel> */
    private array $channels;

    /** @param list<NotificationChannel>|null $channels */
    public function __construct(?array $channels = null)
    {
        $this->channels = $channels ?? self::fromConfig();
    }

    /**
     * @return list<NotificationChannel>
     */
    public static function fromConfig(): array
    {
        $names = collect(explode(',', (string) config('notifications.channels', 'log')))
            ->map(fn (string $name) => trim($name))
            ->filter()
            ->unique()
            ->values();

        return $names->map(fn (string $name) => self::make($name))->all();
    }

    public static function make(string $name): NotificationChannel
    {
        return match ($name) {
            'log' => new LogChannel(),
            'discord' => new DiscordChannel(config('notifications.discord_webhook_url')),
            'email' => new EmailChannel(
                recipients: collect(explode(',', (string) config('notifications.email_to')))
                    ->map(fn (string $address) => trim($address))
                    ->filter()
                    ->values()
                    ->all(),
                from: config('notifications.email_from'),
            ),
            default => throw new InvalidArgumentException(
                "Unknown notification channel '{$name}'. Registered: log, discord, email."
            ),
        };
    }

    /**
     * Report which channels could deliver right now, and why the others cannot.
     *
     * Exists so an operator can find out before a report is due rather than by
     * noticing a missing message afterwards.
     */
    public function status(): array
    {
        return collect($this->channels)->map(function (NotificationChannel $channel) {
            try {
                $channel->checkAvailable();

                return ['channel' => $channel->name(), 'available' => true, 'reason' => null];
            } catch (\Throwable $e) {
                return ['channel' => $channel->name(), 'available' => false, 'reason' => $e->getMessage()];
            }
        })->all();
    }

    /**
     * Send to every configured channel, collecting results.
     *
     * Never throws. A notification failure is reported to the caller and logged;
     * it does not become an exception that aborts a scheduled job which has
     * already done its real work.
     */
    public function send(string $subject, string $markdown): array
    {
        $results = [];

        foreach ($this->channels as $channel) {
            try {
                $channel->send($subject, $markdown);
                $results[] = ['channel' => $channel->name(), 'delivered' => true, 'error' => null];
            } catch (\Throwable $e) {
                Log::warning('[notification] delivery failed', [
                    'channel' => $channel->name(),
                    'error' => $e->getMessage(),
                ]);
                $results[] = ['channel' => $channel->name(), 'delivered' => false, 'error' => $e->getMessage()];
            }
        }

        return $results;
    }

    /** @return list<string> */
    public function channelNames(): array
    {
        return collect($this->channels)->map(fn (NotificationChannel $c) => $c->name())->all();
    }
}
