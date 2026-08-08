<?php

/*
|--------------------------------------------------------------------------
| Notification channels (PROJECT_SPEC.md §40)
|--------------------------------------------------------------------------
|
| Defaults to `log` alone. Nothing leaves this machine until an operator names
| another channel — the same posture as LLM extraction in config/llm.yaml, and
| for the same reason: a system that posts commercial findings to Discord as a
| side effect of someone running a command has surprised its operator.
|
| These live in Laravel's config rather than in the shared config/*.yaml tree
| because they are secrets (a webhook URL is a credential) and belong in .env,
| not in a file mounted read-only into two containers and committed to git.
|
*/

return [
    // Comma-separated: log, discord, email.
    'channels' => env('NOTIFICATION_CHANNELS', 'log'),

    'discord_webhook_url' => env('DISCORD_WEBHOOK_URL'),

    'email_to' => env('REPORT_EMAIL_TO'),
    'email_from' => env('REPORT_EMAIL_FROM'),
];
