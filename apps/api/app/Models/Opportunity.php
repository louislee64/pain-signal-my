<?php

namespace App\Models;

use App\Support\CommercialStage;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\Relations\HasOne;

class Opportunity extends Model
{
    protected $fillable = [
        'topic_id', 'title', 'description', 'industry_id', 'target_buyer', 'status',
        'suggested_status', 'status_changed_at', 'status_note',
        'pain_score', 'commercial_score', 'opportunity_score', 'confidence_score',
        'recommendation', 'score_components', 'scoring_config_version', 'scored_at',
        'problem_statement', 'existing_workaround', 'possible_solution', 'monetization_model',
    ];

    protected $casts = [
        'score_components' => 'array',
        'scored_at' => 'datetime',
        'status_changed_at' => 'datetime',
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

    public function interviews(): HasMany
    {
        return $this->hasMany(CustomerInterview::class);
    }

    public function commercialEvidence(): HasMany
    {
        return $this->hasMany(CommercialEvidence::class);
    }

    public function experiments(): HasMany
    {
        return $this->hasMany(Experiment::class);
    }

    public function stageTransitions(): HasMany
    {
        return $this->hasMany(OpportunityStageTransition::class);
    }

    /** §56's ultimate KPI: money actually received. */
    public function revenue(): HasMany
    {
        return $this->hasMany(OpportunityRevenue::class);
    }

    /** §58: one conclusion per opportunity — concluding twice is an edit. */
    public function outcome(): HasOne
    {
        return $this->hasOne(OpportunityOutcome::class);
    }

    /**
     * The counts §7's gates are decided on.
     *
     * One method, because the gate checks, the stage suggestion, the API
     * response and the transition snapshot must all be looking at the same
     * numbers. Four callers computing "how many independent businesses
     * confirmed this" four times would eventually disagree, and the disagreement
     * would surface as an opportunity that the UI says can be promoted and the
     * API then refuses.
     *
     * Deliberately counts rows, not scores. A gate is a question about what
     * happened ("did anyone pay?"), and answering it from a weighted score would
     * make the answer depend on config.
     */
    public function evidenceSummary(): array
    {
        $interviews = $this->interviews;
        $evidence = $this->commercialEvidence;

        $confirmed = $interviews->filter(fn (CustomerInterview $i) => $i->problem_confirmed === true);

        // Gate 3 asks for independent *businesses*, not interviews. Two
        // conversations at the same company are one business's opinion, so
        // distinct company_ref is the count that matters. Interviews with no
        // company_ref cannot be shown to be independent and so do not count
        // toward it — they remain evidence for Gate 2, which only needs one.
        $independentConfirmations = $confirmed
            ->pluck('company_ref')
            ->filter()
            ->unique()
            ->count();

        $paid = $evidence->filter(
            fn (CommercialEvidence $e) => in_array($e->evidence_type, CommercialEvidence::PAID_TYPES, true)
        );

        return [
            'interview_count' => $interviews->count(),
            'problem_confirmed_count' => $confirmed->count(),
            'problem_denied_count' => $interviews
                ->filter(fn (CustomerInterview $i) => $i->problem_confirmed === false)
                ->count(),
            'independent_confirmations' => $independentConfirmations,

            'evidence_count' => $evidence->count(),
            'has_strong_commercial_signal' => $evidence->contains(
                fn (CommercialEvidence $e) => in_array(
                    $e->evidence_type, CommercialEvidence::STRONG_SIGNAL_TYPES, true
                )
            ),
            'paid_pilot_count' => $evidence
                ->filter(fn (CommercialEvidence $e) => $e->evidence_type === 'paid_pilot')
                ->count(),
            'paid_evidence_count' => $paid->count(),

            // Gate 5 is a second paying *business*. Two pilots with one customer
            // prove retention, not repeatability.
            'paying_business_count' => $paid->pluck('company_ref')->filter()->unique()->count(),

            'pilot_interest_count' => $interviews
                ->filter(fn (CustomerInterview $i) => $i->pilot_interest === true)
                ->count(),
            'experiment_count' => $this->experiments->count(),

            // Gate 1 is a recorded buyer hypothesis, which is what target_buyer
            // is. Nothing else on the row implies one.
            'has_buyer_hypothesis' => filled($this->target_buyer),

            'total_recorded_value' => (float) $evidence->sum(fn (CommercialEvidence $e) => (float) $e->value),
        ];
    }

    /**
     * The furthest stage the recorded evidence supports.
     *
     * A suggestion only. §52: the pipeline never writes `status`.
     */
    public function suggestedStage(?array $evidence = null): string
    {
        return CommercialStage::suggestFrom($evidence ?? $this->evidenceSummary());
    }
}
