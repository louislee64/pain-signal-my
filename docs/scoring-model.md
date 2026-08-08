# The scoring model

How a pile of documents becomes a ranked list of opportunities, and — more
importantly — how you find out *why* any given number is what it is.

PROJECT_SPEC.md §26 (pain score), §27 (commercial score), §29 (opportunity
score), §30 (confidence score), §31 (evidence hierarchy), §35 (recommendations).

---

## The one rule

**Every weight lives in `config/scoring.yaml`. No number in
`src/intelligence/scoring/` is hard-coded.**

The config loader raises rather than defaulting when a key is missing. A silent
default would be a hard-coded weight wearing a disguise, and the failure would
be invisible: scores would keep coming out, just not the ones anyone agreed to.

Every weight in that file is a *starting hypothesis*. §57 is the point of the
whole system — real commercial outcomes feed back and these numbers get
recalibrated against what actually sold. The tests in `tests/scoring/` pin the
arithmetic, not the values, so weights can move without breaking them.

---

## Four scores, not one

| Score | Question | §  |
|---|---|---|
| Pain | How significant does this problem look? | §26 |
| Commercial | How attractive is it as a business? | §27 |
| Opportunity | Blend of the two, with a validation ceiling | §29 |
| Confidence | How much should you believe any of the above? | §30 |

Confidence is deliberately **separate** from opportunity, not folded into it. A
high opportunity score with low confidence means "looks attractive, evidence is
still thin" — which is far more useful than a single number pretending to
certainty. Collapsing them would destroy exactly the information a person needs
to decide whether to go and talk to customers.

### Pain (§26)

`mention_frequency 0.30 · growth 0.25 · severity 0.20 · geographic_spread 0.15 ·
search_interest 0.10`

### Commercial (§27)

`payer_clarity 0.25 · recurrence 0.20 · economic_impact 0.20 ·
implementation_fit 0.15 · urgency 0.10 · commercial_evidence 0.10`

### Opportunity (§29)

`0.45 × pain + 0.55 × commercial`, then:

- `+15` if a paid pilot exists
- `+30` if there are two or more paying customers
- **capped at 79** unless the topic is commercially validated

The cap is §29's stated purpose: *"This stops AI-generated speculation from
outranking actual paying customers."* Until money has changed hands or a human
has confirmed the problem more than once, an opportunity cannot present as
top-tier however good the inferred signals look.

The bonuses need explaining, because they are a reading of the spec rather than
a transcription of it. §29's "Later:" block says `paid_pilot =>
commercial_evidence += major_bonus`. Applied literally — as a bump to the
`commercial_evidence` dimension — it does nothing useful: that dimension carries
§27's documented 0.10 weight, so even a perfect 100 moves the final score by at
most 5.5 points. A maxed-out speculative topic would still beat a modest one
with two paying customers, which is the exact outcome §29 exists to prevent.
Raising the §27 weight instead would contradict a number the spec states
explicitly. So the bonus is applied to the blended score, as the separate
mechanism §29 describes it as. This was caught by a test that put speculation at
79 and real revenue at 51.

### Confidence (§30)

`source_diversity 0.25 · sample_size 0.25 · data_recency 0.20 ·
commercial_validation 0.15 · classification_confidence 0.15`

§30 writes this as a bare sum of five terms, which has no bounded range. It is
implemented as a weighted mean of five 0–100 components — same five inputs, same
relative meaning, on the 0–100 scale the dashboard shows next to opportunity
score.

---

## Explainability is the deliverable

Every opportunity row stores `score_components` (JSONB) recording, for every
dimension: its raw input, its normalized 0–100 value, its weight, and its
contribution to the total. Plus any note the engine attached — "capped at 79:
not commercially validated" is stored, not inferred.

```
GET /api/opportunities/{id}
```

returns the full breakdown. A score you cannot interrogate is a score nobody
will act on, and §26's normalization means the raw inputs (counts, percentages,
dates) are otherwise unrecoverable from the final number.

`scoring_config_version` is stored alongside, so a score computed under one set
of weights is never silently compared against one computed under another.

---

## Normalization

Raw inputs are counts, percentages and dates. Each `*_target` in
`config/scoring.yaml` is the value at which a dimension saturates at 100;
anything beyond is clipped rather than allowed to dominate.

These targets are the most assumption-laden numbers in the project. A few worth
knowing:

- `geographic_spread_target: 5` — Malaysia has 16 states/territories; appearing
  in a third of them already signals a national rather than local problem.
- `growth_percent_target: 100.0` — decline maps to 0, not to a negative
  contribution. A shrinking problem is uninteresting, not anti-interesting.
- `source_diversity_target: 3` — §31's evidence hierarchy: multiple independent
  sources outrank any single one.

`distinct_sources` counts **sources**, not documents. Fifty posts from one forum
is one source. This is the single most consequential detail in
`measurements.py`, and getting it wrong would make any noisy source look like
consensus.

---

## Recommendations (§35)

A state machine, not a threshold on the score:

`PRODUCTIZE → SELL_PILOT → IGNORE → WATCH → VALIDATE → INVESTIGATE → WATCH`

Evaluated most-advanced-state-first, so a topic with paying customers is never
described as something to "investigate". `IGNORE` sits deliberately high in the
order: a topic that has been actively ruled out should not be re-recommended
because its mention count crept up.

---

## Running it

```bash
docker compose exec intelligence python -m intelligence.cli score
```

Rescoring **never** overwrites `status`, `title`, or human-authored narrative
fields (§52). Those are a person's judgement; the engine owns the numbers and
nothing else. This matters more than it sounds — an engine that resets a
human's "we decided to ignore this" on every cron run would train people to stop
recording decisions in the system.
