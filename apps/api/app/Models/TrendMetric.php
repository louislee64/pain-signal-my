<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class TrendMetric extends Model
{
    protected $fillable = [
        'date',
        'keyword_id',
        'country',
        'region',
        'interest',
        'rolling_7d',
        'rolling_30d',
        'baseline_90d',
        'growth_7d',
        'growth_30d',
        'growth_score',
        'z_score',
        'collection_method',
        'collection_batch',
    ];

    protected $casts = [
        // Plain Y-m-d, not a full ISO timestamp: this is a calendar date with no
        // time component, and chart consumers should not have to strip one off.
        'date' => 'date:Y-m-d',
        'interest' => 'integer',
    ];

    public function keyword(): BelongsTo
    {
        return $this->belongsTo(Keyword::class);
    }
}
