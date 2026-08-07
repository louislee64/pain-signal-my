<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class IngestionRun extends Model
{
    const UPDATED_AT = null;

    const CREATED_AT = null;

    protected $fillable = [
        'source_id',
        'started_at',
        'finished_at',
        'status',
        'records_received',
        'records_inserted',
        'records_updated',
        'records_rejected',
        'error_count',
        'metadata_json',
    ];

    protected $casts = [
        'started_at' => 'datetime',
        'finished_at' => 'datetime',
        'metadata_json' => 'array',
    ];

    public function source(): BelongsTo
    {
        return $this->belongsTo(Source::class);
    }
}
