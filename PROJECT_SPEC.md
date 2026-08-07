# Malaysia SME Pain Radar
## Problem Intelligence, Opportunity Discovery & Commercial Validation Platform

**Working name:** Malaysia SME Pain Radar  
**Repository codename:** `my-pain-radar`  
**Primary market:** Malaysia  
**Initial customer focus:** SMEs, SME service providers, consultants, ERP/POS/accounting providers, agencies, associations  
**Primary objective:** Discover recurring Malaysian business problems from public and official data, quantify their commercial potential, validate willingness to pay, and convert the best opportunities into paid services or SaaS products.

---

# 1. Executive Summary

Malaysia SME Pain Radar is not primarily a sentiment-analysis system and not merely a social-listening dashboard.

Its purpose is to answer:

> "What recurring Malaysian SME problems are growing, expensive enough to matter, technically solvable, and associated with buyers willing to pay for a solution?"

The system will continuously ingest:

- Malaysian government/open datasets
- OpenDOSM datasets
- Google Trends signals
- Publicly accessible reviews and discussions
- App reviews where collection is permitted
- Industry-specific public sources
- Manual customer discovery findings
- Commercial validation results

It will convert these sources into normalized **Problem Signals**.

Problem Signals are grouped into **Problem Topics**.

Each Problem Topic receives two major scores:

1. **Pain Score** — how significant the problem appears to be.
2. **Commercial Score** — how attractive the problem is as a business opportunity.

These produce an overall:

**Opportunity Score**

The platform then produces:

- Daily monitoring
- Opportunity rankings
- Trend detection
- Geographic analysis
- Evidence summaries
- Suggested buyer personas
- Suggested monetization models
- Weekly opportunity reports
- Commercial-validation pipeline
- Paid-pilot tracking
- SaaS/product candidates

The system should optimize for:

**finding businesses worth building, rather than finding interesting statistics.**

---

# 2. Business Thesis

A large social problem does not automatically represent a good business.

For example:

```text
Problem:
Government hospital waiting times.

Pain:
Very high.

Clear buyer:
Unclear.

Ability for a small software company to solve:
Low.

Commercial attractiveness:
Low to medium.
```

Compare with:

```text
Problem:
SMEs repeatedly struggling with inventory reconciliation,
e-Invoice workflows and manual invoice processing.

Pain:
Medium/high.

Buyer:
Business owner.

Economic impact:
Staff time + mistakes + delayed invoicing + compliance risk.

Recurring:
Yes.

Software-solvable:
Yes.

Commercial attractiveness:
High.
```

The system must therefore optimize for the second category.

---

# 3. Core Business Principle

Never make product-development decisions from `pain_score` alone.

Use:

```text
Opportunity
=
Observed Pain
× Buyer Evidence
× Economic Impact
× Recurrence
× Implementation Fit
```

Every opportunity progresses through a commercial funnel:

```text
Observed
    ↓
Investigating
    ↓
Buyer Identified
    ↓
Problem Validated
    ↓
Commercially Validated
    ↓
Paid Pilot
    ↓
Repeatable Solution
    ↓
Product Candidate
    ↓
SaaS / Managed Service
```

An opportunity is not considered commercially validated merely because AI says it is promising.

Commercial validation requires human evidence.

---

# 4. Initial Vertical

Do NOT launch as a general "Malaysia social problem monitoring platform."

Version 1 focuses on:

# Malaysian SME Operational Friction

Initial categories:

```text
billing_invoice
inventory_stock
booking_reservation
customer_service
payment_refund
compliance_reporting
workflow_manual_process
staff_operations
price_cost_pressure
software_integration
data_reporting
customer_retention
```

Possible subtopics:

```text
billing_invoice
├── einvoice
├── reconciliation
├── invoice_generation
├── invoice_delivery
├── accounting_sync
└── payment_matching

inventory_stock
├── stock_accuracy
├── stock_transfer
├── reorder
├── purchase_order
├── stock_count
└── multi_branch_inventory

booking_reservation
├── no_show
├── double_booking
├── manual_whatsapp_booking
├── waiting_list
└── reminder

customer_service
├── slow_response
├── unanswered_whatsapp
├── complaint_tracking
├── refund_request
└── status_updates
```

The taxonomy must be configuration-driven.

Do not hard-code topic names in application logic.

---

# 5. Target Buyers

The first system should evaluate problems affecting these buyer groups:

| Buyer | Examples |
|---|---|
| SME Owner | Retailer, restaurant, distributor |
| Operations Manager | Multi-branch operations |
| Finance Department | Invoice/payment/reconciliation |
| Accounting Firm | SME accounting clients |
| ERP/POS Provider | Businesses needing integrations |
| Business Consultant | Digitalisation projects |
| Industry Association | Member intelligence |
| Agency | Customer-service/marketing operations |
| SaaS Provider | Market/product intelligence |

Store buyer type separately from affected user.

Example:

```text
Affected user:
Cashier

Problem:
Stock updates require duplicate manual entry.

Buyer:
Business owner / operations manager
```

---

# 6. Revenue Strategy

The platform itself does not need to become the first product sold.

Use three monetization levels.

## Level A — Intelligence / Diagnosis

Sell:

- Industry pain reports
- Competitor review analysis
- Operational-friction reports
- Digitalisation audits
- Customer feedback analysis

Potential pricing is determined manually through market validation rather than hard-coded assumptions.

Purpose:

Generate revenue while learning.

---

## Level B — Implementation Services

When repeated pain appears, offer implementation.

Examples:

```text
Problem:
Manual WhatsApp reservation handling.

Solution:
Reservation automation + dashboard + reminders.
```

```text
Problem:
Manual invoice reconciliation.

Solution:
Invoice/payment reconciliation integration.
```

```text
Problem:
Stock discrepancies between outlets.

Solution:
Centralized inventory workflow.
```

This aligns strongly with existing full-stack/API/integration skills.

---

## Level C — SaaS

Only productize something after seeing repeated customer demand.

Possible SaaS products could eventually include:

```text
SME Review Intelligence
SME Complaint Intelligence
Invoice Reconciliation
Reservation Automation
Inventory Alerting
Customer Follow-up Automation
SME Reporting Dashboard
Compliance Workflow Automation
```

The system should help identify which one deserves development.

---

# 7. Commercial Validation Rules

Introduce mandatory **Commercial Gates**.

## Gate 0 — Signal

Requirements:

```text
minimum source diversity
minimum occurrence frequency
sustained trend
```

Result:

`OBSERVED`

---

## Gate 1 — Buyer Hypothesis

Record:

```text
buyer_type
affected_industry
affected_role
possible_budget_owner
existing_solution
current_workaround
```

Result:

`BUYER_IDENTIFIED`

---

## Gate 2 — Customer Discovery

Conduct real conversations.

Store:

```text
company_type
industry
company_size
role
problem_confirmed
frequency
current_workaround
estimated_cost
urgency
existing_budget
willingness_to_pay
notes
```

Do NOT necessarily store identifying personal information.

Result:

`PROBLEM_VALIDATED`

---

## Gate 3 — Commercial Validation

Suggested minimum evidence:

```text
Multiple independent businesses confirm the problem

AND

At least one strong commercial signal:
- willingness to run paid pilot
- signed proposal
- deposit
- purchase order
- existing budget
- existing spending on inferior workaround
```

Result:

`COMMERCIALLY_VALIDATED`

---

## Gate 4 — Paid Pilot

A customer pays money.

Result:

`PAID_PILOT`

This is considerably more valuable than:

```text
"I would probably use this."
```

---

## Gate 5 — Repeatability

Find another business experiencing substantially the same workflow problem.

Result:

`PRODUCT_CANDIDATE`

Only now should major SaaS investment begin.

---

# 8. System Architecture

Recommended architecture:

```text
                        ┌──────────────────────┐
                        │   Public Sources     │
                        │                      │
                        │ data.gov.my          │
                        │ OpenDOSM             │
                        │ Google Trends        │
                        │ Reviews              │
                        │ Forums               │
                        │ Industry Sources     │
                        └──────────┬───────────┘
                                   │
                                   ▼
                        ┌──────────────────────┐
                        │ Python Collectors    │
                        │                      │
                        │ API                  │
                        │ HTTP                 │
                        │ Browser if allowed   │
                        │ File ingestion       │
                        └──────────┬───────────┘
                                   │
                                   ▼
                        ┌──────────────────────┐
                        │ RAW DATA LAYER       │
                        │ PostgreSQL           │
                        └──────────┬───────────┘
                                   │
                                   ▼
                        ┌──────────────────────┐
                        │ Processing Workers   │
                        │                      │
                        │ Clean                │
                        │ Normalize            │
                        │ Deduplicate          │
                        │ Classify             │
                        │ Extract Signals      │
                        └──────────┬───────────┘
                                   │
                                   ▼
                        ┌──────────────────────┐
                        │ Analytics Layer      │
                        │                      │
                        │ Topic metrics        │
                        │ Trend detection      │
                        │ Pain scoring         │
                        │ Commercial scoring   │
                        │ Opportunity ranking  │
                        └──────────┬───────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
          ┌───────────────────┐        ┌───────────────────┐
          │ Laravel API       │        │ Report Generator  │
          │                   │        │                   │
          │ Auth              │        │ Weekly report     │
          │ Opportunity CRM   │        │ Email digest      │
          │ Validation        │        │ PDF later         │
          └─────────┬─────────┘        └───────────────────┘
                    │
                    ▼
          ┌───────────────────┐
          │ Nuxt Dashboard    │
          │                   │
          │ Trends            │
          │ Evidence          │
          │ Opportunities     │
          │ Validation CRM    │
          └───────────────────┘
```

---

# 9. Recommended Technology Stack

Use technologies that fit the developer's existing capabilities.

## Main Application

```text
Backend:
Laravel

Frontend:
Nuxt / Vue

Database:
PostgreSQL

Queue/cache:
Redis

Containers:
Docker / Docker Compose
```

## Data/Analytics

```text
Python

Primary libraries:
pandas
polars where useful
pyarrow
httpx
pydantic
sqlalchemy
scikit-learn
numpy
```

Do not introduce Spark, Kafka or Kubernetes in V1.

They add unnecessary operational complexity.

---

# 10. n8n Role

n8n is optional.

Use n8n for:

```text
report distribution
email notifications
Slack/Discord notifications
manual approval workflows
CRM integrations
external automation
```

Do NOT place critical analytics or scoring logic inside n8n nodes.

Core business rules belong in version-controlled code.

---

# 11. Repository Structure

Use a monorepo.

```text
my-pain-radar/
│
├── apps/
│   ├── api/
│   │   └── Laravel application
│   │
│   ├── web/
│   │   └── Nuxt dashboard
│   │
│   └── intelligence/
│       └── Python package
│
├── packages/
│   ├── taxonomy/
│   ├── schemas/
│   └── shared-config/
│
├── config/
│   ├── topics.yaml
│   ├── keywords.yaml
│   ├── industries.yaml
│   ├── regions.yaml
│   ├── sources.yaml
│   └── scoring.yaml
│
├── data/
│   └── samples/
│
├── docs/
│   ├── architecture.md
│   ├── business-model.md
│   ├── data-model.md
│   ├── source-policy.md
│   ├── scoring-model.md
│   ├── commercial-validation.md
│   └── deployment.md
│
├── infrastructure/
│   ├── docker/
│   ├── nginx/
│   └── scripts/
│
├── tests/
│   ├── fixtures/
│   └── integration/
│
├── .github/
│   └── workflows/
│
├── docker-compose.yml
├── .env.example
├── AGENTS.md
├── CLAUDE.md
├── PROJECT_SPEC.md
└── README.md
```

---

# 12. Source Registry

All collectors must be driven through a source registry.

Example:

```yaml
sources:

  data_gov:
    type: official_api
    country: MY
    enabled: true
    reliability: high
    commercial_usage_reviewed: true

  opendosm:
    type: official_dataset
    country: MY
    enabled: true
    reliability: high

  google_trends_bigquery:
    type: trend
    country: MY
    enabled: true

  public_reviews:
    type: review
    enabled: false
```

Each source should contain:

```text
name
source_type
base_url
collector
collection_method
rate_limit
reliability
license
terms_url
terms_review_status
personal_data_risk
enabled
```

---

# 13. Source Acquisition Policy

Preferred order:

```text
1. Official API
2. Official downloadable dataset
3. Official RSS/feed
4. Licensed third-party API
5. Public web collection where permitted
```

Never build the platform around fragile scraping when an official API exists.

Collectors must support:

```text
rate limiting
timeouts
retry with exponential backoff
incremental synchronization
idempotency
deduplication
checkpointing
logging
metrics
```

---

# 14. Initial Malaysian Official Data

Start by discovering datasets connected to:

```text
consumer prices
food prices
household expenditure
income
SME/business statistics
labour
employment
business activity
retail
services
digital economy
cost of living
industry production
regional economic activity
```

Priority example:

## PriceCatcher

Possible insights:

```text
price inflation by item
price dispersion between regions
abnormal price increases
supplier/retailer differences
regional cost pressure
food category trends
```

Do not simply copy the data into a dashboard.

Derive business signals.

Example:

```text
raw:
Chicken price increased.

derived:
Restaurants in Region X may be experiencing unusual ingredient-cost pressure.

business hypothesis:
Restaurants need margin monitoring / menu costing / supplier price alerts.
```

---

# 15. Google Trends Strategy

Use two separate mechanisms.

## A. Google Trends BigQuery

Use for discovery of:

```text
Top searches
Rising searches
Unexpected topics
New Malaysian attention patterns
```

The international dataset includes top and rising queries.

Use this to discover signals the system did not already know about.

---

## B. Keyword Monitoring

Maintain controlled keyword families.

Example:

```yaml
groups:

  sme_finance:
    - e invoice malaysia
    - e-invois
    - invoice software
    - accounting software
    - payment reconciliation

  inventory:
    - inventory system
    - stock management
    - stock count
    - inventory problem

  restaurant:
    - reservation system
    - restaurant booking
    - restaurant pos
    - whatsapp booking

  cost_pressure:
    - kos sara hidup
    - barang mahal
    - harga makanan
    - supplier price
```

Languages should eventually include:

```text
English
Bahasa Malaysia
Chinese
```

Do not assume one keyword represents an entire problem.

Maintain keyword clusters.

---

# 16. Google Trends Normalization

Never interpret Trends numbers as absolute search volume.

Store:

```text
keyword
keyword_group
geo
date
interest
collection_method
collection_batch
```

Calculate:

```text
rolling_7d
rolling_30d
baseline_90d
growth_7d
growth_30d
z_score
```

Potential signal:

```text
trend_signal =
current_interest / baseline_interest
```

Use Trends as corroborating evidence.

Not as standalone market-size evidence.

---

# 17. Public Text Sources

Phase them carefully.

Potential categories:

```text
public business reviews
application reviews
public forum discussions
industry communities
business-owner discussions
public support complaints
public product reviews
```

For every platform:

```text
review access rules
review API availability
review terms
review robots policy where relevant
avoid bypassing technical controls
store only data necessary for analysis
```

Do not make the entire product dependent on a source whose access could disappear.

---

# 18. Raw Document Model

Every unstructured item should normalize into:

```json
{
  "source": "example",
  "external_id": "12345",
  "url": "...",
  "title": "...",
  "body": "...",
  "published_at": "...",
  "collected_at": "...",
  "language": "en",
  "region": "MY-10",
  "metadata": {}
}
```

Original raw records should be immutable.

Processed results go into separate tables.

---

# 19. Data Layers

Use three logical layers.

## RAW

Exactly what was collected.

Never modify.

## NORMALIZED

Cleaned representation.

Examples:

```text
language normalized
region normalized
HTML removed
duplicates linked
dates normalized
topic candidate assigned
```

## ANALYTICS

Aggregated data:

```text
topic/day/region
topic/week
industry/topic/week
source/topic/day
opportunity score
```

---

# 20. Core PostgreSQL Schema

## sources

```text
id
name
slug
source_type
base_url
collector
reliability_score
license
terms_status
enabled
created_at
updated_at
```

---

## ingestion_runs

```text
id
source_id
started_at
finished_at
status
records_received
records_inserted
records_updated
records_rejected
error_count
metadata_json
```

---

## raw_documents

```text
id
source_id
external_id
url
title
body
published_at
collected_at
content_hash
language_raw
region_raw
metadata_json
created_at
```

Unique:

```text
(source_id, external_id)
```

and/or:

```text
content_hash
```

---

## normalized_documents

```text
id
raw_document_id
cleaned_text
language
country
state
city
industry_id
processed_at
```

---

## topics

```text
id
parent_id
slug
name
description
enabled
```

---

## document_topics

```text
document_id
topic_id
confidence
classification_method
model_version
```

---

## problem_signals

```text
id
document_id
topic_id
signal_date
region
industry_id
severity_score
urgency_score
economic_impact_score
frequency_hint
payer_type
evidence_json
```

---

## trend_metrics

```text
id
date
keyword_id
country
region
interest
rolling_7d
rolling_30d
baseline_90d
growth_score
z_score
```

---

## official_metrics

Generic structure:

```text
id
dataset
metric
date
region
category
value
unit
metadata_json
```

Use specialized tables for very large datasets where necessary.

---

## topic_daily_metrics

```text
id
date
topic_id
region
industry_id
mention_count
source_count
avg_severity
avg_urgency
trend_score
official_score
pain_score
commercial_score
opportunity_score
```

---

## opportunities

```text
id
topic_id
title
description
industry_id
target_buyer
status
pain_score
commercial_score
opportunity_score
problem_statement
existing_workaround
possible_solution
monetization_model
created_at
updated_at
```

---

# 21. Commercial CRM Tables

## customer_interviews

```text
id
opportunity_id
industry
company_size
respondent_role
problem_confirmed
frequency_score
severity_score
estimated_cost_score
urgency_score
existing_solution
current_spend_range
willingness_to_pay
pilot_interest
notes
interviewed_at
```

Avoid collecting unnecessary personal information.

---

## commercial_evidence

```text
id
opportunity_id
evidence_type
strength
value
notes
occurred_at
```

Types:

```text
interview
proposal
pilot_interest
paid_pilot
deposit
purchase_order
existing_spend
customer_request
repeat_customer
```

---

## experiments

```text
id
opportunity_id
hypothesis
experiment_type
success_metric
status
result
started_at
completed_at
```

Examples:

```text
landing_page
customer_interview
cold_outreach
manual_service
paid_report
paid_pilot
prototype
```

---

# 22. Text Processing Pipeline

Pipeline:

```text
RAW TEXT
   ↓
cleanup
   ↓
language detection
   ↓
spam/noise filtering
   ↓
deduplication
   ↓
topic classification
   ↓
problem extraction
   ↓
severity estimation
   ↓
buyer extraction
   ↓
economic impact estimation
   ↓
signal storage
```

---

# 23. Rule-Based First

Do not send everything directly to an LLM.

Use inexpensive deterministic preprocessing first.

Example:

```text
keyword matching
language detection
regex
source metadata
industry dictionaries
duplicate detection
similarity
```

Only send useful candidate documents to the LLM.

Benefits:

```text
lower API cost
higher consistency
better debugging
less hallucination
easier testing
```

---

# 24. LLM Role

LLM should perform bounded extraction.

Do NOT ask:

> "Is this a good business opportunity?"

Instead use structured extraction.

Example input:

```text
Customer review:
"We still need to export our POS sales into Excel every night
and manually enter it into accounting software."
```

Expected JSON:

```json
{
  "problem_present": true,
  "topic": "software_integration",
  "subtopic": "accounting_sync",
  "affected_role": "finance_staff",
  "buyer_type": "business_owner",
  "frequency": "daily",
  "severity": 7,
  "economic_impact": 6,
  "urgency": 6,
  "problem_summary": "Daily manual transfer of POS sales into accounting software.",
  "suggested_solution_category": "integration_automation",
  "confidence": 0.93
}
```

Validate all LLM output with JSON Schema/Pydantic.

Reject malformed results.

---

# 25. Model Abstraction

Do not tightly couple the system to OpenAI, Claude, Gemini or one model.

Create:

```text
LLMProviderInterface
```

Possible adapters:

```text
OpenAIProvider
AnthropicProvider
GeminiProvider
OllamaProvider
OpenRouterProvider
```

Application code calls:

```text
classify_problem()
extract_problem()
generate_summary()
```

Never provider-specific APIs directly from business logic.

---

# 26. Pain Score

Normalize dimensions to 0–100.

Initial formula:

```text
pain_score =

0.30 × mention_frequency
+
0.25 × growth
+
0.20 × severity
+
0.15 × geographic_spread
+
0.10 × search_interest
```

This is a starting hypothesis.

All weights must live in:

```text
config/scoring.yaml
```

Do not hard-code them.

---

# 27. Commercial Score

Initial:

```text
commercial_score =

0.25 × payer_clarity
+
0.20 × recurrence
+
0.20 × economic_impact
+
0.15 × implementation_fit
+
0.10 × urgency
+
0.10 × commercial_evidence
```

`commercial_evidence` should eventually become one of the strongest factors.

---

# 28. Implementation Fit Score

This specifically prevents the system from recommending opportunities outside practical technical strengths.

Possible dimensions:

```text
software_solvable
integration_solvable
automation_solvable
requires_hardware
requires_large_capital
requires_regulatory_license
requires_marketplace_network_effect
requires_large_field_operations
```

For this project, increase scores for opportunities solvable through:

```text
web application
mobile application
API integration
workflow automation
AI automation
dashboard
reporting
ERP/POS integration
reservation
inventory
billing
customer-service workflow
```

Decrease scores where success primarily requires:

```text
heavy manufacturing
medical intervention
mass logistics infrastructure
government policy change
huge consumer network effects
large capital expenditure
```

---

# 29. Opportunity Score

Initial:

```text
opportunity_score =

0.45 × pain_score
+
0.55 × commercial_score
```

Commercial evidence deliberately weighs slightly more heavily.

Later:

```text
if commercial_validation == false:
    opportunity_score_cap = 79

if paid_pilot == true:
    commercial_evidence += major_bonus

if repeat_paid_customer == true:
    commercial_evidence += stronger_bonus
```

This stops AI-generated speculation from outranking actual paying customers.

---

# 30. Confidence Score

Keep confidence separate from opportunity score.

Example:

```text
confidence_score =
source_diversity
+
sample_size
+
data_recency
+
commercial_validation
+
classification_confidence
```

Dashboard should show:

```text
Opportunity Score: 84
Confidence: 42
```

This means:

> Looks attractive, but evidence is still weak.

That is much better than pretending the score is certain.

---

# 31. Evidence Hierarchy

Rank evidence roughly:

```text
WEAK

Single social post
↓
Multiple posts
↓
Search trend
↓
Official statistical support
↓
Multiple independent companies reporting problem
↓
Existing spending on workaround
↓
Requested proposal
↓
Paid pilot
↓
Second paying customer
↓
Recurring paying customers

STRONG
```

The system should visibly distinguish:

**internet evidence**

from:

**commercial evidence**

---

# 32. Opportunity Example

```text
Title:
SME POS → Accounting Reconciliation Automation

Pain evidence:
37 relevant complaints/discussions over 30 days

Trend:
+34% relative signal

Industries:
F&B
Retail

Buyer:
Business owner / Finance manager

Problem:
Sales data must be manually reconciled against accounting
and payment-provider data.

Frequency:
Daily

Economic impact:
Staff time + reconciliation mistakes

Existing workaround:
Excel

Implementation fit:
Very high

Potential product:
POS/accounting reconciliation connector

Revenue:
Setup + recurring subscription

Commercial evidence:
2 interviews
1 business already paying staff to perform task manually

Pain score:
76

Commercial score:
84

Opportunity score:
80

Confidence:
61

Next action:
Interview 3 additional retail/F&B operators.
```

---

# 33. Opportunity Dashboard

Main dashboard should answer:

> "What should I investigate or sell this week?"

Not:

> "How much data did we scrape?"

Top cards:

```text
Top Opportunity
Fastest Rising
Strongest Buyer Evidence
Newest Emerging Problem
Highest Paid Validation
```

Main table:

| Opportunity | Industry | Pain | Commercial | Confidence | Stage |
|---|---:|---:|---:|---:|---|
| POS reconciliation | F&B | 76 | 84 | 61 | Validating |
| Inventory mismatch | Retail | 82 | 77 | 71 | Paid pilot |
| WhatsApp booking | F&B | 70 | 80 | 68 | Validated |

Filters:

```text
industry
state
topic
buyer
date
commercial stage
source
confidence
```

---

# 34. Opportunity Detail Page

Show:

## Problem

Concise problem statement.

## Why It Matters

Economic/time/compliance impact.

## Evidence

Official signals.

Search signals.

Public-text examples.

Customer interviews.

Commercial evidence.

## Trend

7/30/90-day graph.

## Geography

State distribution.

## Buyer

Suggested economic buyer.

## Existing Solutions

Manual and commercial alternatives.

## Opportunity

Possible solution.

## Monetization

Possible charging model.

## Validation

Interviews.

Experiments.

Paid pilot status.

## Recommendation

```text
IGNORE
WATCH
INVESTIGATE
VALIDATE
SELL PILOT
PRODUCTIZE
```

---

# 35. Recommendation Engine

Use deterministic rules first.

Example:

```text
if commercial_score < 40:
    IGNORE

elif confidence < 30:
    WATCH

elif opportunity_score >= 60
     and interview_count == 0:
    INVESTIGATE

elif problem_confirmed_count >= threshold
     and paid_pilot_count == 0:
    VALIDATE

elif strong_buyer_signal:
    SELL_PILOT

elif paid_customer_count >= repeatability_threshold:
    PRODUCTIZE
```

LLM can explain the recommendation.

LLM should not decide the status itself.

---

# 36. API Design

Prefix:

```text
/api/v1
```

Endpoints:

```text
GET  /dashboard
GET  /topics
GET  /topics/{topic}
GET  /signals
GET  /opportunities
GET  /opportunities/{id}

POST /opportunities/{id}/interviews
POST /opportunities/{id}/evidence
POST /opportunities/{id}/experiments

GET  /reports
POST /reports/generate

GET  /sources
POST /sources/{id}/run

GET  /ingestion-runs
GET  /metrics
```

Use REST first.

No need for GraphQL.

---

# 37. Background Jobs

Example Laravel jobs:

```text
GenerateWeeklyReport
RecalculateOpportunityScores
RecalculateTopicMetrics
SendOpportunityAlerts
SyncCommercialEvidence
```

Python workers:

```text
collect_data_gov
collect_opendosm
collect_google_trends
normalize_documents
classify_documents
detect_duplicates
extract_problem_signals
aggregate_metrics
detect_anomalies
```

---

# 38. Scheduling

Conceptual schedule:

```text
OFFICIAL DATA
check according to dataset publication frequency

TREND DATA
daily

TEXT SOURCES
daily or source-appropriate frequency

NORMALIZATION
after ingestion

CLASSIFICATION
after normalization

METRICS
daily

OPPORTUNITY SCORING
daily

REPORT
weekly

COMMERCIAL REVIEW
weekly/manual
```

Do not download unchanged official datasets unnecessarily.

Store:

```text
last_modified
etag
dataset_version
last_successful_sync
```

where available.

---

# 39. Weekly Report

Title:

# Malaysia SME Opportunity Intelligence

Sections:

## Executive Summary

Top 3 findings.

## Rising Problems

What accelerated.

## Commercial Opportunities

Top ranked opportunities.

## New Signals

Previously unseen problems.

## Buyer Evidence

Recent interviews and commercial signals.

## Opportunities to Ignore

Problems with high attention but poor monetization.

## Suggested Experiments

What to validate.

## Build Recommendation

Maximum:

```text
0–2 opportunities
```

Do not recommend building 10 products simultaneously.

---

# 40. Alerting

Notify when:

```text
Opportunity score increases significantly

New topic enters Top 10

Major trend anomaly detected

Multiple independent sources mention same new issue

Commercial evidence added

Opportunity reaches SELL_PILOT

Opportunity reaches PRODUCTIZE
```

Possible channels:

```text
Email
Discord
Telegram
Slack
```

---

# 41. Data Quality

Every source receives:

```text
reliability_score
freshness_score
coverage_score
```

Every record maintains:

```text
provenance
source URL
collected_at
published_at
processing_version
```

Never allow AI-generated summaries to replace raw evidence.

Raw evidence is always traceable.

---

# 42. Deduplication

Use multiple strategies:

```text
external source ID
canonical URL
normalized content hash
near-duplicate similarity
```

Do not let syndicated copies artificially increase pain frequency.

Store duplicate relationships rather than deleting evidence blindly.

---

# 43. Multilingual Processing

Malaysia requires at minimum:

```text
English
Bahasa Malaysia
Chinese
```

Architecture must preserve:

```text
original_text
detected_language
normalized_summary_language
```

Do not translate everything before classification unless necessary.

Translation can alter meaning.

---

# 44. Cost Controls

Track AI cost per:

```text
source
document
topic
report
provider
model
```

Table:

```text
ai_usage
```

Fields:

```text
provider
model
operation
input_tokens
output_tokens
estimated_cost
document_id
created_at
```

Introduce:

```text
daily_ai_budget
monthly_ai_budget
```

Skip unnecessary LLM processing.

---

# 45. Caching

Cache:

```text
dashboard summary
topic metrics
opportunity rankings
report results
external API responses where permitted
```

Use Redis.

Do not cache immutable raw documents in Redis.

---

# 46. Observability

Collect:

```text
collector success
collector duration
records received
records rejected
classification failures
LLM failures
queue depth
API errors
data freshness
AI costs
```

Logs must be structured JSON.

Use a correlation ID across:

```text
ingestion_run
processing
classification
reporting
```

---

# 47. Testing Strategy

## Unit Tests

Test:

```text
scoring
normalization
topic mapping
recommendation rules
commercial gates
```

## Collector Tests

Use recorded fixtures.

Never make test suites dependent on live websites.

## Integration Tests

Test:

```text
collector → raw
raw → normalized
normalized → signals
signals → metrics
metrics → opportunity
```

## LLM Tests

Create a fixed evaluation dataset.

Example:

```text
tests/fixtures/problem_classification.jsonl
```

Include:

```text
obvious problem
no problem
spam
sarcasm
mixed language
duplicate
ambiguous buyer
multiple problems
```

Compare model output against expected labels.

---

# 48. Security

Use:

```text
RBAC
secure secrets
encrypted backups
HTTPS
rate limiting
API authentication
audit logs
dependency scanning
container scanning
```

Never commit credentials.

Use `.env.example`.

---

# 49. Privacy / Malaysian PDPA

Design for privacy by default.

Principles:

```text
collect minimum necessary data
avoid unnecessary personal identifiers
prefer aggregate statistics
separate raw and analytics data
define retention
support deletion
log access
document data source
document purpose
```

Malaysia currently has active guidance covering areas including Data Breach Notification, DPOs, privacy by design, DPIA, automated decision-making/profiling and cross-border transfers.

The project should therefore have:

```text
docs/privacy.md
docs/data-retention.md
docs/source-policy.md
docs/dpia.md
```

before handling significant personal-data volumes.

---

# 50. Data Retention

Suggested architecture:

```text
Raw public text:
configurable retention

Aggregated metrics:
long-term

Commercial interview notes:
long-term only where justified

Direct personal identifiers:
avoid unless necessary
```

Retention must be configurable by source.

---

# 51. Admin Features

V1 admin should support:

```text
manage sources
enable/disable collector
view ingestion errors
manage taxonomy
manage keywords
change scoring weights
merge topics
split topics
review classifications
promote signal → opportunity
record customer interview
record commercial evidence
record experiment
override opportunity status
generate report
```

Human review is essential.

---

# 52. Human-in-the-Loop Design

AI suggests.

Human approves important commercial decisions.

For example:

```text
AI:
"This may be a strong inventory-management opportunity."

System:
Suggested

Human:
Promote to Investigating
```

Never automatically create development projects from LLM recommendations.

---

# 53. MVP Scope

V1 SHOULD include:

```text
PostgreSQL schema
source registry
data.gov/OpenDOSM connector
Google Trends connector
generic document ingestion
normalization
basic multilingual support
taxonomy
rule classification
LLM extraction abstraction
pain scoring
commercial scoring
opportunity ranking
Laravel API
Nuxt dashboard
commercial-validation CRM
weekly report
Docker development environment
tests
```

---

# 54. Explicit Non-Goals for V1

Do NOT build:

```text
mobile application
native AI model
vector database unless justified
complex RAG system
Kafka
Kubernetes
microservice explosion
public marketplace
consumer social network
billing system
multi-tenant enterprise platform
automated sales outreach
large-scale unrestricted scraping
```

V1 exists to prove:

> Can this system consistently discover commercially useful SME problems?

---

# 55. Development Milestones

## Milestone 0 — Foundation

Deliver:

```text
monorepo
Docker Compose
Laravel
Nuxt
Python worker
PostgreSQL
Redis
CI
environment configuration
```

Acceptance:

```text
docker compose up

starts all required development services.
```

---

## Milestone 1 — Data Foundation

Deliver:

```text
source registry
ingestion_runs
raw_documents
collector abstraction
OpenDOSM/data.gov connector
```

Acceptance:

A configured official dataset can be ingested repeatedly without duplication.

---

## Milestone 2 — Analytics Foundation

Deliver:

```text
normalization
topic taxonomy
problem signals
daily aggregation
```

Acceptance:

Raw records can become normalized Problem Signals.

---

## Milestone 3 — Trends

Deliver:

```text
Google Trends adapter
keywords
keyword groups
trend metrics
trend charts
```

Acceptance:

Historical daily signals are stored and visible.

---

## Milestone 4 — Intelligence Layer

Deliver:

```text
structured LLM classification
pain score
commercial score
confidence score
opportunity score
```

Acceptance:

Each opportunity is explainable through stored evidence.

---

## Milestone 5 — Dashboard

Deliver:

```text
overview
topic page
opportunity list
opportunity detail
source health
```

Acceptance:

Opening the dashboard answers:

> What are the strongest opportunities right now and why?

---

## Milestone 6 — Commercial Validation

Deliver:

```text
customer interviews
commercial evidence
experiments
commercial stages
```

Acceptance:

A problem can move from internet signal to paid-pilot tracking.

---

## Milestone 7 — Reporting

Deliver:

```text
weekly report
email/Discord notification
report history
```

Acceptance:

Report generation is automatic and reproducible from stored data.

---

## Milestone 8 — Real Market Validation

The developer manually tests top opportunities against actual businesses.

Store every result in the system.

The objective is not to prove that the algorithm is intelligent.

The objective is:

```text
Internet signal
    ↓
Business conversation
    ↓
Confirmed expensive problem
    ↓
Paid solution
```

---

# 56. Success Metrics

Technical metrics:

```text
collector reliability
data freshness
classification accuracy
duplicate rate
processing cost
report generation reliability
```

Business metrics:

```text
opportunities investigated
customer interviews completed
problem confirmation rate
proposal rate
paid pilot rate
repeat buyer rate
revenue generated from discovered opportunities
```

The ultimate KPI is:

# Opportunity-Generated Revenue

Store:

```text
opportunity_id
revenue_type
amount
currency
customer_type
date
```

This allows answering later:

> Did the intelligence system actually help create revenue?

---

# 57. Most Important Feedback Loop

Every commercial result must feed back into scoring.

Example:

```text
Opportunity A
score = 92
10 interviews
0 businesses willing to pay

Result:
commercial assumptions were wrong.
```

Use this to recalibrate the scoring model.

Meanwhile:

```text
Opportunity B
score = 68
3 interviews
2 paid pilots

Result:
system underestimated opportunity.
```

Adjust scoring weights using real commercial outcomes.

Eventually the scoring system becomes personalized to what this developer can actually sell and build.

That becomes much more valuable than generic startup advice.

---

# 58. Opportunity Outcome Dataset

Create:

```text
opportunity_outcomes
```

Fields:

```text
opportunity_id
initial_score
buyer_interviews
confirmed_buyers
proposals_sent
paid_pilots
customers
revenue
outcome
reason
```

Possible outcomes:

```text
successful
promising
no_budget
low_urgency
already_solved
poor_fit
too_complex
regulatory
false_signal
```

This becomes training data for future scoring improvements.

---

# 59. Future Machine Learning

Do NOT start here.

Once sufficient outcome data exists, train a model using:

```text
pain features
commercial features
source diversity
trend features
industry
buyer
previous outcomes
```

Target:

```text
probability_of_paid_pilot
```

This is much better than asking an LLM:

> "Will this make money?"

Because it learns from actual outcomes.

---

# 60. Future Expansion

After SME operational friction proves useful, consider:

```text
consumer problems
property
automotive services
healthcare operations
education services
logistics
professional services
government-service navigation
cost-of-living intelligence
```

Each becomes a vertical module.

Do not expand until the core commercial loop works.

---

# 61. Coding Standards

Codex and Claude must follow:

```text
SOLID where useful
simple architecture over abstraction
typed boundaries
idempotent collectors
database migrations
service-layer business logic
DTO/schema validation
repository interfaces only where beneficial
tests for scoring/business rules
structured logs
explicit error handling
no silent failures
```

Avoid:

```text
god classes
magic strings
duplicated business rules
provider-specific logic everywhere
unbounded LLM outputs
large controllers
business logic inside Vue components
business logic inside n8n
```

---

# 62. Database Rules

Use:

```text
UUID/ULID where appropriate
foreign keys
indexes
unique constraints
timestamps
JSONB only for genuinely variable metadata
```

Do not put everything into JSONB.

Frequently queried dimensions belong in normal columns.

Important indexes:

```text
published_at
collected_at
topic_id
industry_id
state
source_id
signal_date
opportunity_score
content_hash
status
```

---

# 63. Git Workflow

Suggested:

```text
main
develop
feat/*
fix/*
refactor/*
```

Each agent task should:

```text
1. inspect existing code
2. read PROJECT_SPEC.md
3. read AGENTS.md
4. propose implementation scope internally
5. modify smallest necessary surface
6. write/update tests
7. run tests
8. run lint/static analysis
9. document schema/config changes
10. summarize changes
```

Never allow agents to rewrite unrelated modules.

---

# 64. AGENTS.md Rules

Create `AGENTS.md` containing approximately:

```text
This repository implements Malaysia SME Pain Radar.

PROJECT_SPEC.md is the primary product specification.

Priorities:

1. Commercial usefulness
2. Correct data provenance
3. Maintainability
4. Reliability
5. Cost efficiency
6. Performance

Do not introduce new infrastructure without clear justification.

Do not replace Laravel/Nuxt/Python/PostgreSQL/Redis without explicit approval.

All collectors must be:

- idempotent
- retryable
- observable
- configurable

All AI output must:

- use structured schema
- include confidence where appropriate
- remain traceable to evidence
- never overwrite source evidence

Never interpret AI output as verified fact.

Business scoring logic must be deterministic and tested.

Commercial validation evidence always outranks LLM speculation.

Before completing a task:

- run relevant tests
- run lint/static analysis
- update documentation
- report unresolved risks
```

---

# 65. CLAUDE.md

Claude should receive additional repository instructions:

```text
Read PROJECT_SPEC.md and AGENTS.md before changing code.

When requirements conflict:
PROJECT_SPEC.md defines product behavior.

Do not implement future phases unless the current task requires them.

Prefer boring, production-proven solutions.

Do not prematurely introduce:
Kafka
Kubernetes
microservices
vector databases
event sourcing

When implementing data collectors:
preserve raw source provenance.

When implementing LLM functionality:
create provider abstraction and structured responses.

When implementing scoring:
keep weights configurable and write deterministic tests.

When making architectural changes:
document rationale in docs/architecture.md.
```

---

# 66. Recommended First Coding Task

Give Codex/Claude this first:

```text
Read PROJECT_SPEC.md completely.

Implement Milestone 0 only.

Create the initial monorepo structure for Malaysia SME Pain Radar using:

- Laravel API
- Nuxt frontend
- Python intelligence package
- PostgreSQL
- Redis
- Docker Compose

Requirements:

1. Do not implement business features yet.
2. Create health endpoints for all services.
3. Configure environment variables through .env.example.
4. Add basic CI.
5. Add README development instructions.
6. Add AGENTS.md and CLAUDE.md based on PROJECT_SPEC.md.
7. Add architecture documentation.
8. Ensure docker compose can start the development stack.
9. Add health checks.
10. Keep the implementation minimal and production-oriented.

Before finishing:
- run available tests
- validate container configuration
- report anything that cannot be verified
- do not continue to Milestone 1.
```

---

# 67. Second Coding Task

After Foundation works:

```text
Implement Milestone 1 from PROJECT_SPEC.md.

Build the data ingestion foundation.

Requirements:

- sources table
- ingestion_runs table
- raw_documents table
- source configuration
- Python collector interface
- first data.gov.my/OpenDOSM collector
- idempotent imports
- retry handling
- content hashing
- provenance
- integration tests

Do not implement LLM processing yet.

Demonstrate ingestion using one official Malaysian dataset.

Document how to add another dataset without changing core collector logic.
```

---

# 68. Third Coding Task

Then:

```text
Implement Milestone 2.

Add:

- normalization pipeline
- normalized_documents
- topic taxonomy
- topics
- document_topics
- problem_signals
- topic_daily_metrics

Use deterministic classification rules first.

Taxonomy must be YAML/config-driven.

Add fixtures representing:
English
Bahasa Malaysia
Chinese
mixed language

Write tests for classification and normalization.

Do not add LLM classification yet.
```

---

# 69. Fourth Coding Task

Then:

```text
Implement Milestone 3.

Add Google Trends intelligence.

Preferred acquisition order:

1. Official Google Trends API when credentials/access are configured.
2. Google Trends BigQuery public dataset for available discovery signals.
3. Adapter interface allowing future providers.

Do not create brittle scraping as the core implementation.

Implement:

keywords
keyword groups
trend metrics
growth calculations
rolling averages
baseline
z-score
trend dashboard

Ensure Trends data is treated as relative interest rather than absolute search volume.
```

---

# 70. Fifth Coding Task

Then:

```text
Implement Milestone 4.

Create the LLM Intelligence layer.

Requirements:

- provider interface
- structured JSON schema
- Pydantic validation
- topic classification
- problem extraction
- buyer extraction
- severity
- urgency
- economic impact
- confidence

Add provider adapters incrementally.

Do not let provider-specific code leak into domain logic.

Store:
model
provider
prompt version
processing version
cost metadata

Add a fixture-based LLM evaluation suite.
```

---

# 71. Sixth Coding Task

Then:

```text
Implement the opportunity engine.

Implement:

Pain Score
Commercial Score
Confidence Score
Opportunity Score
Recommendation state machine

All weights must come from config/scoring.yaml.

Write exhaustive tests.

Commercial validation must influence scores.

Paid evidence must outrank inferred social evidence.

Every displayed score must be explainable through component values.
```

---

# 72. Seventh Coding Task

Then:

```text
Implement Nuxt opportunity dashboard.

Primary UX question:

"What can I potentially sell or validate now?"

Pages:

Dashboard
Topics
Opportunity ranking
Opportunity detail
Sources
Ingestion health
Commercial validation
Reports

Avoid vanity analytics.

Every opportunity must expose:
score
confidence
trend
buyer
evidence
commercial stage
recommended next action
```

---

# 73. Final Product Principle

The system is successful only if it creates this loop:

```text
DATA
↓
SIGNAL
↓
PROBLEM
↓
BUYER
↓
VALIDATION
↓
PAID PILOT
↓
REPEATABLE SOLUTION
↓
SAAS / SERVICE
↓
REVENUE
↓
FEEDBACK INTO SCORING
```

Do not optimize for:

```text
number of scraped pages
number of AI summaries
number of dashboards
number of datasets
```

Optimize for:

# Validated commercial problems found per month

and eventually:

# Revenue generated from discovered opportunities.

---

# 74. North Star

The long-term asset is not the scraper.

It is not the dashboard.

It is not the LLM.

The long-term asset is the accumulated dataset connecting:

```text
public signals
+
official economic data
+
problem categories
+
buyer types
+
customer interviews
+
commercial experiments
+
paid outcomes
```

Once enough outcomes exist, the platform can answer a far more valuable question:

> "Given what is happening in Malaysia right now, which problem has the highest probability of becoming a business that I can realistically build and sell?"

That is the real product.