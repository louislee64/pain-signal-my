<script setup lang="ts">
/**
 * §55's "report history".
 *
 * A history of *periods*, not of generation attempts — regenerating a week
 * replaces its row rather than appending, so a run of near-identical Tuesdays
 * never appears here.
 *
 * The list carries the content hash because that is what makes the milestone's
 * acceptance criterion checkable by eye: two reports of the same period with the
 * same hash contain the same findings.
 */
const config = useRuntimeConfig()
const apiBase = config.public.apiBaseUrl

interface ReportRow {
  id: number
  report_type: string
  title: string
  period_start: string
  period_end: string
  generated_at: string | null
  content_hash: string
  headline_count: number
  quiet_period: boolean
  build_recommendations: number
}

const { data, error, refresh } = await useFetch<{
  data: ReportRow[]
  meta: { count: number }
}>(`${apiBase}/reports`)

const rows = computed(() => data.value?.data ?? [])

const generating = ref(false)
const feedback = ref<{ tone: 'ok' | 'error'; message: string } | null>(null)

async function generate() {
  generating.value = true
  feedback.value = null
  try {
    // No `notify` flag: generating a report to look at it must not post it to a
    // team channel. The scheduled run is what notifies (§38).
    const response = await $fetch<{ data: { id: number; content_hash: string } }>(
      `${apiBase}/reports/generate`,
      { method: 'POST', body: {} },
    )
    feedback.value = {
      tone: 'ok',
      message: `Generated report #${response.data.id} (${response.data.content_hash.slice(0, 12)}…).`,
    }
    await refresh()
  } catch (e: any) {
    feedback.value = { tone: 'error', message: e?.data?.error ?? 'Could not generate a report.' }
  } finally {
    generating.value = false
  }
}
</script>

<template>
  <div>
    <header class="head">
      <div class="head__row">
        <h1>Reports</h1>
        <button class="button" :disabled="generating" @click="generate">
          {{ generating ? 'Generating…' : 'Generate for last week' }}
        </button>
      </div>
      <p class="head__sub">
        §39's weekly opportunity report, built from stored data. Generating the
        same period twice produces the same findings &mdash; the hash is how you
        check that.
      </p>
    </header>

    <p v-if="feedback" class="notice" :class="feedback.tone === 'error' ? 'notice--error' : 'notice--ok'">
      {{ feedback.message }}
    </p>

    <p v-if="error" class="notice notice--error">Could not reach the API at {{ apiBase }}.</p>

    <p v-else-if="rows.length === 0" class="notice">
      No reports yet. Generate one above, or run
      <code>php artisan reports:generate</code>.
    </p>

    <ul v-else class="reports">
      <li v-for="report in rows" :key="report.id" class="report">
        <NuxtLink :to="`/reports/${report.id}`" class="report__link">
          <div class="report__head">
            <span class="report__period tabular">
              {{ report.period_start }} &rarr; {{ report.period_end }}
            </span>
            <span v-if="report.quiet_period" class="report__quiet">quiet period</span>
          </div>
          <p class="report__meta tabular">
            {{ report.headline_count }} finding{{ report.headline_count === 1 ? '' : 's' }}
            ·
            {{ report.build_recommendations }} build recommendation{{ report.build_recommendations === 1 ? '' : 's' }}
            <template v-if="report.generated_at">
              · generated {{ report.generated_at.slice(0, 10) }}
            </template>
          </p>
          <p class="report__hash tabular">{{ report.content_hash.slice(0, 16) }}…</p>
        </NuxtLink>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.head {
  margin-bottom: 1.25rem;
}

.head__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

h1 {
  font-size: 1.4rem;
  margin: 0;
  letter-spacing: -0.015em;
}

.head__sub {
  margin: 0.3rem 0 0;
  color: var(--text-secondary);
  font-size: 0.85rem;
  max-width: 74ch;
  line-height: 1.55;
}

.button {
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  padding: 0.42rem 0.9rem;
  border: 1px solid var(--accent);
  border-radius: var(--radius-sm);
  background: var(--accent);
  color: #ffffff;
  cursor: pointer;
}

.button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.notice {
  margin: 0 0 1rem;
  padding: 0.7rem 0.9rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-1);
  color: var(--text-secondary);
  font-size: 0.82rem;
}

.notice--error {
  color: var(--status-critical);
}

.notice--ok {
  color: var(--status-good);
  background: var(--status-good-soft);
  border-color: var(--status-good-soft);
}

.reports {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.5rem;
}

.report__link {
  display: block;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.7rem 0.85rem;
  text-decoration: none;
  color: inherit;
}

.report__link:hover {
  border-color: var(--accent);
}

.report__head {
  display: flex;
  align-items: baseline;
  gap: 0.6rem;
  flex-wrap: wrap;
}

.report__period {
  font-size: 0.92rem;
  font-weight: 650;
}

.report__quiet {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
}

.report__meta {
  margin: 0.2rem 0 0;
  font-size: 0.76rem;
  color: var(--text-secondary);
}

.report__hash {
  margin: 0.15rem 0 0;
  font-size: 0.7rem;
  color: var(--text-muted);
}
</style>
