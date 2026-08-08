<?php

namespace App\Notifications\Channels;

use Illuminate\Support\Facades\Http;
use RuntimeException;

/**
 * §40's Discord channel, via an incoming webhook.
 *
 * A webhook rather than a bot because the requirement is one-way delivery: a bot
 * would mean an application, a token, a gateway connection and a permissions
 * model, all to post a message.
 */
class DiscordChannel implements NotificationChannel
{
    /**
     * Discord rejects messages over 2000 characters outright. A weekly report is
     * comfortably longer, so it is split rather than truncated — losing the
     * Build Recommendation section (the last one) to a silent cut would remove
     * the most actionable part of the document.
     */
    private const MAX_LENGTH = 1900;

    public function __construct(
        private readonly ?string $webhookUrl,
        private readonly int $timeout = 15,
    ) {}

    public function name(): string
    {
        return 'discord';
    }

    public function checkAvailable(): void
    {
        if (blank($this->webhookUrl)) {
            throw new RuntimeException(
                'Discord channel needs DISCORD_WEBHOOK_URL. See docs/reporting.md.'
            );
        }

        if (! str_starts_with($this->webhookUrl, 'https://')) {
            throw new RuntimeException('DISCORD_WEBHOOK_URL must be an https URL.');
        }
    }

    public function send(string $subject, string $markdown): void
    {
        $this->checkAvailable();

        $chunks = $this->chunk("**{$subject}**\n\n".$markdown);

        foreach ($chunks as $index => $chunk) {
            $response = Http::timeout($this->timeout)
                ->asJson()
                ->post($this->webhookUrl, ['content' => $chunk]);

            if ($response->failed()) {
                throw new RuntimeException(sprintf(
                    'Discord webhook returned %d on part %d/%d: %s',
                    $response->status(),
                    $index + 1,
                    count($chunks),
                    // Discord's error bodies name the actual problem (bad
                    // webhook, rate limit), so passing it through beats a
                    // generic failure message.
                    str($response->body())->limit(300),
                ));
            }
        }
    }

    /**
     * Split on blank lines, so a chunk boundary never lands mid-table or
     * mid-sentence. Falls back to a hard cut only for a single paragraph that is
     * itself over the limit.
     */
    private function chunk(string $text): array
    {
        if (strlen($text) <= self::MAX_LENGTH) {
            return [$text];
        }

        $chunks = [];
        $current = '';

        foreach (explode("\n\n", $text) as $paragraph) {
            if (strlen($paragraph) > self::MAX_LENGTH) {
                if ($current !== '') {
                    $chunks[] = $current;
                    $current = '';
                }
                foreach (str_split($paragraph, self::MAX_LENGTH) as $piece) {
                    $chunks[] = $piece;
                }

                continue;
            }

            $candidate = $current === '' ? $paragraph : $current."\n\n".$paragraph;

            if (strlen($candidate) > self::MAX_LENGTH) {
                $chunks[] = $current;
                $current = $paragraph;
            } else {
                $current = $candidate;
            }
        }

        if ($current !== '') {
            $chunks[] = $current;
        }

        return $chunks;
    }
}
