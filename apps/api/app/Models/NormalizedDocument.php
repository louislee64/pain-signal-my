<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;
use Illuminate\Database\Eloquent\Relations\HasMany;

class NormalizedDocument extends Model
{
    // The table has no created_at/updated_at at all — `processed_at` is the
    // only time this row cares about. Both constants must be nulled, not just
    // UPDATED_AT: Eloquent otherwise writes a created_at column that does not
    // exist, and nothing had inserted through this model until now so the gap
    // stayed hidden.
    const CREATED_AT = null;

    const UPDATED_AT = null;

    protected $fillable = [
        'raw_document_id',
        'cleaned_text',
        'language',
        'country',
        'state',
        'city',
        'industry_id',
        'normalized_content_hash',
        'duplicate_of_normalized_document_id',
        'processed_at',
    ];

    protected $casts = [
        'processed_at' => 'datetime',
    ];

    public function rawDocument(): BelongsTo
    {
        return $this->belongsTo(RawDocument::class);
    }

    public function duplicateOf(): BelongsTo
    {
        return $this->belongsTo(NormalizedDocument::class, 'duplicate_of_normalized_document_id');
    }

    public function topics(): BelongsToMany
    {
        return $this->belongsToMany(Topic::class, 'document_topics', 'document_id', 'topic_id')
            ->withPivot(['confidence', 'classification_method', 'model_version']);
    }

    public function problemSignals(): HasMany
    {
        return $this->hasMany(ProblemSignal::class, 'document_id');
    }
}
