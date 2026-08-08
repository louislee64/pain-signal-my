<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * §58's outcome dataset — what actually happened when someone went and tried.
 *
 * The row that closes §57's feedback loop.
 */
class OpportunityOutcome extends Model
{
    /**
     * §58's nine outcomes, grouped by what they say about the *score*.
     *
     * The grouping is the useful part. `no_budget` and `low_urgency` mean the
     * commercial reading was wrong; `false_signal` means the pain reading was
     * wrong; `too_complex` and `regulatory` mean implementation fit was wrong.
     * §57 asks "which assumption was wrong", and that question is unanswerable
     * without knowing what each outcome indicts.
     */
    public const OUTCOMES = [
        'successful',
        'promising',
        'no_budget',
        'low_urgency',
        'already_solved',
        'poor_fit',
        'too_complex',
        'regulatory',
        'false_signal',
    ];

    /** Outcomes where the developer got paid or is clearly on the way. */
    public const POSITIVE_OUTCOMES = ['successful', 'promising'];

    /**
     * Which score dimension each negative outcome implicates.
     *
     * Deliberately not exhaustive per outcome — an outcome usually indicts one
     * thing, and listing three would dilute the signal into noise.
     */
    public const OUTCOME_IMPLICATES = [
        'no_budget' => 'commercial_score',
        'low_urgency' => 'commercial_score',
        'already_solved' => 'commercial_score',
        'poor_fit' => 'commercial_score',
        'too_complex' => 'commercial_score',
        'regulatory' => 'commercial_score',
        'false_signal' => 'pain_score',
    ];

    protected $fillable = [
        'opportunity_id',
        'initial_score', 'initial_pain_score', 'initial_commercial_score',
        'initial_confidence_score', 'initial_score_components', 'scoring_config_version',
        'buyer_interviews', 'confirmed_buyers', 'proposals_sent',
        'paid_pilots', 'customers', 'revenue', 'currency',
        'outcome', 'reason', 'concluded_at',
    ];

    protected $casts = [
        'initial_score' => 'decimal:2',
        'initial_pain_score' => 'decimal:2',
        'initial_commercial_score' => 'decimal:2',
        'initial_confidence_score' => 'decimal:2',
        'initial_score_components' => 'array',
        'revenue' => 'decimal:2',
        'concluded_at' => 'date',
    ];

    public function opportunity(): BelongsTo
    {
        return $this->belongsTo(Opportunity::class);
    }

    public function isPositive(): bool
    {
        return in_array($this->outcome, self::POSITIVE_OUTCOMES, true);
    }
}
