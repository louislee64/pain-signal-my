<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

/**
 * §39's weekly report, stored (§55's "report history").
 *
 * `markdown` is frozen at generation time rather than re-rendered on view. A
 * report that changed under the reader would be useless as a record of what was
 * known when a decision was made.
 */
class Report extends Model
{
    protected $fillable = [
        'report_type', 'period_start', 'period_end', 'title',
        'sections', 'markdown', 'inputs', 'content_hash', 'generated_at',
    ];

    protected $casts = [
        'sections' => 'array',
        'inputs' => 'array',
        'period_start' => 'date',
        'period_end' => 'date',
        'generated_at' => 'datetime',
    ];
}
