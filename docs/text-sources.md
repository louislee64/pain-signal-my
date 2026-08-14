# Public text sources

PROJECT_SPEC.md §17 (public text sources), §13 (acquisition policy), §21 (personal
data), §38 (scheduling), §43 (multilingual).

Two collectors live here. `rss_feed` (eight Malaysian news feeds, live) and
`reddit_subreddit` (three subreddits, built and deliberately disabled pending a
terms decision). Before either existed the only source was data.gov.my fuel
prices — machine-generated numbers that match no topic keyword by design — so the
whole text pipeline was working on demo data.

**Read the yield section before adding more news feeds.** The collector works;
the honest answer about what news carries is less comfortable, and it is the
reason the Reddit collector exists.

---

## News feeds (`rss_feed`, live)

Adding a feed is a `config/sources.yaml` entry and nothing else:

```yaml
  - slug: fmt_business
    name: "Free Malaysia Today — Business"
    source_type: news_feed
    collector: rss_feed
    config:
      feed_url: "https://www.freemalaysiatoday.com/category/business/feed/"
      fetch_articles: false
      requests_per_minute: 20
      language: en
      region: MY
```

```bash
docker compose exec api php artisan sources:sync
docker compose exec api php artisan sources:ingest --type=news_feed
```

`sources:ingest` reads the registry rather than naming slugs, so §13/§67's
"adding a source needs no code change" survives contact with the scheduler. A
hardcoded slug in `routes/console.php` would have broken that in the most
irritating way available: the source works when run by hand and silently never
runs again.

---

## Which feeds exist, and which do not

§13 ranks "official RSS/feed" third, above licensed APIs and web collection. It is
the highest tier actually available for Malaysian SME text — but most of the
obvious publishers do not offer it.

**No usable feed** (checked, not assumed): The Star, New Straits Times, The Edge
Malaysia, Bernama, SME Corp Malaysia (403), MDEC, Astro Awani, Sin Chew, Oriental
Daily, Nanyang, Sinar Harian Bisnes (feed present, zero items).

That list matters as much as the enabled one. Anyone adding "just pull The Star's
SME section" as a task should know it has no feed to pull.

**Enabled (8):**

| Source | Lang | Feed body | Notes |
|---|---|---|---|
| `fmt_business` | en | ~2,430 chars | full `content:encoded` |
| `malaymail_money` | en | ~2,590 | full |
| `malaysian_reserve` | en | ~2,500 | full, business-specialist |
| `digital_news_asia` | en | ~4,780 | enterprise/SME digitalisation |
| `hmetro_bm` | ms | ~2,320 | **highest SME hit rate measured** |
| `utusan_bm` | ms | ~2,220 | full |
| `businesstoday_my` | en | ~370 | teaser only; article fetch blocked, see below |
| `thevibes_business` | en | 0 | headline only; article fetch works |

**Disabled (1):** `vulcanpost_my`, and the reason is worth keeping. It had by far
the richest SME-operational content of anything tested — a merchant whose margins
fell from 28% to 6%, owners explaining why they borrow. Exactly what this project
wants. And 9 of its 10 entries were about **Singapore**. Ingesting it as `region:
MY` would put Singaporean businesses behind Malaysian opportunity scores and
corrupt §26's geographic-spread dimension. §41 forbids that, so it is off until
per-entry country detection exists.

---

## Full-text fetching

Most feeds carry the whole article. Two publish headlines alone, so the body has
to come from the page. That fetch is governed by
`collectors/fetching.py`, and nothing about it is incidental:

- **robots.txt first, per host, cached.** Failure handling follows RFC 9309: a
  4xx means no rules exist (allow), a 5xx or network error means we could not
  read the rules (refuse). Collapsing those into "allow on any failure" is how a
  crawler ends up ignoring a robots.txt that was behind a flaky proxy.
- **Rate limit per host**, default 20/minute. A publisher's `Crawl-delay` wins
  whenever it asks for more patience — `businesstoday.com.my` declares 10s and
  gets it. It never makes us faster: `Crawl-delay: 0` is not an invitation.
- **A per-run cap** on fetches, and it is **logged when it bites**. The Vibes has
  100 entries and a cap of 25; the run records `entries_left_thin: 75`. A
  silently truncated run looks like a source with less to say than it had.
- **Fetch only when the feed body is thin** (<600 chars). Measured feed bodies
  cluster at 0–430 or 2,000–9,000 characters, so 600 sits in the empty gap
  between the two populations rather than at a round number. A publisher who
  already sent the article is not asked for it again.
- **Extraction favours precision.** Navigation and related-article headlines are
  not article text, and letting them through would let a site's own menu match
  topic keywords and manufacture signals.

### robots.txt permission is not access

`businesstoday_my` is the useful lesson. Its robots.txt allows the article paths
and politely declares `Crawl-delay: 10`, which the limiter honoured. All ten
requests returned **403 Forbidden** anyway.

A 403 to an honestly-identified client is the publisher declining. §17 says "avoid
bypassing technical controls", so the response was to set `fetch_articles: false`
— not to send a browser User-Agent instead. Retrying nightly would be ten
pointless requests to a host that has already said no. The ~370-character teaser
is what that source contributes.

The bot identifies itself, with a URL to complain to:

```
PainRadarBot/0.1 (Malaysia SME Pain Radar; +https://github.com/louislee64/pain-signal-my)
```

---

## §21 and the immutable-raw trade-off

Text is the first free-form human writing this project stores, and §21 says to
avoid collecting unnecessary personal information. Three things happen before
storage:

1. **Bylines are dropped.** Every live feed measured carries `dc:creator` or an
   Atom `<author>`. A journalist's name is personal information no part of this
   system needs, so it is never written — not to a column, not into the payload.
2. **Emails and Malaysian phone numbers are redacted** in titles, summaries and
   article bodies alike. Storing the raw summary beside a redacted body would
   defeat the purpose, so both go through the same scrubber.
3. **Comments are excluded** from extraction — the most personal-data-dense part
   of a news page.

Redaction is visible (`[email redacted]`), not silent deletion, so a reader knows
something was removed rather than reading the result as the original.

**This is in tension with §18's immutable raw layer, deliberately.** §21 is a rule
about what we *collect*; once a phone number is in `raw_documents` it has already
been collected, and immutability would preserve it forever. So the scrub happens
at collection and provenance is preserved as source + URL + feed entry + fetch
timestamp + `body_source` — a faithful record of what arrived and where from, not
a byte-identical copy of the publisher's HTML.

`payload.body_source` records whether the body came from `feed` or `article`, and
`body_fetch_note` records why a fetch did not produce one (`robots_disallowed`,
`fetch_failed`, `extraction_empty`, `per_run_cap_reached`). Without those, a short
document is indistinguishable from a blocked one.

The phone pattern is bounded so it cannot clip a price or a year — there is a test
asserting `"In 2026 the group reported RM54 billion, up 7.4% from 1.9%"` survives
untouched. A redaction loose enough to eat those would quietly corrupt every
economic signal in the corpus.

---

## §38's conditional fetch, finally exercised

The conditional-fetch path was built for data.gov.my, which sends neither `ETag`
nor `Last-Modified`, so it had never actually engaged against a live source. RSS
feeds do send them. Six of the eight enabled sources now store a validator, and a
re-run produces a real 304:

```
{"source": "fmt_business", "status": "succeeded", "source_unchanged": true,
 "received": 0, "inserted": 0}
```

Incremental collection is client-side — RSS has no server-side date parameter — so
`since` is applied after parsing. Its value is not saving the upsert, which is
idempotent anyway, but **not spending an article fetch** on an entry stored last
night.

---

## Yield: what news feeds actually contain

This is the part to read before expanding.

Measured over a live 191-article corpus from seven feeds:

- **0 of 140 articles** matched any pre-existing topic keyword.
- The most frequent terms were macroeconomic: `inflation` (30 articles), `costs`
  (29), `ringgit` (19), `logistics` (13). Operational terms were nearly absent:
  `invoice` (1), `point of sale` (1), `payroll` (2). `e-invoice`, `myinvois`,
  `lhdn` and `minimum wage`: **zero**.
- `sme`/`smes` appeared in 9 of 140.
- After tuning, a deliberately tight keyword set matched **9 articles in 191**.

Live ingestion produced **301 documents** and **13 signals** across **2 topics**.

So: Malaysian general news does not carry SME operational complaints. It carries
macroeconomic commentary. The single best item found was a Harian Metro headline —
*"80 peratus perniagaan hadapi tekanan kos"* (80% of businesses face cost
pressure) — and it took a Bahasa Malaysia tabloid to produce it, which is §43
earning its keep rather than being a principle.

### Why the keywords are all multi-word

Candidate single words were tested against real text and rejected for what they
matched:

| Rejected | What it actually matched |
|---|---|
| `cukai` (tax) | `keuntungan sebelum cukai` — profit **before** tax, i.e. every bank earnings report |
| `kos sara hidup` | `Kementerian Perdagangan Dalam Negeri dan Kos Sara Hidup` — the ministry's own name |
| `system integration` | an ECRL railway commissioning story |
| `profit margin` | listed-company downgrades (Gamuda, Toyota) |
| `cash flow` | `negative free cash flow` in analyst notes |
| `automation` | semiconductor fab capacity announcements |

`tekanan kos` is used instead of `kos sara hidup` — it finds the same cost-pressure
stories without matching the ministry.

A keyword that fires on the wrong thing is worse than a missing one: §41 forbids
letting weak evidence look strong, and `mention_frequency` counts a false signal
exactly like a real one.

Some added phrases match nothing in the current corpus. That is deliberate — they
describe their topic correctly and will fire when such an article appears. Absence
today is a fact about the news cycle, not evidence the keyword is wrong.

### Macro cost signals are legitimate, and stay weak by construction

§14 explicitly endorses this derivation: "Chicken price increased" → "Restaurants
may be experiencing ingredient-cost pressure". So BNM inflation commentary is real
if weak evidence of SME cost pressure.

It stays weak without anyone remembering to keep it weak. `price_cost_pressure`
came out of the live run with the **highest confidence of any topic (63.5)** —
six independent publishers corroborating, all reporting today — and the **lowest
opportunity score (11.5), recommendation IGNORE**:

```
confidence:  source_diversity 6 (target 3) → 100, contributing 25.0
             data_recency                  → 100, contributing 20.0
opportunity: implementation_fit            →  30  (§28, config/scoring.yaml)
             payer_clarity                 →   0
```

That is §30's separation of score from confidence doing exactly its job: *we are
fairly sure this problem is real, and it is still not a business we can build.*
§28 scores `price_cost_pressure` at 30 because the lever is supplier negotiation,
not software. It was also the first time `source_diversity` had more than one
source to measure.

### What would actually move the needle

Not more news feeds. A source where business owners describe their own
operational problems. That is what the Reddit collector below is for — built,
tested, and deliberately switched off pending a decision only you can make.

---

## Forum discussions: the Reddit collector

`reddit_subreddit`, covering §17's "public forum discussions". Three sources are
registered — `reddit_malaysia`, `reddit_malaysianpf`, `reddit_bolehland` — and
**all three ship `enabled: false`**.

### Why this source type is different

Every other source in the registry is somebody describing the economy. This is
owners describing their own operations, in the phrasing §4's taxonomy was written
for. The fixture used in the tests is representative of what the format produces:

> "Boss here. Every month we do stock count and the numbers never match between
> my two outlets. Kena reconcile manual entry in Excel setiap hari…"

That single post touches `stock_count`, `reconciliation`, `workflow_manual_process`
and a `business_owner` payer, and it carries the frequency marker (`setiap hari`)
that §27's recurrence dimension reads. No news article in the 191-article corpus
did any of that. The topics where §28 scores implementation fit 90–95 — billing,
inventory, bookings, manual workflow, integrations — currently have **zero** real
signals; this is the source type that can change that.

### How it accesses Reddit, and why that is not a workaround

```
https://www.reddit.com/robots.txt  →  User-agent: *
                                      Disallow: /
legacy https://www.reddit.com/r/<sub>/new.json  →  403
```

Reddit refuses to be crawled, and closed the unauthenticated JSON path. So the
collector uses the **official Data API** on `oauth.reddit.com` with OAuth2
client-credentials — §13's **tier 1**, above everything else in this document —
and **never fetches a reddit.com page**.

That distinction is the whole basis for using this source at all. robots.txt
governs crawling; the Data API is credentialed, licensed access under separate
terms. We are not routing around the refusal, we are not the thing it refuses.
There is a test (`test_it_never_requests_a_reddit_com_web_page`) asserting every
request goes to the API host or the token endpoint, precisely so nobody later
"improves" this by adding a page fetch or a browser User-Agent.

### Why it is disabled — two separate reasons

**1. Credentials (mechanical).** Create a *script* app at
<https://www.reddit.com/prefs/apps>, then in `apps/intelligence/.env`:

```bash
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USERNAME=louislee64   # optional but recommended
```

`REDDIT_USERNAME` shapes the User-Agent into Reddit's documented form
(`python:my.painradar.collector:0.1 (by /u/<username>)`); it throttles generic
agents hard. A contact URL is substituted when absent.

Without credentials, an enabled source fails loudly rather than quietly
collecting nothing — verified end to end:

```
run status: failed
error: "reddit_subreddit collector needs REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET
        in apps/intelligence/.env. Create a 'script' app at
        https://www.reddit.com/prefs/apps to get them, and read the
        commercial-use note in docs/text-sources.md before enabling the source."
health: {"status": "failing", "reasons": ["Last run failed", "1 error(s) in the last run"]}
```

Wrong credentials are distinguished from an outage: a 401/403 on the token
endpoint says "confirm the app is a script type and the secret has not been
rotated" instead of retrying into a wall.

**2. Terms (yours to decide).** Reddit's Data API Terms and Public Content Policy
restrict commercial use, and §6 gives this project commercial intent. That is a
licensing judgement about someone else's platform, not a technical check, so
`terms_status: needs_review` and nothing enables itself. §17 asks for exactly this
review. There are tests asserting all three sources stay disabled and
`needs_review`, so no future code change can flip them on quietly.

Reddit's own robots.txt points at
[r/reddit4researchers](https://www.reddit.com/r/reddit4researchers/) for
non-commercial research access — worth reading before deciding, since it may be
the cleaner route depending on how you characterise this project.

### §21: the username is the whole problem

`personal_data_risk: medium` — the highest in the registry, and not pessimism.
This is user-generated text where people volunteer details about themselves and
their businesses.

**The Reddit username is never stored.** `author`, `author_fullname` and
`author_flair_text` are all excluded. A handle links every post a person has ever
made across every subreddit, which makes it a *stronger* identifier than a
journalist's byline, not a weaker one — "pseudonymous" is not "anonymous". Emails
and phone numbers are scrubbed from title and body by the same
`scrub_contact_details` used for news.

What is stored is the post id, the subreddit, the permalink, the timestamp, flair,
and the scrubbed text. The permalink contains no username.

**Before enabling, revisit §49's PDPA posture.** Nothing here stores an identifier
deliberately, but the prose is written by identifiable people who did not publish
it as a business record, and that is a different situation from a news feed.

### Two smaller decisions worth knowing

**Engagement counters are not stored** — `score`, `ups`, `num_comments`,
`upvote_ratio` are all dropped. Not squeamishness: they change hourly, so
including them in the payload would change the content hash and mark every recent
post `updated` on every nightly run. Nothing consumes them (§26's
mention_frequency counts signals, not upvotes), so a snapshot that goes stale
immediately buys churn and no information. If engagement-weighted severity is ever
wanted it needs its own mechanism, not a field that silently rewrites
`raw_documents` every night.

**Tombstones are not text.** `[deleted]` and `[removed]` bodies are discarded
rather than stored, so a removed post cannot look like a real one that happened to
say nothing. The title survives if it is real. `min_body_chars: 120` drops
one-line posts, which forums produce in bulk and §22 cannot classify.

### Rate limiting

Reddit's free tier is 100 requests/minute **per OAuth client**, shared across every
source using the same credentials. The registry declares 60/minute for each of the
three subreddits so they cannot breach it between them, and there is a test
asserting that. Beyond the static floor, the collector reads
`X-Ratelimit-Remaining` / `X-Ratelimit-Reset` and sleeps when Reddit says the
budget is gone — server feedback beats any static guess, because the budget is
shared. Pagination is capped at 10 pages per run and logs when the cap bites.

### Enabling it

```bash
# 1. credentials in apps/intelligence/.env, then:
docker compose up -d --force-recreate intelligence

# 2. decide the terms question, then set enabled: true and terms_status
#    in config/sources.yaml for the subreddits you want

docker compose exec api php artisan sources:sync
docker compose exec api php artisan sources:ingest --type=forum
docker compose exec intelligence python -m intelligence.cli normalize
docker compose exec intelligence python -m intelligence.cli classify
docker compose exec intelligence python -m intelligence.cli aggregate
docker compose exec intelligence python -m intelligence.cli score
```

`--type=forum` is not in the schedule yet, deliberately: adding a nightly entry
for a source whose terms are unresolved would be a scheduled licensing risk. Add
it to `routes/console.php` when you enable the sources.

### What it has NOT been verified against

Live Reddit data. The entire test suite (43 tests) runs against fixture JSON,
because a suite that only passes for whoever holds the API secret is not a suite.
The OAuth flow, pagination cursor, rate-limit handling and §21 scrubbing are all
exercised — against recorded shapes, not a live response. Expect the first real
run to surface something the fixtures did not, most likely in whichever fields
r/malaysia populates differently from the documented schema.

---

## Terms status: unreviewed, and that is accurate

Every feed is `terms_status: unreviewed`. What was verified is narrow:

- robots.txt permits the article paths for our User-Agent (checked
  programmatically, per host).
- The feed is published openly, no credential, no paywall.

What was **not** verified is each publisher's Terms of Use, specifically whether
storing extracted full-article text is permitted. That is a copyright judgement
about someone else's content, not a technical check, and it is a human decision.
§17 asks for it ("review terms") and it is deliberately not being claimed here.

`fetch_articles` is therefore off wherever the feed already carries the body, so
full-text extraction touches **one** publisher rather than eight.

`personal_data_risk` is `low`, not `none`: news prose is human-written and can name
people. No identifier is stored deliberately, but this is not machine-generated
data the way fuel prices are.

---

## Operational notes

**Classification starvation.** Fixed as part of this work, and worth knowing
about. A document matching no keyword produces no `document_topics` row, so it is
re-scanned forever — deliberate, since rule-based matching is cheap. But the query
had `LIMIT` and no `ORDER BY`, so Postgres could return the same arbitrary 500
never-matching documents indefinitely, and newly ingested documents were never
classified at all. With 945 fuel-price documents in front of them, the news
articles were invisible: `classify` reported "500 documents, 0 matches" on every
pass. The query is now newest-first with an id tiebreak. Regression test:
`tests/test_classification_order.py`.

**Naive vs aware timestamps.** Laravel migrations create `timestamp(0)` columns —
WITHOUT time zone — so Postgres returns naive datetimes even though `db.py`
declares `DateTime(timezone=True)`. A collector comparing `since` against a parsed
feed date raised `can't compare offset-naive and offset-aware datetimes` **only on
the second run**, because the first has no `last_successful_sync`. Fixed once at
the read boundary in `repositories/sources.py`.

**Draining the pipeline.** `normalize` and `classify` process 500 documents per
invocation. Eight feeds produce ~300 documents a day, so one nightly pass is
enough — but after a first bulk ingest, run them until they report zero.

```bash
docker compose exec api php artisan sources:ingest --type=news_feed
docker compose exec intelligence python -m intelligence.cli normalize
docker compose exec intelligence python -m intelligence.cli classify
docker compose exec intelligence python -m intelligence.cli aggregate
docker compose exec intelligence python -m intelligence.cli score
```
