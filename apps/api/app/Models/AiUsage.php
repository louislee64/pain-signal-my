<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class AiUsage extends Model
{
    protected $table = 'ai_usage';

    const UPDATED_AT = null;

    protected $fillable = [
        'provider', 'model', 'operation', 'input_tokens', 'output_tokens',
        'estimated_cost', 'currency', 'document_id', 'prompt_version',
        'processing_version', 'succeeded', 'error',
    ];

    protected $casts = [
        'succeeded' => 'boolean',
        'input_tokens' => 'integer',
        'output_tokens' => 'integer',
    ];
}
