<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ProblemSignal extends Model
{
    protected $fillable = [
        'document_id',
        'topic_id',
        'signal_date',
        'region',
        'industry_id',
        'severity_score',
        'urgency_score',
        'economic_impact_score',
        'frequency_hint',
        'payer_type',
        'evidence_json',
        'classification_method',
    ];

    protected $casts = [
        'signal_date' => 'date',
        'evidence_json' => 'array',
    ];

    public function document(): BelongsTo
    {
        return $this->belongsTo(NormalizedDocument::class, 'document_id');
    }

    public function topic(): BelongsTo
    {
        return $this->belongsTo(Topic::class);
    }
}
