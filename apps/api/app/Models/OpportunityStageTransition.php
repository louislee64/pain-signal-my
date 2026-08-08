<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * One recorded stage decision.
 *
 * `evidence_snapshot` is denormalised on purpose: the underlying rows keep
 * changing, and the question this table answers is "what did we know when we
 * decided", which a live join can never reconstruct. §57 needs that to
 * recalibrate weights against real outcomes.
 */
class OpportunityStageTransition extends Model
{
    const UPDATED_AT = null;

    protected $fillable = [
        'opportunity_id',
        'from_status',
        'to_status',
        'suggested_status_at_time',
        'note',
        'evidence_snapshot',
    ];

    protected $casts = [
        'evidence_snapshot' => 'array',
        'created_at' => 'datetime',
    ];

    public function opportunity(): BelongsTo
    {
        return $this->belongsTo(Opportunity::class);
    }
}
