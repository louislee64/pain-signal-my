# Outcomes, revenue and calibration

Milestone 8. PROJECT_SPEC.md §56 (success metrics), §57 (the feedback loop),
§58 (the outcome dataset).

Milestone 8's actual work is **yours**: taking the top-ranked opportunities to
real businesses and finding out. §55 says so plainly —

> The developer manually tests top opportunities against actual businesses.
> Store every result in the system.
> The objective is not to prove that the algorithm is intelligent.

So what got built here is only the part that makes storing the result cheap, and
the part that turns stored results back into a judgement about the model.

---

## §58's outcome dataset

One row per opportunity, written when you conclude it.

The column that matters most is `initial_score`, and it is the easiest one to get
wrong. It is **snapshotted at conclusion, never joined later** — and the API
refuses a caller-supplied value for the same reason. The score moves as evidence
accumulates, so by the time you record an outcome the score has already been
dragged toward the answer by the interviews and evidence you logged along the
way. Comparing a live score against the outcome it helped produce measures
nothing.

The same applies to the counted fields (`buyer_interviews`, `paid_pilots`, …):
frozen, because they are what was true when the call was made. They default from
recorded evidence rather than being re-typed, since re-typing numbers the system
already knows is how they end up wrong.

§58's nine outcomes, grouped by what each one indicts:

| Outcome | Implicates |
|---|---|
| `successful`, `promising` | — (the model was right) |
| `no_budget`, `low_urgency`, `already_solved`, `poor_fit`, `too_complex`, `regulatory` | `commercial_score` |
| `false_signal` | `pain_score` |

That grouping is what lets §57 answer *which* assumption was wrong rather than
only *that* one was.

`reason` is required by the API even though the column is nullable. Nine
categories cannot hold what actually happened, and a year later the reason is the
part worth reading.

```bash
curl -X POST $API/opportunities/4/outcome -H 'Content-Type: application/json' -d '{
  "outcome": "no_budget",
  "reason": "Six owners all agreed the problem is real. None had a budget line for it.",
  "concluded_at": "2026-08-09"
}'
```

---

## §56's ultimate KPI

`opportunity_revenue` is separate from `commercial_evidence` even though both
carry a value, and the separation is the point:

- **Evidence** records *that something happened* — a proposal signed, a deposit
  arrived — as a signal about how real an opportunity is.
- **Revenue** records *money received*, as an accounting fact.

A signed proposal worth RM6,000 is one piece of evidence and **zero revenue**
until it is paid. A RM4,500 pilot invoiced monthly is one piece of evidence and
**many** revenue rows. Summing `commercial_evidence.value` would count proposals
that never converted and count a running pilot once — the KPI would be
unanswerable.

Refunds are negative rows rather than deletions. The original payment did happen,
and erasing it would lose that.

```bash
curl -X POST $API/opportunities/2/revenue -H 'Content-Type: application/json' -d '{
  "revenue_type": "paid_pilot", "amount": 4500,
  "company_ref": "retailer-c", "customer_type": "multi-outlet retail",
  "received_at": "2026-08-05"
}'
```

`company_ref` stays pseudonymous, same contract as everywhere else (§21), so
"revenue from how many distinct businesses" is answerable without naming any.

Revenue recorded after an outcome was concluded updates that outcome — otherwise
the dataset would permanently understate what the opportunity earned.

---

## §57's feedback loop

```bash
docker compose exec api php artisan calibration:report
```

Two things this deliberately does **not** do, and they matter more than anything
it does.

### It never edits `config/scoring.yaml`

§52's rule applies with more force here than anywhere else in the system.
Auto-tuning weights would let a handful of outcomes silently rewrite the model
that ranks everything, and you would have no idea why last month's rankings no
longer reproduce. The report says what looks wrong and by how much; you make the
edit. The API response says so too, because an API consumer is exactly who would
otherwise write the auto-tuning loop this is designed to prevent.

### It refuses to conclude from too little data

Nothing here is statistics — with six outcomes there is no statistics to do. So
rather than computing a correlation coefficient nobody should trust, every
finding carries the count behind it, and below **8 outcomes** the report describes
rather than concludes. Below **3 examples** a pattern gets no verdict at all: two
examples of anything is an anecdote.

This is §30's separation of score from confidence, turned on the system's opinion
of itself.

### What it reports

**Accuracy, as four counts rather than one percentage.** A percentage hides the
asymmetry, and the asymmetry is the point: scoring something high that flopped
costs weeks of wasted effort; scoring something low that would have worked costs
an opportunity you never knew you missed. Different costs, so they never average.

**§57's Opportunity A** — high score, real effort, nothing came of it. The test
requires `buyer_interviews >= 2`, because a negative outcome with no customer
contact reflects effort rather than the model, and counting it would blame the
model for work never done.

**§57's Opportunity B** — low score, money arrived. Keyed on paid pilots and
revenue rather than on the `successful` label: the label is a judgement someone
typed, a payment is a fact, and being strict here costs nothing.

**Which dimension looks mis-weighted.** §57 asks for weight adjustment, which
needs more than "the score was too high". For each dimension, the report compares
its mean normalized value among overestimated opportunities against the mean among
underestimated ones. A dimension scoring high on things that flopped and low on
things that worked is doing the opposite of its job — the strongest signal this
data can carry, and still only a hint.

### It works

Recorded against the demo data, both of §57's examples:

```
Against the §35 INVESTIGATE threshold of 60:
             | Worked | Failed
 Scored high |   0    |   0
 Scored low  |   1    |   1
  wasted effort: 0   missed: 1

Overestimated (§57 Opportunity A):
  Software Integration — scored 56, 6 interviews, ended no budget (implicates commercial_score)

Underestimated (§57 Opportunity B):
  Inventory & Stock — scored 54, 2 paid pilot(s), MYR 8,300.00 revenue

Opportunity-Generated Revenue: MYR 8,300.00 across 1 opportunity(ies)

• Record at least 8 outcomes before changing anything in config/scoring.yaml.
  At 2, a single unusual result moves every average enough to mislead.
```

Note what it did *not* say. It found both patterns and still refused to draw a
conclusion, because two outcomes is two outcomes.

---

## §56's success metrics

```bash
curl $API/metrics
```

Split into technical and business, and the split is worth keeping visible rather
than flattening into one wall of numbers. Technical metrics say whether the
machine works; business metrics say whether the machine is *worth* working. **A
green technical panel above an empty business panel is the most important state
this system can be in** — everything runs and nothing has been sold.

Every rate carries its numerator and denominator. "40% confirmation from two
interviews" and "40% from two hundred" are different facts, and a bare percentage
makes them identical. A zero denominator gives `null`, not `0`: "no interviews
yet" is not "interviews happened and none confirmed".

One honest substitution: §56 asks for **classification accuracy**, which cannot
be measured without labelled ground truth. The only labelled data in the project
is the §70 evaluation set, which covers LLM extraction rather than rule-based
classification. So the metric reports *coverage* and says in the payload that it
is coverage — a number that sounds like accuracy and is not would be worse than
an absent one.

---

## What is deliberately not here

**§59's machine learning.** The spec opens that section with "Do NOT start here",
and it is right: a model trained on two outcomes would be superstition with a
confusion matrix. `opportunity_outcomes` is shaped as the training set for when
enough of them exist.

**Auto-tuning.** Covered above, but worth repeating because it is the obvious
next thing to build and the wrong one.

---

## Endpoints

```
POST /api/v1/opportunities/{id}/outcome    §58 — conclude one
POST /api/v1/opportunities/{id}/revenue    §56 — record money received
GET  /api/v1/outcomes                      the dataset as recorded
GET  /api/v1/calibration                   §57's report
GET  /api/v1/metrics                       §56's success metrics
```

The dashboard's `/outcomes` page renders all of it, with the sample-size banner
first — a reader who edits weights on the strength of four data points has been
misled by the page, so the count leads and the findings follow.
