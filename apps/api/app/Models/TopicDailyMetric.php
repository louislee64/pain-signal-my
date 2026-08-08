<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class TopicDailyMetric extends Model
{
    protected $fillable = [
        'date',
        'topic_id',
        'region',
        'industry_id',
        'mention_count',
        'source_count',
        'avg_severity',
        'avg_urgency',
        'trend_score',
        'official_score',
        'pain_score',
        'commercial_score',
        'opportunity_score',
    ];

    protected $casts = [
        'date' => 'date',
    ];

    public function topic(): BelongsTo
    {
        return $this->belongsTo(Topic::class);
    }
}
