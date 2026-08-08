# Commercial validation

Milestone 6. PROJECT_SPEC.md §3 (the funnel), §7 (the gates), §21 (the CRM
tables), §52 (human-in-the-loop).

The acceptance criterion is that **a problem can move from internet signal to
paid-pilot tracking**. Everything here exists to make that move possible while
keeping it honest — §3 is blunt that "an opportunity is not considered
commercially validated merely because AI says it is promising."

This is also the milestone that finally lets §29's 79-point cap lift. Until a row
lands in `commercial_evidence`, no amount of inferred signal can present an
opportunity as a certainty.

---

## The funnel (§3)

```
observed → investigating → buyer_identified → problem_validated
  → commercially_validated → paid_pilot → repeatable_solution
  → product_candidate → saas_or_managed_service
```

Two columns, not one:

| Column | Written by | Meaning |
|---|---|---|
| `status` | **only a human**, via `PATCH /stage` | where this opportunity actually is |
| `suggested_status` | the engine, on every evidence write | the furthest stage the recorded evidence supports |

§52 is unambiguous: *"AI suggests. Human approves."* A pipeline that promoted an
opportunity to `paid_pilot` because the gates happened to pass would be making a
commercial decision. Collapsing the two columns into one would force a choice
between an invisible suggestion and an automatic promotion, and both are wrong —
so the gap between them is rendered as information to act on.

`CommercialStage::ORDER` is the single source of truth for the progression. The
array order *is* the funnel: `rank()` is how "promotion or demotion" gets
answered, so reordering that list changes behaviour and is not a cosmetic edit.

---

## The gates (§7)

| Stage | Requirement |
|---|---|
| `buyer_identified` | Gate 1 — a buyer hypothesis recorded (`target_buyer`) |
| `problem_validated` | Gate 2 — at least one interview confirming the problem |
| `commercially_validated` | Gate 3 — **two independent businesses** confirming **and** one strong commercial signal |
| `paid_pilot` | Gate 4 — recorded evidence that a customer paid |
| `repeatable_solution` | Gate 5 — a **second paying business** |

`observed` and `investigating` are ungated. `investigating` means someone decided
to look, which needs no evidence; gating a decision to pay attention would just
teach people to skip recording it.

Everything past `repeatable_solution` is ungated too, and the engine never
suggests it. §7 Gate 5 says "only now should major SaaS investment begin" — beyond
that point the funnel stops being about evidence and starts being about build
decisions, which are not the engine's business.

### Advancing checks every gate on the way

`gateCheckPath()` checks each stage between where you are and where you are
going, not just the destination, and reports the **first** unmet gate.

This was found by walking the funnel end to end: checking only the destination
let `problem_validated` be reached from `investigating` with no buyer hypothesis
recorded. That state is one the suggestion logic can never produce — it stops at
the first failing gate — so allowing it left the API and the engine disagreeing
about what the funnel contains.

### Demotions are never gated

Deciding an opportunity was over-promoted is exactly the correction the funnel
must permit. Making it hard would leave stale optimistic stages in place, which
is worse than the demotion.

### Overrides are recorded as overrides

`override_gate=true` advances past an unmet gate, for the case where the evidence
exists outside this system. The transition note gets `[gate overridden]` appended.
A bypassed gate that leaves no trace is indistinguishable from a satisfied one to
anyone reading later.

---

## Personal data (§21, §7 Gate 2)

> §21: "Avoid collecting unnecessary personal information."
> §7 Gate 2: "Do NOT necessarily store identifying personal information."

Honoured by omission. `customer_interviews` has **no** name, email, phone, or
company-name column, and there is a test asserting the schema never grows one —
because a column added in a hurry is exactly how this posture gets lost. What the
scoring model needs is categories (industry, company size, respondent role), and
none of those identify a person. If you need to correlate a row to a person, that
belongs in your own CRM.

### Why `company_ref` exists

One field needs explaining. §7 Gate 3 requires "multiple independent businesses
confirm the problem" — a count of distinct businesses, which is impossible against
a schema that cannot distinguish them. Two interviews at the same company are not
independent evidence.

So `company_ref` is an opaque, operator-chosen label: `retailer-a`, `kl-cafe-3`.
It tells businesses apart without naming them. It is validated as
`^[a-z0-9][a-z0-9_-]*$` and capped at 64 characters, which is what stops
`Restoran Ali Sdn Bhd (ali@example.com)` being passed off as a reference — the
whole personal-data posture of the table rests on this field staying a label.

Interviews and evidence without a `company_ref` still count as evidence; they just
cannot prove independence (Gate 3) or repeatability (Gate 5). The API warns when a
*paid* record arrives without one, because that is the case where the omission
costs the most.

---

## Counting rules that are easy to get wrong

Three of them, and each is implemented **twice** — once in Laravel (which decides
whether a promotion is allowed) and once in Python (which decides whether §29's
cap lifts). A test reads the PHP source and asserts the type lists match, because
if they drift an opportunity can sit at `paid_pilot` while scoring as though
nobody ever paid, and nothing else would report the contradiction.

**Independent confirmations count businesses, not interviews.** `COUNT(DISTINCT
company_ref)` over confirmed interviews. Five conversations at one enthusiastic
customer must not clear Gate 3 alone.

**Paying businesses count businesses, not payments.** Gate 5 wants a *second*
paying business; two pilots with the same customer prove retention, not
repeatability.

**`pilot_interest` is not a strong commercial signal.** §7 Gate 4 is explicit
that a customer paying is "considerably more valuable than 'I would probably use
this'", and stated interest is the polite end of that sentence, not evidence of
budget. It is recorded and counted separately, and it never satisfies Gate 3.

`PAID_TYPES ⊆ STRONG_SIGNAL_TYPES` is asserted: money changing hands must never
fail to count as a strong signal, or an opportunity could clear Gate 4 while
failing Gate 3.

---

## Nullable booleans mean something

`problem_confirmed` and `pilot_interest` are nullable, not defaulted to false.
"We spoke and they do not have this problem" and "we have not established it" are
different outcomes, and only the first is a negative result worth acting on.
`problem_denied_count` is reported separately for exactly that reason.

---

## Experiments require a bar for success

`hypothesis` and `success_metric` are both NOT NULL, and a `completed` experiment
is refused without a `result`.

An experiment with no stated hypothesis and no stated bar for success cannot
fail: whatever happens gets read as encouraging, and the row becomes a record of
effort rather than of evidence. Requiring both up front is what makes a `failed`
result mean something later.

Creation and conclusion are separate calls, because the useful sequence is plan →
run → conclude. Forcing the result to be known at creation time would push people
to create the row afterwards, losing the hypothesis — the part worth recording
*before* you know the answer.

---

## Endpoints

```
GET   /api/v1/opportunities/{id}/validation      everything recorded + gate status
POST  /api/v1/opportunities/{id}/interviews      §7 Gate 2
POST  /api/v1/opportunities/{id}/evidence        §21, Gates 3-5
POST  /api/v1/opportunities/{id}/experiments     §21
PATCH /api/v1/opportunities/{id}/experiments/{n} conclude one
PATCH /api/v1/opportunities/{id}/stage           §52's human approval
PATCH /api/v1/opportunities/{id}                 human-authored fields
```

That last one exists because Gate 1 was otherwise **unreachable** — nothing in the
system could write `target_buyer`. The scoring engine deliberately never touches
it: inferring a buyer from signal `payer_type` would make Gate 1 pass itself,
which is the opposite of what a gate is for. Walking the funnel end to end is what
revealed the gap.

The validation payload is a separate endpoint from `/opportunities/{id}` on
purpose. It is a working view for someone doing customer discovery, and folding it
into the ranked-list detail response would make every dashboard page load carry
it.

### `meta.gates` reports all five, always

Satisfied or not, each with its requirement and — when unmet — the blocking
reason. A UI that only received the passing gates could show progress but never
show what to go and do next. "You cannot promote this" is useless feedback;
"Gate 3 needs a second independent business" tells someone what to do.

---

## Stage history

Every stage change writes an `opportunity_stage_transitions` row holding:

- from, to, and the note
- **what the engine was suggesting at that moment** — so a later reader can see
  whether the human agreed, overrode, or moved without a suggestion
- **a frozen evidence snapshot**

The snapshot is denormalised deliberately. The underlying rows keep changing, and
the question this answers is *"what did we know when we decided"*, which a live
join can never reconstruct. §57 needs that to recalibrate the scoring weights
against real commercial outcomes.

---

## Walking it

```bash
API=http://localhost:8000/api/v1; ID=1

# Gate 2
curl -X POST $API/opportunities/$ID/interviews -H 'Content-Type: application/json' \
  -d '{"company_ref":"retailer-a","problem_confirmed":true,"interviewed_at":"2026-08-02"}'

# Gate 1 (nothing else writes target_buyer)
curl -X PATCH $API/opportunities/$ID -H 'Content-Type: application/json' \
  -d '{"target_buyer":"business_owner"}'

# Gate 3 needs a second business AND a strong signal
curl -X POST $API/opportunities/$ID/interviews -H 'Content-Type: application/json' \
  -d '{"company_ref":"retailer-b","problem_confirmed":true,"interviewed_at":"2026-08-04"}'
curl -X POST $API/opportunities/$ID/evidence -H 'Content-Type: application/json' \
  -d '{"evidence_type":"proposal","company_ref":"retailer-a","value":6000,"occurred_at":"2026-08-05"}'

# Gate 4 — money
curl -X POST $API/opportunities/$ID/evidence -H 'Content-Type: application/json' \
  -d '{"evidence_type":"paid_pilot","company_ref":"retailer-a","value":4500,"occurred_at":"2026-08-07"}'

curl -X PATCH $API/opportunities/$ID/stage -H 'Content-Type: application/json' \
  -d '{"status":"paid_pilot","note":"RM4,500 pilot invoiced and paid"}'

# The cap lifts only after rescoring
docker compose exec intelligence python -m intelligence.cli score
```

Observed on the demo data: opportunity score **55.82 → 75.49**, with
`+15 paid pilot bonus (§29)` in the stored notes and the recommendation moving
`WATCH → SELL_PILOT`. The dashboard's validation page (`/opportunities/{id}/
validation`) does all of the above through forms.
