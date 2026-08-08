<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * §40's alerts.
 *
 * `dedupe_key` is what makes an alert fire once. §40's conditions are standing
 * facts ("opportunity reaches SELL_PILOT"), not events, so re-evaluating them on
 * a schedule would re-fire everything still true — and a channel that repeats
 * itself daily gets muted within a week.
 */
class Alert extends Model
{
    protected $fillable = [
        'alert_type', 'severity', 'opportunity_id', 'title', 'body',
        'context', 'dedupe_key', 'detected_at', 'delivered_at',
        'delivered_via', 'delivery_error',
    ];

    protected $casts = [
        'context' => 'array',
        'detected_at' => 'datetime',
        'delivered_at' => 'datetime',
    ];

    public function opportunity(): BelongsTo
    {
        return $this->belongsTo(Opportunity::class);
    }
}
