<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Opportunity extends Model
{
    protected $fillable = [
        'topic_id', 'title', 'description', 'industry_id', 'target_buyer', 'status',
        'pain_score', 'commercial_score', 'opportunity_score', 'confidence_score',
        'recommendation', 'score_components', 'scoring_config_version', 'scored_at',
        'problem_statement', 'existing_workaround', 'possible_solution', 'monetization_model',
    ];

    protected $casts = [
        'score_components' => 'array',
        'scored_at' => 'datetime',
        // Explicit decimal casts so the JSON shape is identical on Postgres
        // (production) and sqlite (the test suite). Without them the two
        // drivers serialize DECIMAL differently — 42 vs "42.00" — and an API
        // consumer would be parsing a different type depending on which
        // database happened to answer.
        'pain_score' => 'decimal:2',
        'commercial_score' => 'decimal:2',
        'opportunity_score' => 'decimal:2',
        'confidence_score' => 'decimal:2',
    ];

    public function topic(): BelongsTo
    {
        return $this->belongsTo(Topic::class);
    }
}
