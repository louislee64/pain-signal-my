<script setup lang="ts">
/**
 * Milestone 3 acceptance: "Historical daily signals are stored and visible."
 *
 * Deliberately narrow. The real opportunity dashboard is Milestone 5
 * (PROJECT_SPEC.md §33/§55) and building it early would be implementing a
 * future phase; this page exists to make the stored trend series inspectable
 * and to prove the collect -> compute -> serve path end to end.
 */

const config = useRuntimeConfig()
const apiBase = config.public.apiBaseUrl

interface TrendRow {
  keyword: string
  keyword_group: string
  language: string | null
  source: string
  date: string
  interest: number
  rolling_7d: string | null
  growth_7d: string | null
  growth_score: string | null
  z_score: string | null
  collection_method: string
}

const { data: overview, error: overviewError } = await useFetch<{
  data: TrendRow[]
  meta: { interest_scale: string; tracked_keywords: number }
}>(`${apiBase}/trends`)

const rows = computed(() => overview.value?.data ?? [])
const selected = ref<string | null>(null)

// Default to the top-ranked (most-rising) keyword so the page answers
// "what is moving?" without requiring a click first.
watchEffect(() => {
  if (selected.value === null && rows.value.length > 0) {
    selected.value = rows.value[0].keyword
  }
})

const { data: series } = await useAsyncData(
  'trend-series',
  () => {
    if (!selected.value) return Promise.resolve(null)
    return $fetch<{
      data: { keyword: string; keyword_group: string; series: any[] }
      meta: { points: number }
    }>(`${apiBase}/trends/${encodeURIComponent(selected.value)}`)
  },
  { watch: [selected] },
)

const showTable = ref(false)

function formatRatio(value: string | null): string {
  if (value === null) return '—'
  return Number(value).toFixed(2)
}

function formatPercent(value: string | null): string {
  if (value === null) return '—'
  const n = Number(value)
  return `${n > 0 ? '+' : ''}${n.toFixed(1)}%`
}
</script>

<template>
  <div class="page">
    <header class="page__header">
      <h1>Search Trend Signals</h1>
      <p class="page__sub">
        Malaysian search interest for the tracked keyword clusters.
      </p>
    </header>

    <p v-if="overviewError" class="notice notice--error">
      Could not reach the API at {{ apiBase }}.
    </p>

    <p v-else-if="rows.length === 0" class="notice">
      No trend data stored yet. Collect some with
      <code>intelligence trends collect google_trends_csv --path &lt;export.csv&gt;</code>
      then <code>intelligence trends compute</code>.
    </p>

    <template v-else>
      <!--
        §16 is emphatic that Trends values are relative, not absolute volume.
        The caveat travels with the data from the API's meta block rather than
        being retyped here, so it cannot drift out of sync.
      -->
      <p class="notice notice--caveat">{{ overview?.meta.interest_scale }}</p>

      <section class="layout">
        <div class="ranked">
          <h2 class="ranked__title">
            Tracked keywords
            <span class="ranked__count">{{ rows.length }} with data</span>
          </h2>
          <ul class="ranked__list">
            <li v-for="row in rows" :key="row.keyword">
              <button
                class="ranked__item"
                :class="{ 'ranked__item--active': row.keyword === selected }"
                :aria-current="row.keyword === selected ? 'true' : undefined"
                @click="selected = row.keyword"
              >
                <span class="ranked__keyword">{{ row.keyword }}</span>
                <span class="ranked__meta">
                  {{ row.keyword_group }} · {{ row.language ?? 'n/a' }}
                </span>
                <span class="ranked__figures">
                  <span class="ranked__interest">{{ row.interest }}</span>
                  <span class="ranked__growth">vs baseline {{ formatRatio(row.growth_score) }}×</span>
                </span>
              </button>
            </li>
          </ul>
        </div>

        <div class="detail">
          <template v-if="series?.data">
            <h2 class="detail__title">{{ series.data.keyword }}</h2>

            <TrendChart :points="series.data.series" :keyword="series.data.keyword" />

            <button class="toggle" @click="showTable = !showTable">
              {{ showTable ? 'Hide' : 'Show' }} data table
            </button>

            <!-- Table view is the accessibility fallback for the chart, and the
                 place the derived metrics are readable as exact figures. -->
            <table v-if="showTable" class="table">
              <caption class="table__caption">
                Stored observations for {{ series.data.keyword }} ({{ series.meta.points }} points)
              </caption>
              <thead>
                <tr>
                  <th scope="col">Date</th>
                  <th scope="col">Interest</th>
                  <th scope="col">7d avg</th>
                  <th scope="col">30d avg</th>
                  <th scope="col">90d baseline</th>
                  <th scope="col">7d growth</th>
                  <th scope="col">z-score</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="point in series.data.series" :key="point.date">
                  <td>{{ point.date }}</td>
                  <td>{{ point.interest }}</td>
                  <td>{{ formatRatio(point.rolling_7d) }}</td>
                  <td>{{ formatRatio(point.rolling_30d) }}</td>
                  <td>{{ formatRatio(point.baseline_90d) }}</td>
                  <td>{{ formatPercent(point.growth_7d) }}</td>
                  <td>{{ formatRatio(point.z_score) }}</td>
                </tr>
              </tbody>
            </table>
          </template>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.page {
  /* Tokens now come from assets/css/tokens.css, shared with every other page.
     They lived here until Milestone 5 added four more pages that needed them. */
  padding-bottom: 1rem;
}

.page__header {
  margin: 0 0 1.25rem;
}

h1 {
  font-size: 1.4rem;
  margin: 0 0 0.3rem;
  letter-spacing: -0.015em;
}

.page__sub {
  margin: 0;
  color: var(--text-secondary);
  font-size: 0.9rem;
}

.notice {
  margin: 0 0 1.25rem;
  padding: 0.7rem 0.9rem;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-1);
  color: var(--text-secondary);
  font-size: 0.82rem;
  line-height: 1.5;
}

.notice--error {
  color: var(--status-critical);
}

.notice code {
  font-size: 0.78rem;
}

.layout {
  display: grid;
  grid-template-columns: minmax(220px, 300px) 1fr;
  gap: 1.5rem;
  align-items: start;
}

@media (max-width: 800px) {
  .layout {
    grid-template-columns: 1fr;
  }
}

.ranked__title {
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
  margin: 0 0 0.6rem;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 0.5rem;
}

.ranked__count {
  text-transform: none;
  letter-spacing: 0;
}

.ranked__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}

.ranked__item {
  width: 100%;
  text-align: left;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 0.6rem 0.7rem;
  cursor: pointer;
  font: inherit;
  color: var(--text-primary);
  display: grid;
  gap: 0.15rem;
}

.ranked__item:hover {
  border-color: var(--accent);
}

.ranked__item--active {
  border-color: var(--accent);
  box-shadow: inset 3px 0 0 var(--accent);
}

.ranked__keyword {
  font-weight: 600;
  font-size: 0.9rem;
}

.ranked__meta {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.ranked__figures {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-size: 0.75rem;
  color: var(--text-secondary);
  font-variant-numeric: tabular-nums;
}

.ranked__interest {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.detail__title {
  font-size: 1.05rem;
  margin: 0 0 0.75rem;
}

.toggle {
  margin-top: 0.9rem;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 0.4rem 0.75rem;
  font: inherit;
  font-size: 0.8rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.table {
  margin-top: 0.9rem;
  width: 100%;
  border-collapse: collapse;
  font-size: 0.8rem;
  font-variant-numeric: tabular-nums;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.table__caption {
  caption-side: top;
  text-align: left;
  padding: 0.5rem 0.6rem;
  color: var(--text-muted);
  font-size: 0.75rem;
}

.table th,
.table td {
  padding: 0.4rem 0.6rem;
  text-align: right;
  border-top: 1px solid var(--border);
}

.table th:first-child,
.table td:first-child {
  text-align: left;
}

.table th {
  color: var(--text-muted);
  font-weight: 600;
}
</style>
