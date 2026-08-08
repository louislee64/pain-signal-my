# LLM providers, cost and evaluation

Milestone 4 is the first part of this system that spends money per document.
Everything here follows from that: extraction is off by default, every call is
recorded, and the budget is a limit rather than a report.

PROJECT_SPEC.md §24 (what the LLM is asked), §25 (provider independence), §44
(cost tracking) and §70 (evaluation).

---

## What the LLM is and is not asked

§24 draws a hard line, and the code enforces it in the schema itself.

**Asked:** read one document, report what operational problem it describes —
topic, affected role, who would plausibly pay, how often it happens, how severe
it is, and how confident the model is about all of that.

**Never asked:** "Is this a good business opportunity?" That judgement is made
by the deterministic scoring engine (`docs/scoring-model.md`), where every
number is explainable, testable, and reproducible. A model cannot be
cross-examined about why a score moved; a weight in `config/scoring.yaml` can.

`ProblemExtraction` forbids extra fields, so a model that volunteers
`market_size_usd` produces a validation error rather than an opinion the system
would have to decide whether to trust. There is a test asserting the schema
never grows an opportunity-judgement field.

---

## Providers

| Name | Cost | Needs | Use for |
|---|---|---|---|
| `fixture` | free | recorded answers | CI, local development, the eval harness |
| `anthropic` | per token | `ANTHROPIC_API_KEY` + `pip install -e '.[anthropic]'` | real extraction, recording fixtures |

Both implement `LLMProvider` (`src/intelligence/llm/base.py`). Adding a third —
OpenAI, Gemini, a local model — is a subclass plus one line in
`llm/registry.py`; nothing in the pipeline, the CLI, or the eval harness knows
which provider it is talking to.

The prompt lives in `base.py`, not in the adapters. A prompt is part of the
extraction contract, not a vendor detail: two adapters whose prompts drifted
apart would make evaluation results incomparable.

### Anthropic adapter notes

- Uses `client.messages.parse()` with `output_format=ProblemExtraction`, so the
  response is schema-validated at the API boundary rather than parsed by hand.
- `stop_reason == "refusal"` is checked explicitly before reading the parsed
  output — a safety decline is a content outcome, not an exception, and
  `parsed_output` is absent when it happens.
- Default model is `claude-opus-5` with `effort: low`. It is deliberately not
  downgraded to a cheaper tier in code: picking a model is a cost/quality
  decision that belongs to the operator, and `config/llm.yaml` is where they
  make it. The budget guard is the cost control, not a silently weaker model.
- Adaptive thinking is left on (the model's default). Extraction is short and
  bounded, so `effort` is the lever that matters.

---

## Turning it on

Extraction is disabled until `config/llm.yaml` says otherwise:

```yaml
enabled: true
provider: anthropic
provider_config:
  model: claude-opus-5
  effort: low
budget:
  daily_usd: 2.00
  monthly_usd: 30.00
max_documents_per_run: 50
```

Then set the key in `apps/intelligence/.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Install the optional extra and rebuild:

```bash
docker compose exec intelligence pip install -e '.[anthropic]'
```

Check what a run *would* do before letting it spend anything:

```bash
docker compose exec intelligence python -m intelligence.cli llm extract --dry-run
```

---

## The guards, and why each exists

| Guard | Behaviour | Why |
|---|---|---|
| `enabled: false` | refuses to build a paid provider | an accidental pipeline run should cost nothing |
| budget check | runs **before** each call, aborts the run | a budget enforced after the spend is a report, not a limit |
| `max_documents_per_run` | caps the batch regardless of budget | bounds blast radius when a bad backfill queues thousands of documents |
| `min_text_length` | skips short text without calling | paying to be told "no problem here" about a 12-word post is pure waste |
| ledger-based dedup | a document paid for is never re-sent | see below |
| `--dry-run` | reports the queue, calls nothing | lets you see the bill before committing to it |
| unknown source | stops the run | falling back to "all sources" on a typo is the expensive reading of an obvious mistake |

### Why dedup keys on the ledger, not on results

The free rule-based classifier in `process.py` re-scans documents that produced
no match on every run — cheap and harmless. The LLM path cannot do that: most
documents legitimately contain no problem, and keying on produced-signals would
pay for the same `problem_present: false` forever.

So "already processed" means "there is a successful `ai_usage` row for this
document under this prompt version". Failed calls are deliberately excluded: a
transient API error should be retried, and its ledger row exists to record the
spend, not to blacklist the document.

Bumping `PROMPT_VERSION` re-opens every document for extraction under the new
prompt. That is intended — a new prompt is a new question — but it means a
prompt change is also a spend decision.

---

## Cost tracking (§44)

Every call writes an `ai_usage` row before its result is used, successful or
not. A failed call still consumed tokens; omitting failures would understate
real spend exactly when something is going wrong.

```bash
docker compose exec intelligence python -m intelligence.cli llm usage
```

```json
{"spent_today_usd": 0.184, "spent_this_month_usd": 2.41,
 "daily_budget_usd": 2.0, "monthly_budget_usd": 30.0,
 "enabled": true, "provider": "anthropic"}
```

`estimated_cost` is stored at 6 decimal places. One extraction on Opus 5
(~2k in / ~200 out) costs about $0.015; at 2dp a thousand of them would round to
either nothing or double.

Rates live in `llm/pricing.py`. They are published prices, not invoices — treat
that table as something to review, because when a rate drifts from reality the
budget guard drifts with it. An unpriced model estimates as $0.00 rather than
raising (a missing price must not stop an authorised extraction), and
`is_priced()` exists so that gap can be surfaced rather than silently treated as
free.

---

## Evaluation (§70)

`apps/intelligence/evaluation/cases.yaml` holds twelve documents with
known-correct answers. Without it, "the extraction got better" is an opinion.

The cases cover the failure modes §70 names plus the ones this domain makes
likely: an obvious problem, a statistic, vendor marketing, spam, sarcasm,
Malay/English code-switching, Chinese, a buyer who is not the sufferer, a
genuinely ambiguous buyer, a document with two problems, a vague complaint, and
a prompt injection.

Assertions are deliberately partial. Numeric fields are ranges and unlisted
fields are unchecked, because over-specifying turns a working extraction into a
failure over a judgement call — is "very slow" severity 70 or 75?

```bash
# free, deterministic, what CI runs
docker compose exec intelligence python -m intelligence.cli llm evaluate --provider fixture

# measures the model; costs about a cent
docker compose exec intelligence python -m intelligence.cli llm evaluate --provider anthropic
```

The report always names which cases failed, because that matters more than how
many: 10/12 with the two known-hard cases failing is a different situation from
10/12 with the injection case failing.

### Recordings

`evaluation/recordings/` ships empty. Recordings are real model responses, and
there is no honest way to produce one without calling a model — a hand-written
file would let the suite pass against answers nobody's model ever gave.

```bash
docker compose exec intelligence python -m intelligence.cli llm record --provider anthropic
```

The fixture provider keys recordings by the SHA-256 of the case text, so editing
a case stops matching rather than silently replaying the answer to the old text.
It also refuses to replay recordings made under a different `PROMPT_VERSION`.

A fixture run exercises schema validation, taxonomy mapping and the scorer. It
proves nothing about model quality — the answers are fixed. That distinction is
the whole reason both modes exist.

---

## Prompt injection

Source documents are untrusted text that may address the model directly. Three
things stand between that and the database:

1. The system prompt states the document is data to analyse, never instructions
   to follow, and the document is delimited in `<document>` tags.
2. `ProblemExtraction` forbids extra fields and bounds every score, so a
   successful injection cannot inflate a topic beyond what the schema allows.
3. `prompt_injection` is an evaluation case with an expected answer of
   `problem_present: false`. A regression here is a security failure, not a
   quality one, and the eval report names it.
