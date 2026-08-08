<script setup lang="ts">
/**
 * Source health — the page that answers "can I trust today's numbers?".
 *
 * The failure this exists for is not the loud one. A collector that errors gets
 * noticed; a collector that succeeds and returns zero records raises nothing
 * anywhere, and every score that depended on it quietly drains away. So the
 * health column reports reasons, not a green tick, and a succeeded-but-empty run
 * is degraded rather than ok.
 */
const config = useRuntimeConfig()
const apiBase = config.public.apiBaseUrl

interface Health {
  status: string
  reasons: string[]
}

interface SourceRow {
  slug: string
  name: string
  source_type: string
  collector: string
  collection_method: string | null
  enabled: boolean
  terms_status: string | null
  personal_data_risk: string | null
  license: string | null
  reliability_score: number | null
  documents: number
  last_run: {
    status: string
    started_at: string | null
    received: number
    inserted: number
    updated: number
    rejected: number
    errors: number
  } | null
  health: Health
}

interface RunRow {
  id: number
  source: string | null
  status: string
  started_at: string | null
  duration_seconds: number | null
  received: number
  inserted: number
  updated: number
  rejected: number
  errors: number
}

const includeDisabled = ref(false)

const { data: sources, error } = await useAsyncData(
  'sources',
  () => $fetch<{ data: SourceRow[]; meta: { count: number; sources_are_configured_in: string } }>(
    `${apiBase}/sources${includeDisabled.value ? '?include_disabled=1' : ''}`,
  ),
  { watch: [includeDisabled] },
)

const { data: runs } = await useFetch<{ data: RunRow[] }>(`${apiBase}/ingestion-runs?limit=25`)

const rows = computed(() => sources.value?.data ?? [])

// Unhealthy first: the page's job is to surface problems, and alphabetical order
// buries the one row that matters under nine that don't.
const HEALTH_ORDER = ['failing', 'stale', 'degraded', 'never_run', 'ok', 'disabled']
const ordered = computed(() =>
  [...rows.value].sort(
    (a, b) =>
      HEALTH_ORDER.indexOf(a.health.status) - HEALTH_ORDER.indexOf(b.health.status) ||
      a.slug.localeCompare(b.slug),
  ),
)

const problems = computed(() => rows.value.filter((s) => s.health.status !== 'ok').length)

function timestamp(value: string | null): string {
  return value ? value.slice(0, 16).replace('T', ' ') : '—'
}
</script>

<template>
  <div>
    <header class="head">
      <h1>Source health</h1>
      <p class="head__sub">
        Configured in <code>{{ sources?.meta.sources_are_configured_in }}</code>.
        Every score above rests on these &mdash; a source that stops delivering
        drains the numbers that depended on it without raising an error anywhere.
      </p>
    </header>

    <p v-if="error" class="notice notice--error">Could not reach the API at {{ apiBase }}.</p>

    <template v-else>
      <div class="bar">
        <span class="bar__stat" :class="{ 'bar__stat--warn': problems > 0 }">
          {{ rows.length }} sources ·
          <template v-if="problems === 0">all healthy</template>
          <template v-else>{{ problems }} needing attention</template>
        </span>
        <label class="check">
          <input v-model="includeDisabled" type="checkbox" >
          Include disabled
        </label>
      </div>

      <ul class="sources">
        <li v-for="source in ordered" :key="source.slug" class="source">
          <div class="source__head">
            <div class="source__identity">
              <h2 class="source__name">{{ source.name }}</h2>
              <p class="source__slug tabular">
                {{ source.slug }} · {{ source.source_type }} · {{ source.collector }}
              </p>
            </div>
            <ScoreBadge :value="source.health.status" kind="health" />
          </div>

          <!-- All reasons, not the first one found: a source can be both stale
               and returning nothing, and reporting one hides the other. -->
          <ul v-if="source.health.reasons.length" class="reasons">
            <li v-for="reason in source.health.reasons" :key="reason">{{ reason }}</li>
          </ul>

          <dl class="facts tabular">
            <div>
              <dt>Documents</dt>
              <dd>{{ source.documents }}</dd>
            </div>
            <div>
              <dt>Last run</dt>
              <dd>{{ timestamp(source.last_run?.started_at ?? null) }}</dd>
            </div>
            <div>
              <dt>Received</dt>
              <dd>{{ source.last_run?.received ?? '—' }}</dd>
            </div>
            <div>
              <dt>Inserted</dt>
              <dd>{{ source.last_run?.inserted ?? '—' }}</dd>
            </div>
            <div>
              <dt>Rejected</dt>
              <dd :class="{ 'facts__warn': (source.last_run?.rejected ?? 0) > 0 }">
                {{ source.last_run?.rejected ?? '—' }}
              </dd>
            </div>
            <div>
              <dt>Reliability</dt>
              <dd>{{ source.reliability_score ?? '—' }}</dd>
            </div>
          </dl>

          <!-- §11/§42: whether the evidence is legally usable matters as much
               as whether it arrived, so it sits on the same row. -->
          <p class="compliance">
            terms <strong>{{ source.terms_status ?? 'unknown' }}</strong>
            · personal data risk <strong>{{ source.personal_data_risk ?? 'unknown' }}</strong>
            <template v-if="source.license"> · {{ source.license }}</template>
            <template v-if="source.collection_method"> · {{ source.collection_method }}</template>
          </p>
        </li>
      </ul>

      <section class="panel">
        <h2 class="panel__title">Recent ingestion runs</h2>
        <p v-if="(runs?.data.length ?? 0) === 0" class="empty">
          No runs recorded yet. Run
          <code>intelligence ingest &lt;source-slug&gt;</code>.
        </p>
        <div v-else class="scroller">
          <table class="table tabular">
            <thead>
              <tr>
                <th scope="col">Started</th>
                <th scope="col">Source</th>
                <th scope="col">Status</th>
                <th scope="col">Duration</th>
                <th scope="col">Received</th>
                <th scope="col">Inserted</th>
                <th scope="col">Updated</th>
                <th scope="col">Rejected</th>
                <th scope="col">Errors</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="run in runs?.data ?? []" :key="run.id">
                <td>{{ timestamp(run.started_at) }}</td>
                <td class="table__source">{{ run.source ?? '—' }}</td>
                <td>
                  <!-- The run's own status, not a health verdict. A run that
                       succeeded while receiving nothing is a succeeded run; the
                       source above is what calls that degraded. Showing "ok"
                       here would contradict the row directly above it. -->
                  <span class="table__status" :class="`table__status--${run.status}`">
                    {{ run.status }}
                  </span>
                </td>
                <td class="table__muted">{{ run.duration_seconds === null ? '—' : `${run.duration_seconds}s` }}</td>
                <td>{{ run.received }}</td>
                <td>{{ run.inserted }}</td>
                <td class="table__muted">{{ run.updated }}</td>
                <td :class="{ 'table__warn': run.rejected > 0 }">{{ run.rejected }}</td>
                <td :class="{ 'table__warn': run.errors > 0 }">{{ run.errors }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <p class="footnote">
        Runs are triggered from the Python service
        (<code>intelligence ingest &lt;slug&gt;</code>), not from this page.
        §36 lists a <code>POST /sources/{id}/run</code> endpoint; it is
        deliberately not implemented, because a dashboard button that fires a
        long-running collector hides both its duration and its failures.
        Scheduling is §38, Milestone 7.
      </p>
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
  max-width: 74ch;
  line-height: 1.55;
}

.bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-bottom: 0.7rem;
}

.bar__stat {
  font-size: 0.78rem;
  color: var(--text-muted);
}

.bar__stat--warn {
  color: var(--status-serious);
  font-weight: 600;
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

.sources {
  list-style: none;
  margin: 0 0 2rem;
  padding: 0;
  display: grid;
  gap: 0.7rem;
}

.source {
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.8rem 0.9rem;
}

.source__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.source__name {
  font-size: 0.95rem;
  margin: 0;
}

.source__slug {
  margin: 0.1rem 0 0;
  font-size: 0.72rem;
  color: var(--text-muted);
}

.reasons {
  margin: 0.55rem 0 0;
  padding-left: 1.1rem;
  font-size: 0.78rem;
  color: var(--status-serious);
  line-height: 1.5;
}

.facts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(90px, 1fr));
  gap: 0.6rem;
  margin: 0.75rem 0 0;
}

.facts dt {
  font-size: 0.68rem;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.facts dd {
  margin: 0.1rem 0 0;
  font-size: 0.88rem;
  font-weight: 600;
}

.facts__warn {
  color: var(--status-serious);
}

.compliance {
  margin: 0.7rem 0 0;
  padding-top: 0.55rem;
  border-top: 1px solid var(--border);
  font-size: 0.72rem;
  color: var(--text-muted);
}

.panel__title {
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
  margin: 0 0 0.6rem;
}

.empty {
  margin: 0;
  font-size: 0.8rem;
  color: var(--text-muted);
}

.scroller {
  overflow-x: auto;
}

.table {
  width: 100%;
  min-width: 760px;
  border-collapse: collapse;
  font-size: 0.78rem;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.table th,
.table td {
  padding: 0.42rem 0.6rem;
  text-align: right;
  border-top: 1px solid var(--border);
  white-space: nowrap;
}

.table thead th {
  border-top: 0;
  color: var(--text-muted);
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  font-weight: 600;
}

.table th:first-child,
.table td:first-child,
.table td:nth-child(2),
.table td:nth-child(3) {
  text-align: left;
}

.table__source {
  color: var(--text-secondary);
}

.table__status {
  font-size: 0.72rem;
  font-weight: 600;
}

.table__status--succeeded {
  color: var(--status-good);
}

.table__status--failed,
.table__status--partial {
  color: var(--status-critical);
}

.table__muted {
  color: var(--text-muted);
}

.table__warn {
  color: var(--status-serious);
  font-weight: 600;
}

.footnote {
  margin: 1.5rem 0 0;
  font-size: 0.74rem;
  color: var(--text-muted);
  line-height: 1.6;
  max-width: 74ch;
}
</style>
