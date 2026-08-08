<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * §21 — one discrete piece of human commercial evidence.
 *
 * The table §29's 79-point cap waits for: until a row lands here, no amount of
 * inferred signal can present an opportunity as a certainty.
 */
class CommercialEvidence extends Model
{
    protected $table = 'commercial_evidence';

    /** §21's nine types, ordered weakest to strongest (§31's hierarchy). */
    public const TYPES = [
        'customer_request',
        'interview',
        'pilot_interest',
        'proposal',
        'existing_spend',
        'purchase_order',
        'deposit',
        'paid_pilot',
        'repeat_customer',
    ];

    /**
     * The types §7 Gate 3 accepts as "at least one strong commercial signal".
     *
     * `pilot_interest` is deliberately NOT here. §7 Gate 4 is explicit that a
     * customer paying is "considerably more valuable than 'I would probably use
     * this'", and stated interest is the polite end of that sentence, not
     * evidence of budget.
     */
    public const STRONG_SIGNAL_TYPES = [
        'proposal',
        'deposit',
        'purchase_order',
        'existing_spend',
        'paid_pilot',
        'repeat_customer',
    ];

    /** Money actually changed hands (§7 Gate 4). */
    public const PAID_TYPES = [
        'paid_pilot',
        'deposit',
        'purchase_order',
        'repeat_customer',
    ];

    public const STRENGTHS = ['weak', 'medium', 'strong'];

    protected $fillable = [
        'opportunity_id',
        'evidence_type',
        'strength',
        'value',
        'currency',
        'company_ref',
        'notes',
        'occurred_at',
    ];

    protected $casts = [
        'value' => 'decimal:2',
        'occurred_at' => 'datetime',
    ];

    public function opportunity(): BelongsTo
    {
        return $this->belongsTo(Opportunity::class);
    }
}
