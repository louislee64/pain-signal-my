<script setup lang="ts">
/**
 * The configured taxonomy with its observed activity.
 *
 * Topics with zero signals are shown, not filtered out. A topic the sources
 * never mention is a real finding — either collection has a gap or the problem
 * does not exist here — and hiding it hides both possibilities.
 */
const config = useRuntimeConfig()
const apiBase = config.public.apiBaseUrl

interface TopicRow {
  slug: string
  name: string
  description: string | null
  parent: string | null
  signal_count: number
  last_seen: string | null
  opportunity_id: number | null
  opportunity_score: string | null
  confidence_score: string | null
  recommendation: string | null
}

const { data, error } = await useFetch<{
  data: TopicRow[]
  meta: { count: number; topics_are_configured_in: string }
}>(`${apiBase}/topics`)

const onlyActive = ref(false)

const rows = computed(() => {
  const all = data.value?.data ?? []
  const filtered = onlyActive.value ? all.filter((t) => t.signal_count > 0) : all
  // Most-evidenced first, then alphabetical. The list's job is "where is the
  // activity", and slug order answers a question nobody asked.
  return [...filtered].sort((a, b) => b.signal_count - a.signal_count || a.slug.localeCompare(b.slug))
})

const silent = computed(() => (data.value?.data ?? []).filter((t) => t.signal_count === 0).length)

function score(value: string | null): string {
  return value === null ? '—' : Number(value).toFixed(0)
}
</script>

<template>
  <div>
    <header class="head">
      <h1>Topics</h1>
      <p class="head__sub">
        The taxonomy from <code>{{ data?.meta.topics_are_configured_in }}</code>,
        with what the sources have actually said about each.
      </p>
    </header>

    <p v-if="error" class="notice notice--error">Could not reach the API at {{ apiBase }}.</p>

    <template v-else>
      <div class="bar">
        <span class="bar__stat">
          {{ data?.meta.count }} enabled ·
          <template v-if="silent > 0">{{ silent }} with no signals yet</template>
          <template v-else>all have signals</template>
        </span>
        <label class="check">
          <input v-model="onlyActive" type="checkbox" >
          Only topics with signals
        </label>
      </div>

      <div class="scroller">
        <table class="table tabular">
          <thead>
            <tr>
              <th scope="col">Topic</th>
              <th scope="col">Signals</th>
              <th scope="col">Last seen</th>
              <th scope="col">Opportunity</th>
              <th scope="col">Confidence</th>
              <th scope="col">Recommendation</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.slug" :class="{ 'row--silent': row.signal_count === 0 }">
              <th scope="row" class="table__name">
                <NuxtLink :to="`/topics/${row.slug}`">{{ row.name }}</NuxtLink>
                <span v-if="row.parent" class="table__parent">in {{ row.parent }}</span>
              </th>
              <td>{{ row.signal_count }}</td>
              <td class="table__muted">{{ row.last_seen ? String(row.last_seen).slice(0, 10) : '—' }}</td>
              <td class="table__lead">
                <NuxtLink v-if="row.opportunity_id" :to="`/opportunities/${row.opportunity_id}`">
                  {{ score(row.opportunity_score) }}
                </NuxtLink>
                <span v-else>—</span>
              </td>
              <td>{{ score(row.confidence_score) }}</td>
              <td>
                <ScoreBadge v-if="row.recommendation" :value="row.recommendation" kind="recommendation" />
                <span v-else class="table__muted">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.head {
  margin-bottom: 1.25rem;
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

.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 0.6rem;
}

.bar__stat {
  font-size: 0.78rem;
  color: var(--text-muted);
}

.check {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.8rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.notice {
  padding: 0.75rem 0.9rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-1);
  font-size: 0.82rem;
}

.notice--error {
  color: var(--status-critical);
}

.scroller {
  overflow-x: auto;
}

.table {
  width: 100%;
  min-width: 680px;
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
.table td:last-child {
  text-align: left;
}

.table__name {
  font-weight: 600;
  white-space: normal;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.table__name a {
  color: var(--text-primary);
  text-decoration: none;
}

.table__name a:hover {
  color: var(--accent);
  text-decoration: underline;
}

.table__parent {
  font-size: 0.7rem;
  font-weight: 400;
  color: var(--text-muted);
}

.table__muted {
  color: var(--text-muted);
}

.table__lead {
  font-weight: 650;
}

.table__lead a {
  text-decoration: none;
}

/* A silent topic is recessive but present — the reader should still be able to
   see the taxonomy covers it. */
.row--silent .table__name a,
.row--silent td {
  color: var(--text-muted);
}
</style>
