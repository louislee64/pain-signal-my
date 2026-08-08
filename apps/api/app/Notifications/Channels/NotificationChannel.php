<?php

namespace App\Notifications\Channels;

/**
 * §40's delivery channels, behind one interface.
 *
 * Same pattern as the collectors (M1), trend providers (M3) and LLM providers
 * (M4): an interface, a registry, and `checkAvailable()` that raises an
 * actionable error rather than silently doing nothing. A notification channel
 * that fails quietly is worse than one that is absent — the operator believes
 * they are being told about paid pilots and they are not.
 */
interface NotificationChannel
{
    public function name(): string;

    /**
     * Throw with an actionable message if this channel cannot deliver — missing
     * webhook URL, unconfigured mailer. Never return false; "why not" is the
     * whole value of the check.
     */
    public function checkAvailable(): void;

    /**
     * Deliver one message. `$markdown` is the body; `$subject` is a one-line
     * summary for channels that have a subject (email) or want a lead line
     * (Discord).
     */
    public function send(string $subject, string $markdown): void;
}
