<?php

namespace Tests\Support;

use App\Models\NormalizedDocument;
use App\Models\ProblemSignal;
use App\Models\RawDocument;
use App\Models\Source;

/**
 * Builds the source → raw_document → normalized_document → problem_signal chain
 * that the dashboard endpoints join across.
 *
 * A signal cannot exist without a document (`document_id` is NOT NULL, and
 * rightly so — a signal with no source text is not evidence), so every test
 * about signals needs the whole chain. Having it in one place keeps the tests
 * about what they assert rather than about fixture plumbing.
 */
trait SeedsSignals
{
    protected function source(string $slug = 'test-source', array $attributes = []): Source
    {
        return Source::firstOrCreate(
            ['slug' => $slug],
            array_merge([
                'name' => "Source {$slug}",
                'source_type' => 'test',
                'collector' => 'test',
                'config' => [],
                'terms_status' => 'reviewed',
                'personal_data_risk' => 'none',
                'reliability_score' => 70,
                'enabled' => true,
            ], $attributes)
        );
    }

    protected function signal(
        int $topicId,
        string $date,
        ?string $region = null,
        int $severity = 50,
        string $method = 'rule_based_keyword_v1',
        string $sourceSlug = 'test-source',
        ?string $payerType = null,
        ?array $evidence = null,
        string $text = 'Reconciling bank-in slips against invoices takes three days every month end.',
    ): ProblemSignal {
        $source = $this->source($sourceSlug);

        $raw = RawDocument::create([
            'id' => (string) str()->ulid(),
            'source_id' => $source->id,
            'external_id' => 'ext-'.str()->random(10),
            'title' => 'Test document',
            'body' => $text,
            'url' => 'https://example.test/'.str()->random(6),
            'content_hash' => hash('sha256', str()->random(24)),
            'collected_at' => now(),
            'published_at' => $date,
        ]);

        $document = NormalizedDocument::create([
            'raw_document_id' => $raw->id,
            'cleaned_text' => $text,
            'language' => 'en',
            'country' => 'MY',
            'state' => $region,
            'processed_at' => now(),
        ]);

        return ProblemSignal::create([
            'document_id' => $document->id,
            'topic_id' => $topicId,
            'signal_date' => $date,
            'region' => $region,
            'severity_score' => $severity,
            'urgency_score' => $severity,
            'economic_impact_score' => $severity,
            'payer_type' => $payerType,
            'evidence_json' => $evidence,
            'classification_method' => $method,
        ]);
    }
}
