<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * §21 — a test run against an opportunity.
 *
 * `hypothesis` and `success_metric` are required. An experiment without a stated
 * bar for success cannot fail, so it records effort rather than evidence.
 */
class Experiment extends Model
{
    public const TYPES = [
        'landing_page',
        'customer_interview',
        'cold_outreach',
        'manual_service',
        'paid_report',
        'paid_pilot',
        'prototype',
    ];

    public const STATUSES = ['planned', 'running', 'completed', 'abandoned'];

    protected $fillable = [
        'opportunity_id',
        'hypothesis',
        'experiment_type',
        'success_metric',
        'status',
        'result',
        'succeeded',
        'started_at',
        'completed_at',
    ];

    protected $casts = [
        'succeeded' => 'boolean',
        'started_at' => 'datetime',
        'completed_at' => 'datetime',
    ];

    public function opportunity(): BelongsTo
    {
        return $this->belongsTo(Opportunity::class);
    }
}
