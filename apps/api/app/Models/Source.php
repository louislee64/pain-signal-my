<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Source extends Model
{
    protected $fillable = [
        'name',
        'slug',
        'source_type',
        'base_url',
        'collector',
        'config',
        'collection_method',
        'rate_limit',
        'reliability_score',
        'license',
        'terms_url',
        'terms_status',
        'personal_data_risk',
        'enabled',
        'last_synced_at',
        'last_dataset_updated_at',
    ];

    protected $casts = [
        'config' => 'array',
        'enabled' => 'boolean',
        'reliability_score' => 'integer',
        'last_synced_at' => 'datetime',
        'last_dataset_updated_at' => 'datetime',
    ];

    public function ingestionRuns(): HasMany
    {
        return $this->hasMany(IngestionRun::class);
    }

    public function rawDocuments(): HasMany
    {
        return $this->hasMany(RawDocument::class);
    }
}
