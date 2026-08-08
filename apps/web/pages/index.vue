<script setup lang="ts">
/**
 * Milestone 5's acceptance criterion: opening this page must answer
 *
 *   "What are the strongest opportunities right now and why?"
 *
 * The "and why" half is why every row links to its breakdown and why the cards
 * carry the figure that earned them their place rather than just a superlative.
 * §33 is also explicit about what this page must NOT lead with — how much data
 * was scraped — so the collection counts sit at the bottom under a link to the
 * source-health page.
 */
const config = useRuntimeConfig()
const apiBase = config.public.apiBaseUrl

interface Card {
  available?: boolean
  reason?: string
  id?: number
  title?: string
  topic?: string
  topic_name?: string
  opportunity_score?: string | null
  confidence_score?: string | null
  recommendation?: string | null
  because?: string
  growth_percent?: number
  payer_clarity?: number
  target_buyer?: string | null
  first_seen?: string
  signal_count?: number
}

interface OpportunityRow {
  id: number
  title: string
  topic: string | null
  topic_name: string | null
  status: string
  recommendation: string | null
  pain_score: string | null
  commercial_score: string | null
  opportunity_score: string | null
  confidence_score: string | null
}

const { data: dashboard, error: dashboardError } = await useFetch<{
  data: { cards: Record<string, Card | null>; system: Record<string, unknown> }
  meta: { answers: string }
}>(`${apiBase}/dashboard`)

// Filters live in one row above the table (§33's filter list, restricted to the
// ones with data behind them — the API reports which are not yet available and
// this page omits those controls rather than shipping dead ones).
const recommendation = ref('')
const minConfidence = ref('')
const query = computed(() => {
  const params = new URLSearchParams({ limit: '50' })
  if (recommendation.value) params.set('recommendation', recommendation.value)
  if (minConfidence.value) params.set('min_confidence', minConfidence.value)
  return params.toString()
})

const { data: list } = await useAsyncData(
  'opportunity-list',
  () => $fetch<{
    data: OpportunityRow[]
    meta: { count: number; filters_not_yet_available: Record<string, string> }
  }>(`${apiBase}/opportunities?${query.value}`),
  { watch: [query] },
)

const CARD_TITLES: Record<string, string> = {
  top_opportunity: 'Top opportunity',
  fastest_rising: 'Fastest rising',
  strongest_buyer_evidence: 'Strongest buyer evidence',
  newest_emerging_problem: 'Newest emerging problem',
  highest_paid_validation: 'Highest paid validation',
}

// A null card means "nothing qualified for THIS ranking", which is rarely the
// same statement as "nothing is scored". Growth needs a prior window to compare
// against; payer clarity needs a payer to have been inferred at all. One generic
// message across all five would tell the reader something untrue about four of
// them.
const CARD_EMPTY: Record<string, string> = {
  top_opportunity: 'Nothing scored yet.',
  fastest_rising: 'No topic has a prior window to compare against yet.',
  strongest_buyer_evidence: 'No payer inferred from any signal yet.',
  newest_emerging_problem: 'No signals recorded yet.',
}

const cards = computed(() =>
  Object.entries(dashboard.value?.data.cards ?? {}).map(([key, card]) => ({
    key,
    title: CARD_TITLES[key] ?? key,
    card,
  })),
)

const rows = computed(() => list.value?.data ?? [])
const system = computed(() => dashboard.value?.data.system ?? {})

function score(value: string | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return Number(value).toFixed(0)
}

function cardFigure(key: string, card: Card): string | null {
  if (key === 'fastest_rising' && card.growth_percent !== undefined) {
    return `${card.growth_percent > 0 ? '+' : ''}${card.growth_percent}% vs previous window`
  }
  if (key === 'strongest_buyer_evidence' && card.payer_clarity !== undefined) {
    return `payer clarity ${card.payer_clarity}${card.target_buyer ? ` · ${card.target_buyer.replace(/_/g, ' ')}` : ''}`
  }
  if (key === 'newest_emerging_problem' && card.first_seen) {
    return `first seen ${card.first_seen.slice(0, 10)} · ${card.signal_count} signals`
  }
  return null
}
</script>

<template>
  <div>
    <header class="head">
      <h1>What should I investigate or sell this week?</h1>
      <p class="head__sub">
        Ranked by blended opportunity score. Every number links to the evidence behind it.
      </p>
    </header>

    <p v-if="dashboardError" class="notice notice--error">
      Could not reach the API at {{ apiBase }}.
    </p>

    <template v-else>
      <section class="cards" aria-label="Highlights">
        <article v-for="entry in cards" :key="entry.key" class="card">
          <h2 class="card__title">{{ entry.title }}</h2>

          <template v-if="entry.card === null">
            <p class="card__empty">{{ CARD_EMPTY[entry.key] ?? 'Nothing to show yet.' }}</p>
          </template>

          <!-- A card that declares itself unavailable is honest; one that
               silently vanishes reads as "no opportunity qualifies". -->
          <template v-else-if="entry.card.available === false">
            <p class="card__empty">Not tracked yet</p>
            <p class="card__reason">{{ entry.card.reason }}</p>
          </template>

          <template v-else>
            <NuxtLink :to="`/opportunities/${entry.card.id}`" class="card__link">
              {{ entry.card.title }}
            </NuxtLink>
            <div class="card__figures tabular">
              <span class="card__score">{{ score(entry.card.opportunity_score) }}</span>
              <span class="card__confidence">
                confidence {{ score(entry.card.confidence_score) }}
              </span>
            </div>
            <ScoreBadge :value="entry.card.recommendation" kind="recommendation" />
            <p class="card__because">
              {{ cardFigure(entry.key, entry.card) ?? entry.card.because }}
            </p>
          </template>
        </article>
      </section>

      <section class="listing">
        <div class="listing__head">
          <h2 class="listing__title">
            Opportunities
            <span class="listing__count">{{ rows.length }} shown</span>
          </h2>

          <div class="filters">
            <label class="filter">
              <span class="filter__label">Recommendation</span>
              <select v-model="recommendation" class="filter__control">
                <option value="">All</option>
                <option value="PRODUCTIZE">Productize</option>
                <option value="SELL_PILOT">Sell pilot</option>
                <option value="VALIDATE">Validate</option>
                <option value="INVESTIGATE">Investigate</option>
                <option value="WATCH">Watch</option>
                <option value="IGNORE">Ignore</option>
              </select>
            </label>

            <label class="filter">
              <span class="filter__label">Min confidence</span>
              <select v-model="minConfidence" class="filter__control">
                <option value="">Any</option>
                <option value="30">30+</option>
                <option value="50">50+</option>
                <option value="70">70+</option>
              </select>
            </label>
          </div>
        </div>

        <p v-if="rows.length === 0" class="notice">
          No scored opportunities yet. Classify some documents, then run
          <code>intelligence score</code>.
        </p>

        <div v-else class="scroller">
          <table class="table tabular">
            <thead>
              <tr>
                <th scope="col">Opportunity</th>
                <th scope="col">Topic</th>
                <th scope="col">Pain</th>
                <th scope="col">Commercial</th>
                <th scope="col">Opportunity</th>
                <th scope="col">Confidence</th>
                <th scope="col">Recommendation</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.id">
                <th scope="row" class="table__name">
                  <NuxtLink :to="`/opportunities/${row.id}`">{{ row.title }}</NuxtLink>
                </th>
                <td class="table__topic">
                  <NuxtLink v-if="row.topic" :to="`/topics/${row.topic}`">
                    {{ row.topic_name ?? row.topic }}
                  </NuxtLink>
                  <span v-else>—</span>
                </td>
                <td class="table__muted">{{ score(row.pain_score) }}</td>
                <td class="table__muted">{{ score(row.commercial_score) }}</td>
                <td class="table__lead">{{ score(row.opportunity_score) }}</td>
                <!-- §30: confidence sits beside the score it qualifies, never
                     one column away or one page away. -->
                <td>{{ score(row.confidence_score) }}</td>
                <td>
                  <ScoreBadge :value="row.recommendation" kind="recommendation" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <p v-if="list?.meta.filters_not_yet_available" class="footnote">
          Industry and commercial-stage filters are not shown:
          <template v-for="(reason, name) in list.meta.filters_not_yet_available" :key="name">
            {{ reason }}<template v-if="name !== 'commercial_stage'">; </template>
          </template>
        </p>
      </section>

      <!-- §33: not the headline. Present because a dashboard that hides a dead
           collector is worse than one that buries the counts. -->
      <section class="system">
        <h2 class="system__title">Collection</h2>
        <dl class="system__grid tabular">
          <div>
            <dt>Signals</dt>
            <dd>{{ system.signals ?? '—' }}</dd>
          </div>
          <div>
            <dt>Scored opportunities</dt>
            <dd>{{ system.opportunities_scored ?? '—' }}</dd>
          </div>
          <div>
            <dt>Enabled sources</dt>
            <dd>{{ system.sources_enabled ?? '—' }}</dd>
          </div>
          <div>
            <dt>Sources needing attention</dt>
            <dd :class="{ 'system__warn': Number(system.unhealthy_sources ?? 0) > 0 }">
              {{ system.unhealthy_sources ?? '—' }}
            </dd>
          </div>
          <div>
            <dt>Last ingestion</dt>
            <dd>{{ system.last_ingestion_at ? String(system.last_ingestion_at).slice(0, 16).replace('T', ' ') : 'never' }}</dd>
          </div>
        </dl>
        <NuxtLink to="/sources" class="system__link">Source health &rarr;</NuxtLink>
      </section>
    </template>
  </div>
</template>

<style scoped>
.head {
  margin-bottom: 1.5rem;
}

h1 {
  font-size: 1.4rem;
  margin: 0 0 0.3rem;
  letter-spacing: -0.015em;
}

.head__sub {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.85rem;
}

.notice {
  padding: 0.75rem 0.9rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-1);
  color: var(--text-secondary);
  font-size: 0.82rem;
  line-height: 1.5;
}

.notice--error {
  color: var(--status-critical);
}

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 0.75rem;
  margin-bottom: 2rem;
}

.card {
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.8rem 0.85rem;
  display: grid;
  gap: 0.4rem;
  align-content: start;
}

.card__title {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.045em;
  color: var(--text-muted);
  margin: 0;
  font-weight: 600;
}

.card__link {
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--text-primary);
  text-decoration: none;
  line-height: 1.3;
}

.card__link:hover {
  color: var(--accent);
}

.card__figures {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}

.card__score {
  font-size: 1.6rem;
  font-weight: 680;
  line-height: 1;
}

.card__confidence {
  font-size: 0.72rem;
  color: var(--text-muted);
}

.card__because,
.card__reason {
  margin: 0;
  font-size: 0.72rem;
  color: var(--text-muted);
  line-height: 1.45;
}

.card__empty {
  margin: 0;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.listing__head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 0.6rem;
}

.listing__title {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
  margin: 0;
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}

.listing__count {
  text-transform: none;
  letter-spacing: 0;
  font-weight: 400;
}

.filters {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
}

.filter {
  display: grid;
  gap: 0.15rem;
}

.filter__label {
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
}

.filter__control {
  font: inherit;
  font-size: 0.8rem;
  padding: 0.28rem 0.4rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-1);
  color: var(--text-primary);
}

.scroller {
  overflow-x: auto;
}

.table {
  width: 100%;
  min-width: 720px;
  border-collapse: collapse;
  font-size: 0.82rem;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.table th,
.table td {
  padding: 0.5rem 0.65rem;
  text-align: right;
  border-top: 1px solid var(--border);
  white-space: nowrap;
}

.table thead th {
  border-top: 0;
  color: var(--text-muted);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.035em;
  font-weight: 600;
}

.table th:first-child,
.table td:first-child,
.table td:nth-child(2),
.table td:last-child {
  text-align: left;
}

.table__name {
  font-weight: 600;
  white-space: normal;
}

.table__name a {
  color: var(--text-primary);
  text-decoration: none;
}

.table__name a:hover {
  color: var(--accent);
  text-decoration: underline;
}

.table__topic a {
  color: var(--text-secondary);
  font-size: 0.78rem;
  text-decoration: none;
}

.table__topic a:hover {
  color: var(--accent);
}

/* Component scores recede; the blended score and its confidence lead. */
.table__muted {
  color: var(--text-muted);
}

.table__lead {
  font-weight: 650;
}

.footnote {
  margin: 0.6rem 0 0;
  font-size: 0.72rem;
  color: var(--text-muted);
  line-height: 1.5;
}

.system {
  margin-top: 2.5rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--border);
}

.system__title {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
  margin: 0 0 0.6rem;
}

.system__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 0.75rem;
  margin: 0 0 0.75rem;
}

.system__grid dt {
  font-size: 0.7rem;
  color: var(--text-muted);
  margin-bottom: 0.1rem;
}

.system__grid dd {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}

.system__warn {
  color: var(--status-critical);
}

.system__link {
  font-size: 0.8rem;
  text-decoration: none;
}

.system__link:hover {
  text-decoration: underline;
}
</style>
