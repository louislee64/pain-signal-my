<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\Relations\HasOne;

class Topic extends Model
{
    protected $fillable = [
        'parent_id',
        'slug',
        'name',
        'description',
        'enabled',
    ];

    protected $casts = [
        'enabled' => 'boolean',
    ];

    public function parent(): BelongsTo
    {
        return $this->belongsTo(Topic::class, 'parent_id');
    }

    public function children(): HasMany
    {
        return $this->hasMany(Topic::class, 'parent_id');
    }

    public function problemSignals(): HasMany
    {
        return $this->hasMany(ProblemSignal::class);
    }

    /** One opportunity per topic — the scoring engine refreshes in place. */
    public function opportunity(): HasOne
    {
        return $this->hasOne(Opportunity::class);
    }
}
