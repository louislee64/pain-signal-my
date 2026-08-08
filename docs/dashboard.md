# The dashboard

Milestone 5. PROJECT_SPEC.md §33 (opportunity dashboard), §34 (detail page),
§36 (API design).

The acceptance criterion is a question, not a feature list:

> Opening the dashboard answers: **What are the strongest opportunities right now
> and why?**

Both halves are load-bearing. "Strongest" is the ranked table; "and why" is the
reason every row links to a stored score breakdown and every card carries the
figure that earned it its place.

§33 also says what the page must *not* answer — "How much data did we scrape?"
So the collection counts sit at the bottom of the overview under a link to the
source-health page, not at the top.

---

## Pages

| Page | Answers |
|---|---|
| `/` | What should I look at this week, and what's rising? |
| `/opportunities/{id}` | Why is this score what it is, and what evidence backs it? |
| `/topics` | Where is the activity across the taxonomy? |
| `/topics/{slug}` | What have the sources actually said about this problem? |
| `/trends` | What is Malaysian search interest doing? (Milestone 3) |
| `/sources` | Can I trust today's numbers? |

---

## Endpoints

```
GET /api/v1/dashboard              §33's five cards + collection block
GET /api/v1/opportunities          ranked, filtered
GET /api/v1/opportunities/{id}     §34's sections + full score breakdown
GET /api/v1/topics                 taxonomy with observed activity
GET /api/v1/topics/{slug}          one topic's evidence
GET /api/v1/sources                per-source health
GET /api/v1/ingestion-runs         run history
```

`POST /sources/{id}/run` appears in §36's endpoint list and is **deliberately not
implemented**. It would give the API write access to a pipeline the Python
service owns, and a dashboard button that fires a long-running collector hides
both its duration and its failures. Triggering runs is a scheduler concern
(§38, Milestone 7).

---

## The five cards (§33)

| Card | Ranked on | Why that and not something else |
|---|---|---|
| Top opportunity | `opportunity_score` | — |
| Fastest rising | stored `pain_score.dimensions.growth.raw` | reads the same stored number the detail page shows, so card and page can never disagree |
| Strongest buyer evidence | `payer_clarity` normalized | §27 weights payer clarity highest of the six commercial dimensions: knowing who pays is what separates a problem from a business |
| Newest emerging problem | `MIN(signal_date)` per topic | "newest" means newly *appearing*. Ranking on the latest signal would just return the busiest topic under a misleading label |
| Highest paid validation | nothing yet | declared unavailable — see below |

### Empty states say which emptiness they mean

A null card means "nothing qualified for *this* ranking", which is usually not
the same statement as "nothing is scored". Growth needs a prior window to compare
against; payer clarity needs a payer to have been inferred at all. So each card
carries its own message. One generic "nothing scored yet" across all five would
tell the reader something untrue about four of them.

The paid-validation card returns `available: false` with a reason rather than
being omitted. A card that silently disappears reads as "no opportunity has paid
validation" — a claim about the work. "We don't track this yet" is the truth.

---

## Filters

Implemented: `topic`, `buyer`, `state`, `source`, `since`, `recommendation`,
`status`, `min_confidence`, `min_opportunity`.

`state` and `source` describe the *evidence*, not the opportunity, so they match
on whether any of the topic's signals came from there.

Confidence is a floor, not an equality match. §30's point is that a score means
little without its confidence, so the useful question is "show me only what I can
believe", not "confidence exactly 61".

Two of §33's filters are **not** implemented, and the API says so in
`meta.filters_not_yet_available`:

- **industry** — `industry_id` exists on the table but nothing populates it; no
  industry classifier has been built.
- **commercial stage** beyond `status` — pilots and paying customers arrive with
  the CRM tables in Milestone 6 (§21).

The overview reads that metadata and omits those controls. A filter that silently
matches nothing is worse than an absent one: it reads as "no opportunities in
retail" rather than "we don't classify industry".

---

## Score explainability

`/opportunities/{id}` renders `score_components` as a table per score: each
dimension's raw input, its normalized 0–100 value, its weight, and its
contribution — largest contribution first, because the reader's question is "what
drove this" and alphabetical order answers a question nobody asked.

The weight column stays visible so a small contribution can be told apart from a
small weight. Stored notes are rendered above each table, because without them a
reader cannot distinguish "no data" from "measured as zero" — the difference
between `growth: no prior window to compare against` and a genuinely flat topic.

---

## Source health

The failure this page exists for is not the loud one. A collector that errors gets
noticed. A collector that **succeeds and returns zero records** raises nothing
anywhere, and every score that depended on it quietly drains away.

Statuses: `ok`, `degraded`, `stale`, `failing`, `never_run`, `disabled`.

Reasons are a list, not a message — a source can be both stale and returning
nothing, and reporting whichever check ran first hides half the problem. `ok` with
an empty reason list is the only healthy shape, so a check added later cannot pass
by default.

`Source::health()` lives on the model because two pages ask the question: the
source page and the overview's collection block. Two implementations would drift,
and silently — the overview reading "0 problems" while `/sources` lists three.
There is a test asserting the two agree.

Compliance posture (`terms_status`, `personal_data_risk`, `license`) sits on the
same row as the delivery figures. §11/§42: whether the evidence is legally usable
matters as much as whether it arrived.

---

## Charts

Three rules, each of which rules out something tempting:

**One axis, always.** The activity chart plots mentions per day and puts average
severity in the tooltip instead of on a second line. Mentions are a count and
severity is a 0–100 index; sharing one y-axis would be meaningless, and giving
them separate axes would be worse — a dual-axis chart lets any two series be made
to look correlated.

**Bars for counts, lines for continuous quantities.** Mentions per day are
discrete counts, so they are bars. A line implies a continuous quantity was
sampled and interpolates across days that genuinely had zero mentions.

**x is scaled by date, not by array index.** A gap in collection reads as a gap
rather than being compressed into an even cadence.

Identity is never carried by colour alone. Score bars are four separate
single-value bars, each directly labelled, so no categorical palette is needed at
all. Recommendation and health chips always render their text label; colour only
carries emphasis. Every chart has a table view beside it.

Design tokens live in `apps/web/assets/css/tokens.css`. They were duplicated
inside `pages/trends.vue`'s scoped block until this milestone needed them on five
pages — scoped styles cannot share tokens, and five copies of a palette is how
three slightly different greys ship.

---

## Demo data

The dashboard cannot be verified on an empty database, and the one real source
wired up so far (data.gov.my fuel prices) produces no topic matches by design —
it is price data, not complaints.

```bash
docker compose exec api php artisan db:seed --class=DemoDataSeeder
docker compose exec intelligence python -m intelligence.cli aggregate
docker compose exec intelligence python -m intelligence.cli score
```

Five topics chosen to exercise different shapes the pages must render: a strong
well-evidenced case, a rising one, a single-source one (which §31 should hold
back), a code-switched one, and one whose evidence is all months old (which the
30-day scoring window correctly declines to score at all). Three sources with
deliberately different health states, so the source page shows something other
than a column of green.

Two rules make it safe:

1. **It writes signals and evidence, never `opportunities` rows.** Scores come
   from running the real engine over this data. A hand-written score would make a
   broken scorer look fine.
2. **Everything is prefixed `demo_` and every document says it is fabricated.**
   Re-seeding is idempotent; `php artisan demo:purge` removes exactly what it
   created and nothing else.

Purge leaves derived rows alone on purpose: they are recomputed by `aggregate` /
`score`, and deleting an opportunity would also destroy any human-authored
narrative on it (§52). The command says so and names the commands to run.

Never seed this against production. The prefix is what makes that recoverable.
