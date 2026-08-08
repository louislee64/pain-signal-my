<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Source extends Model
{
    protected $fillable = [
        'name',
        'slug',
        'source_type',
        'base_url',
        'collector',
        'config',
        'collection_method',
        'rate_limit',
        'reliability_score',
        'license',
        'terms_url',
        'terms_status',
        'personal_data_risk',
        'enabled',
        'last_synced_at',
        'last_dataset_updated_at',
    ];

    protected $casts = [
        'config' => 'array',
        'enabled' => 'boolean',
        'reliability_score' => 'integer',
        'last_synced_at' => 'datetime',
        'last_dataset_updated_at' => 'datetime',
    ];

    public function ingestionRuns(): HasMany
    {
        return $this->hasMany(IngestionRun::class);
    }

    /**
     * Days without a run after which a source counts as stale.
     */
    public const STALE_AFTER_DAYS = 7;

    /**
     * This source's state as a status plus the reasons behind it.
     *
     * Lives on the model rather than in the controller because two pages ask
     * the question — the overview's collection block and the source-health page.
     * Two implementations would drift, and the drift would be silent: the
     * overview would show "0 problems" while the health page listed three.
     *
     * Reasons are a list, not a message: a source can be both stale and
     * returning nothing, and collapsing that to whichever check ran first hides
     * half the problem. `ok` with an empty reason list is the only healthy
     * shape, so a check added later cannot pass by default.
     *
     * @param  IngestionRun|null  $lastRun  Pass the already-loaded latest run to
     *                                      avoid a query per source in a list.
     */
    public function health(?IngestionRun $lastRun = null): array
    {
        if (! $this->enabled) {
            return ['status' => 'disabled', 'reasons' => ['Source is disabled in config/sources.yaml']];
        }

        $last = $lastRun ?? $this->ingestionRuns()->orderByDesc('started_at')->first();

        if ($last === null) {
            return ['status' => 'never_run', 'reasons' => ['No ingestion run recorded yet']];
        }

        $reasons = [];
        $status = 'ok';

        if ($last->status !== 'succeeded') {
            $status = 'failing';
            $reasons[] = "Last run {$last->status}";
        }

        if ($last->error_count > 0) {
            $status = $status === 'ok' ? 'degraded' : $status;
            $reasons[] = "{$last->error_count} error(s) in the last run";
        }

        // Succeeded-but-empty. No error is raised anywhere for this, which is
        // exactly why it needs an explicit check: the run is green and every
        // score that depended on this source quietly drains away.
        if ($last->status === 'succeeded' && (int) $last->records_received === 0) {
            $status = $status === 'ok' ? 'degraded' : $status;
            $reasons[] = 'Last run succeeded but received no records';
        }

        if ($last->started_at !== null && $last->started_at->diffInDays(now()) > self::STALE_AFTER_DAYS) {
            $status = $status === 'ok' ? 'stale' : $status;
            $reasons[] = 'No run in over '.self::STALE_AFTER_DAYS.' days';
        }

        if ($last->records_received > 0 && (int) $last->records_rejected === (int) $last->records_received) {
            $status = 'failing';
            $reasons[] = 'Every record in the last run was rejected';
        }

        return ['status' => $status, 'reasons' => $reasons];
    }

    public function rawDocuments(): HasMany
    {
        return $this->hasMany(RawDocument::class);
    }
}
