<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * §7 Gate 2 — one real conversation with one real business.
 *
 * Deliberately holds no name, email, phone or company name (§21: "Avoid
 * collecting unnecessary personal information"). `company_ref` is a
 * pseudonymous label whose only job is to tell businesses apart for Gate 3's
 * independent-business count.
 */
class CustomerInterview extends Model
{
    protected $fillable = [
        'opportunity_id',
        'company_ref',
        'industry',
        'company_size',
        'respondent_role',
        'problem_confirmed',
        'frequency_score',
        'severity_score',
        'estimated_cost_score',
        'urgency_score',
        'existing_solution',
        'current_workaround',
        'current_spend_range',
        'existing_budget',
        'willingness_to_pay',
        'pilot_interest',
        'notes',
        'interviewed_at',
    ];

    protected $casts = [
        // Nullable booleans, not defaulted: "they said no" and "we have not
        // asked" are different findings and only one is a negative result.
        'problem_confirmed' => 'boolean',
        'pilot_interest' => 'boolean',
        'interviewed_at' => 'datetime',
        'frequency_score' => 'integer',
        'severity_score' => 'integer',
        'estimated_cost_score' => 'integer',
        'urgency_score' => 'integer',
    ];

    public function opportunity(): BelongsTo
    {
        return $this->belongsTo(Opportunity::class);
    }
}
