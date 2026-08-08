<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * §56's ultimate KPI: money actually received against a discovered opportunity.
 *
 * Distinct from `commercial_evidence` even though both carry a value. Evidence
 * says *something happened*; this says *money arrived*. A signed proposal is
 * evidence and zero revenue until it is paid.
 */
class OpportunityRevenue extends Model
{
    protected $table = 'opportunity_revenue';

    public const TYPES = [
        'paid_pilot',
        'subscription',
        'one_off_project',
        'retainer',
        'paid_report',
        'licence',
        'other',
    ];

    protected $fillable = [
        'opportunity_id', 'revenue_type', 'amount', 'currency',
        'customer_type', 'company_ref', 'notes', 'received_at',
    ];

    protected $casts = [
        'amount' => 'decimal:2',
        'received_at' => 'date',
    ];

    public function opportunity(): BelongsTo
    {
        return $this->belongsTo(Opportunity::class);
    }
}
