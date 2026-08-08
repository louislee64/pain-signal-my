<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Keyword extends Model
{
    public const SOURCE_CONFIG = 'config';

    public const SOURCE_DISCOVERED = 'discovered';

    protected $fillable = [
        'keyword',
        'keyword_group',
        'language',
        'geo',
        'source',
        'enabled',
    ];

    protected $casts = [
        'enabled' => 'boolean',
    ];

    public function trendMetrics(): HasMany
    {
        return $this->hasMany(TrendMetric::class);
    }
}
