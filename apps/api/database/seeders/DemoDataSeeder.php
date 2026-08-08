<?php

namespace Database\Seeders;

use App\Models\IngestionRun;
use App\Models\NormalizedDocument;
use App\Models\ProblemSignal;
use App\Models\RawDocument;
use App\Models\Source;
use App\Models\Topic;
use Illuminate\Database\Seeder;

/**
 * Demo data for local dashboard work.
 *
 * Milestone 5's acceptance criterion is about what the dashboard *answers*,
 * which cannot be checked against an empty database — and the one real source
 * wired up so far (data.gov.my fuel prices) produces no topic matches by
 * design, since it is price data rather than complaints. So this exists to make
 * the pages verifiable and demonstrable.
 *
 * Everything it creates is prefixed `demo_` and every document says it is
 * fabricated. Two rules follow from that and are load-bearing:
 *
 *   1. It writes signals and evidence, never `opportunities` rows. Scores come
 *      from running `intelligence score` over this data, so what the dashboard
 *      displays is the real engine's output, not a hand-written number that
 *      would make a broken scorer look fine.
 *   2. `php artisan db:seed --class=DemoDataSeeder` is idempotent, and
 *      `demo:purge` removes exactly what it created.
 *
 * Never run this against production. The prefix is what makes that recoverable.
 */
class DemoDataSeeder extends Seeder
{
    public const PREFIX = 'demo_';

    public function run(): void
    {
        $this->command?->warn('Seeding DEMO data (prefix `demo_`). Not for production.');

        $sources = $this->sources();
        $signals = 0;

        foreach ($this->scenarios() as $scenario) {
            $topic = Topic::where('slug', $scenario['topic'])->first();

            if ($topic === null) {
                $this->command?->warn("Skipping {$scenario['topic']}: run `php artisan topics:sync` first.");
                continue;
            }

            foreach ($scenario['signals'] as $index => $signal) {
                $source = $sources[$signal['source']];
                $signals += $this->recordSignal($topic, $source, $signal, $index) ? 1 : 0;
            }
        }

        $this->command?->info("Demo data ready: {$signals} signals across ".count($this->scenarios()).' topics.');
        $this->command?->info('Now run: docker compose exec intelligence python -m intelligence.cli aggregate && ... score');
    }

    /**
     * Three sources with deliberately different health states, so the source
     * page has something to show other than a column of green.
     */
    private function sources(): array
    {
        $definitions = [
            'forum' => [
                'name' => 'DEMO SME operators forum',
                'source_type' => 'forum',
                'reliability_score' => 55,
                'personal_data_risk' => 'low',
                'terms_status' => 'reviewed',
                'run' => ['status' => 'succeeded', 'received' => 180, 'rejected' => 4, 'errors' => 0, 'days_ago' => 0],
            ],
            'association' => [
                'name' => 'DEMO industry association bulletins',
                'source_type' => 'association',
                'reliability_score' => 80,
                'personal_data_risk' => 'none',
                'terms_status' => 'reviewed',
                // Succeeded but empty — the quiet failure the health page exists
                // for. Nothing errors; the numbers just stop moving.
                'run' => ['status' => 'succeeded', 'received' => 0, 'rejected' => 0, 'errors' => 0, 'days_ago' => 1],
            ],
            'agency' => [
                'name' => 'DEMO government agency notices',
                'source_type' => 'official',
                'reliability_score' => 95,
                'personal_data_risk' => 'none',
                'terms_status' => 'reviewed',
                // Stale: last successful run was weeks ago.
                'run' => ['status' => 'succeeded', 'received' => 26, 'rejected' => 0, 'errors' => 0, 'days_ago' => 21],
            ],
        ];

        $sources = [];

        foreach ($definitions as $key => $definition) {
            $source = Source::updateOrCreate(
                ['slug' => self::PREFIX.$key],
                [
                    'name' => $definition['name'],
                    'source_type' => $definition['source_type'],
                    'collector' => 'demo',
                    'config' => ['demo' => true],
                    'collection_method' => 'api',
                    'license' => 'demo-only',
                    'terms_status' => $definition['terms_status'],
                    'personal_data_risk' => $definition['personal_data_risk'],
                    'reliability_score' => $definition['reliability_score'],
                    'enabled' => true,
                ]
            );

            $run = $definition['run'];
            $startedAt = now()->subDays($run['days_ago']);

            IngestionRun::where('source_id', $source->id)->delete();
            IngestionRun::create([
                'source_id' => $source->id,
                'status' => $run['status'],
                'started_at' => $startedAt,
                'finished_at' => $startedAt->copy()->addSeconds(12),
                'records_received' => $run['received'],
                'records_inserted' => $run['received'] - $run['rejected'],
                'records_updated' => 0,
                'records_rejected' => $run['rejected'],
                'error_count' => $run['errors'],
                'metadata_json' => ['demo' => true],
            ]);

            $sources[$key] = $source;
        }

        return $sources;
    }

    private function recordSignal(Topic $topic, Source $source, array $signal, int $index): bool
    {
        $externalId = self::PREFIX.$topic->slug.'_'.$index;
        $date = now()->subDays($signal['days_ago'])->toDateString();
        $text = 'DEMO FABRICATED TEXT — '.$signal['text'];

        $raw = RawDocument::updateOrCreate(
            ['id' => $this->stableUlid($externalId)],
            [
                'source_id' => $source->id,
                'external_id' => $externalId,
                'title' => $signal['title'],
                'body' => $text,
                'url' => 'https://demo.invalid/'.$externalId,
                'content_hash' => hash('sha256', $externalId),
                'published_at' => $date,
                'collected_at' => now(),
            ]
        );

        $document = NormalizedDocument::updateOrCreate(
            ['raw_document_id' => $raw->id],
            [
                'cleaned_text' => $text,
                'language' => $signal['language'] ?? 'en',
                'country' => 'MY',
                'state' => $signal['state'],
                'processed_at' => now(),
            ]
        );

        ProblemSignal::updateOrCreate(
            [
                'document_id' => $document->id,
                'topic_id' => $topic->id,
                'classification_method' => $signal['method'],
            ],
            [
                'signal_date' => $date,
                'region' => $signal['state'],
                'severity_score' => $signal['severity'],
                'urgency_score' => $signal['urgency'],
                'economic_impact_score' => $signal['economic_impact'],
                'frequency_hint' => $signal['frequency'],
                'payer_type' => $signal['payer'],
                'evidence_json' => [
                    'demo' => true,
                    'affected_role' => $signal['affected_role'],
                    'problem_summary' => $signal['title'],
                ] + ($signal['method'] === 'llm_extract_problem_v1'
                    ? ['model' => 'demo-recorded', 'prompt_version' => 'extract_problem_v1', 'confidence' => 0.82]
                    : ['matched_topic_keywords' => $signal['keywords'] ?? []]),
            ]
        );

        return true;
    }

    /**
     * A deterministic ULID per external id, so re-seeding updates the same rows
     * instead of piling up duplicates. Real ULIDs are time-ordered and random;
     * these only need to be stable and correctly shaped (26 Crockford base32
     * characters).
     */
    private function stableUlid(string $key): string
    {
        $alphabet = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';
        $digest = hash('sha256', $key);
        $ulid = '';

        for ($i = 0; $i < 26; $i++) {
            $ulid .= $alphabet[hexdec($digest[$i * 2].$digest[$i * 2 + 1]) % 32];
        }

        return $ulid;
    }

    /**
     * Five topics chosen to exercise different shapes the dashboard has to
     * render: a strong well-evidenced case, a rising one, a single-source one
     * (which §31 should hold back), a code-switched one, and one whose evidence
     * is all months old.
     */
    private function scenarios(): array
    {
        return [
            [
                'topic' => 'billing_invoice',
                'signals' => $this->spread([
                    ['days_ago' => 2, 'state' => 'Selangor', 'source' => 'forum', 'severity' => 82, 'urgency' => 70, 'economic_impact' => 75, 'frequency' => 'monthly', 'payer' => 'business_owner', 'affected_role' => 'admin clerk', 'method' => 'llm_extract_problem_v1', 'title' => 'Month-end payment matching takes three days', 'text' => 'Every month end my admin spends almost three full days matching bank-in slips against invoices. About 400 invoices a month, payments arrive as lump sums.'],
                    ['days_ago' => 4, 'state' => 'Johor', 'source' => 'forum', 'severity' => 74, 'urgency' => 65, 'economic_impact' => 70, 'frequency' => 'monthly', 'payer' => 'business_owner', 'affected_role' => 'finance staff', 'method' => 'llm_extract_problem_v1', 'title' => 'Chased a customer who had already paid', 'text' => 'We chased a customer for payment twice this year when they had already paid. The reconciliation is done by hand in a spreadsheet.'],
                    ['days_ago' => 7, 'state' => 'Selangor', 'source' => 'association', 'severity' => 68, 'urgency' => 80, 'economic_impact' => 65, 'frequency' => 'monthly', 'payer' => 'accounting_firm', 'affected_role' => 'account executive', 'method' => 'rule_based_keyword_v1', 'keywords' => ['reconcile', 'invoice'], 'title' => 'Members report reconciliation load at month end', 'text' => 'Members consistently report that invoice reconciliation is the single heaviest administrative task at month end.'],
                    ['days_ago' => 11, 'state' => 'Penang', 'source' => 'forum', 'severity' => 79, 'urgency' => 72, 'economic_impact' => 71, 'frequency' => 'monthly', 'payer' => 'business_owner', 'affected_role' => 'admin clerk', 'method' => 'llm_extract_problem_v1', 'title' => 'e-Invoice submission fails near the deadline', 'text' => 'Third time this month the e-invoice submission failed at 11pm on deadline day and the portal returned a blank error.'],
                    ['days_ago' => 16, 'state' => 'Sabah', 'source' => 'agency', 'severity' => 60, 'urgency' => 85, 'economic_impact' => 60, 'frequency' => 'monthly', 'payer' => 'business_owner', 'affected_role' => 'business owner', 'method' => 'rule_based_keyword_v1', 'keywords' => ['myinvois'], 'title' => 'Notice: e-invoice validation rules updated', 'text' => 'Validation rules for submitted e-invoices have been updated. Submitters report confusion between the documentation and the portal behaviour.'],
                    ['days_ago' => 23, 'state' => 'Selangor', 'source' => 'forum', 'severity' => 71, 'urgency' => 60, 'economic_impact' => 68, 'frequency' => 'monthly', 'payer' => 'finance_department', 'affected_role' => 'finance staff', 'method' => 'llm_extract_problem_v1', 'title' => 'Splitting lump-sum payments by hand', 'text' => 'Lump sum payments have to be split across invoices manually in Excel before they can be entered into the accounting system.'],
                ]),
            ],
            [
                'topic' => 'inventory_stock',
                'signals' => $this->spread([
                    ['days_ago' => 1, 'state' => 'Selangor', 'source' => 'forum', 'severity' => 76, 'urgency' => 68, 'economic_impact' => 72, 'frequency' => 'weekly', 'payer' => 'business_owner', 'affected_role' => 'store supervisor', 'method' => 'llm_extract_problem_v1', 'language' => 'ms', 'title' => 'Stock count never matches the system', 'text' => 'Setiap kali nak buat stock count kat cawangan Shah Alam, sistem dengan fizikal tak sama. Last month beza dalam 200 unit.'],
                    ['days_ago' => 3, 'state' => 'Johor', 'source' => 'forum', 'severity' => 70, 'urgency' => 62, 'economic_impact' => 66, 'frequency' => 'weekly', 'payer' => 'operations_manager', 'affected_role' => 'store supervisor', 'method' => 'llm_extract_problem_v1', 'title' => 'Two-day manual recount after every discrepancy', 'text' => 'Any discrepancy means a full manual recount, which costs two days of staff time across the branch.'],
                    ['days_ago' => 5, 'state' => 'Penang', 'source' => 'forum', 'severity' => 66, 'urgency' => 58, 'economic_impact' => 62, 'frequency' => 'weekly', 'payer' => 'business_owner', 'affected_role' => 'cashier', 'method' => 'rule_based_keyword_v1', 'keywords' => ['stock transfer'], 'title' => 'Stock transfers between outlets go unrecorded', 'text' => 'Transfers between outlets are agreed over WhatsApp and often never entered into the system at all.'],
                    ['days_ago' => 9, 'state' => 'Melaka', 'source' => 'association', 'severity' => 64, 'urgency' => 55, 'economic_impact' => 60, 'frequency' => 'monthly', 'payer' => 'erp_pos_provider', 'affected_role' => 'operations manager', 'method' => 'rule_based_keyword_v1', 'keywords' => ['stock discrepancy'], 'title' => 'Multi-outlet retailers cite stock accuracy', 'text' => 'Multi-outlet members cite stock accuracy as their primary operational complaint this quarter.'],
                ]),
            ],
            [
                'topic' => 'software_integration',
                'signals' => $this->spread([
                    ['days_ago' => 2, 'state' => 'Selangor', 'source' => 'forum', 'severity' => 72, 'urgency' => 60, 'economic_impact' => 64, 'frequency' => 'daily', 'payer' => 'business_owner', 'affected_role' => 'cashier', 'method' => 'llm_extract_problem_v1', 'title' => 'POS does not talk to the accounting software', 'text' => 'I key the day sales into the accounting software by hand every evening because the POS does not talk to it. Takes an hour after closing.'],
                    ['days_ago' => 6, 'state' => 'Selangor', 'source' => 'forum', 'severity' => 68, 'urgency' => 56, 'economic_impact' => 62, 'frequency' => 'daily', 'payer' => 'business_owner', 'affected_role' => 'cashier', 'method' => 'llm_extract_problem_v1', 'title' => 'Integration quoted at more than the software costs', 'text' => 'The software vendor quoted more to integrate the two systems than either system costs per year.'],
                    ['days_ago' => 13, 'state' => 'Kuala Lumpur', 'source' => 'forum', 'severity' => 64, 'urgency' => 52, 'economic_impact' => 58, 'frequency' => 'daily', 'payer' => 'saas_provider', 'affected_role' => 'operations manager', 'method' => 'rule_based_keyword_v1', 'keywords' => ['export to excel'], 'title' => 'Everything moves between systems as a spreadsheet', 'text' => 'Every hand-off between our systems is an export to Excel and a re-import. Nothing is automatic.'],
                ]),
            ],
            [
                'topic' => 'workflow_manual_process',
                // Single source on purpose: §31 ranks corroborated evidence
                // above any one source, and the dashboard should visibly hold
                // this back despite otherwise-strong signals.
                'signals' => $this->spread([
                    ['days_ago' => 2, 'state' => 'Selangor', 'source' => 'forum', 'severity' => 88, 'urgency' => 82, 'economic_impact' => 84, 'frequency' => 'daily', 'payer' => 'business_owner', 'affected_role' => 'admin clerk', 'method' => 'llm_extract_problem_v1', 'title' => 'Whole admin team re-types the same data', 'text' => 'The same order data is typed into three different systems by three different people every single day.'],
                    ['days_ago' => 5, 'state' => 'Selangor', 'source' => 'forum', 'severity' => 84, 'urgency' => 78, 'economic_impact' => 80, 'frequency' => 'daily', 'payer' => 'business_owner', 'affected_role' => 'admin clerk', 'method' => 'llm_extract_problem_v1', 'title' => 'Manual re-keying eats the admin week', 'text' => 'Between re-keying orders and chasing confirmations there is no time left for anything else in the admin week.'],
                ]),
            ],
            [
                'topic' => 'compliance_reporting',
                // All evidence months old: the confidence score should decay and
                // the recommendation should not treat this as live.
                'signals' => $this->spread([
                    ['days_ago' => 120, 'state' => 'Kuala Lumpur', 'source' => 'agency', 'severity' => 70, 'urgency' => 90, 'economic_impact' => 72, 'frequency' => 'monthly', 'payer' => 'business_owner', 'affected_role' => 'business owner', 'method' => 'rule_based_keyword_v1', 'keywords' => ['sst'], 'title' => 'SST rate change requires per-SKU tax code updates', 'text' => 'The SST rate change means every product in the system needs its tax code updated one by one, 1200 SKUs in our case.'],
                    ['days_ago' => 145, 'state' => 'Selangor', 'source' => 'association', 'severity' => 64, 'urgency' => 84, 'economic_impact' => 66, 'frequency' => 'monthly', 'payer' => 'accounting_firm', 'affected_role' => 'account executive', 'method' => 'rule_based_keyword_v1', 'keywords' => ['sst'], 'title' => 'Members were penalised for late submissions', 'text' => 'Several members were penalised for late statutory submissions following the rate change.'],
                ]),
            ],
        ];
    }

    /** Fills in the keys every signal needs so the scenarios stay readable. */
    private function spread(array $signals): array
    {
        return array_map(fn (array $signal) => $signal + [
            'language' => 'en',
            'keywords' => [],
        ], $signals);
    }
}
