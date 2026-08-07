<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Concerns\HasUlids;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class RawDocument extends Model
{
    use HasUlids;

    const UPDATED_AT = null;

    public $incrementing = false;

    protected $keyType = 'string';

    protected $fillable = [
        'source_id',
        'external_id',
        'url',
        'title',
        'body',
        'published_at',
        'collected_at',
        'content_hash',
        'language_raw',
        'region_raw',
        'metadata_json',
    ];

    protected $casts = [
        'published_at' => 'datetime',
        'collected_at' => 'datetime',
        'metadata_json' => 'array',
    ];

    public function source(): BelongsTo
    {
        return $this->belongsTo(Source::class);
    }
}
