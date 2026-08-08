<?php

namespace App\Notifications\Channels;

use Illuminate\Support\Facades\Mail;
use RuntimeException;

/**
 * §40's email channel.
 *
 * Sends the Markdown as plain text rather than rendering it to HTML. The report
 * is written to read acceptably as plain text (that is why it is Markdown), and
 * an HTML email template would be a second rendering path that could disagree
 * with the dashboard about what the report says.
 */
class EmailChannel implements NotificationChannel
{
    /**
     * @param  list<string>  $recipients
     */
    public function __construct(
        private readonly array $recipients,
        private readonly ?string $from = null,
    ) {}

    public function name(): string
    {
        return 'email';
    }

    public function checkAvailable(): void
    {
        if ($this->recipients === []) {
            throw new RuntimeException(
                'Email channel needs REPORT_EMAIL_TO (comma-separated). See docs/reporting.md.'
            );
        }

        foreach ($this->recipients as $recipient) {
            if (! filter_var($recipient, FILTER_VALIDATE_EMAIL)) {
                throw new RuntimeException("REPORT_EMAIL_TO contains an invalid address: {$recipient}");
            }
        }

        // The default mailer in a fresh install is `log`, which "works" and
        // delivers nothing. Saying so is more useful than a silent success that
        // an operator discovers a month later.
        $mailer = config('mail.default');
        if ($mailer === 'log') {
            throw new RuntimeException(
                'MAIL_MAILER is `log`, so email would be written to the log rather than sent. '
                .'Configure a real mailer, or use the `log` notification channel deliberately.'
            );
        }
    }

    public function send(string $subject, string $markdown): void
    {
        $this->checkAvailable();

        Mail::raw($markdown, function ($message) use ($subject) {
            $message->subject($subject)->to($this->recipients);

            if ($this->from !== null) {
                $message->from($this->from);
            }
        });
    }
}
