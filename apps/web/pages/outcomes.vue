<script setup lang="ts">
/**
 * §58's outcome dataset and §57's feedback loop.
 *
 * The page that asks whether the system is any good. Everything else in this
 * dashboard reports what the system believes; this reports how often it was
 * right, and it is deliberately blunt about how little it can conclude from a
 * handful of outcomes.
 *
 * The sample-size banner leads. A reader who takes "payer_clarity is
 * over-weighted" from four data points and edits config/scoring.yaml has been
 * misled by this page, so the count comes first and the findings come after.
 */
const config = useRuntimeConfig()
const apiBase = config.public.apiBaseUrl

interface Sample {
  outcomes_recorded: number
  minimum_to_conclude: number
  sufficient: boolean
  note: string | null
}

interface Accuracy {
  score_threshold: number
  scored_high_and_worked: number
  scored_high_and_failed: number
  scored_low_and_failed: number
  scored_low_and_worked: number
  wasted_effort: number
  missed: number
}

interface Miscalibrated {
  opportunity_id: number
  title: string | null
  initial_score: number
  outcome: string
  reason: string | null
  buyer_interviews?: number
  paid_pilots?: number
  revenue?: number
  implicates?: string | null
}

interface DimensionSignal {
  mean_in_overestimated: number | null
  mean_in_underestimated: number | null
  support: number
  verdict: string | null
  note: string | null
}

interface Calibration {
  sample: Sample
  accuracy: Accuracy | null
  overestimated: Miscalibrated[]
  underestimated: Miscalibrated[]
  by_outcome: Record<string, { count: number; mean_initial_score: number | null; implicates: string | null }>
  dimension_signals: Record<string, DimensionSignal>
  revenue: {
    total: number
    currency: string
    entries: number
    revenue_generating_opportunities: number
    by_opportunity: { opportunity_id: number; title: string | null; total: number; entries: number; distinct_customers: number }[]
  }
  suggestions: { kind: string; support: number; text: string }[]
}

interface OutcomeRow {
  opportunity_id: number
  title: string | null
  initial_score: number | null
  outcome: string
  reason: string | null
  buyer_interviews: number
  confirmed_buyers: number
  paid_pilots: number
  customers: number
  revenue: number
  concluded_at: string | null
}

const { data: calibration, error, refresh: refreshCalibration } = await useFetch<{
  data: Calibration
  meta: { note: string }
}>(`${apiBase}/calibration`)

const { data: outcomes, refresh: refreshOutcomes } = await useFetch<{
  data: OutcomeRow[]
  meta: { count: number; outcomes: string[] }
}>(`${apiBase}/outcomes`)

const report = computed(() => calibration.value?.data)
const rows = computed(() => outcomes.value?.data ?? [])

const dimensionsWithVerdict = computed(() =>
  Object.entries(report.value?.dimension_signals ?? {})
    .filter(([, signal]) => signal.verdict !== null)
    .map(([name, signal]) => ({ name, ...signal })),
)

function money(value: number, currency = 'MYR'): string {
  return `${currency} ${value.toLocaleString('en-MY', { minimumFractionDigits: 2 })}`
}

function label(value: string): string {
  return value.replace(/_/g, ' ')
}

async function refreshAll() {
  await Promise.all([refreshCalibration(), refreshOutcomes()])
}
</script>

<template>
  <div>
    <header class="head">
      <h1>Outcomes &amp; calibration</h1>
      <p class="head__sub">
        §57's feedback loop: what happened when these opportunities met real
        businesses, and where the scoring model was wrong.
      </p>
    </header>

    <p v-if="error" class="notice notice--error">Could not reach the API at {{ apiBase }}.</p>

    <template v-else-if="report">
      <!-- Leads, deliberately. A reader who edits config/scoring.yaml on the
           strength of four data points has been misled by this page. -->
      <section
        class="sample"
        :class="report.sample.sufficient ? 'sample--ok' : 'sample--thin'"
      >
        <span class="sample__count tabular">{{ report.sample.outcomes_recorded }}</span>
        <div>
          <p class="sample__label">
            outcome{{ report.sample.outcomes_recorded === 1 ? '' : 's' }} recorded
            <template v-if="!report.sample.sufficient">
              · {{ report.sample.minimum_to_conclude }} needed before concluding
            </template>
          </p>
          <p v-if="report.sample.note" class="sample__note">{{ report.sample.note }}</p>
        </div>
      </section>

      <!-- §56's ultimate KPI. -->
      <section class="kpi">
        <div class="kpi__figure">
          <span class="kpi__label">Opportunity-generated revenue</span>
          <span class="kpi__value tabular">
            {{ money(report.revenue.total, report.revenue.currency) }}
          </span>
          <span class="kpi__meta">
            {{ report.revenue.entries }} entr{{ report.revenue.entries === 1 ? 'y' : 'ies' }}
            across {{ report.revenue.revenue_generating_opportunities }}
            opportunit{{ report.revenue.revenue_generating_opportunities === 1 ? 'y' : 'ies' }}
          </span>
        </div>
        <p class="kpi__question">
          §56: <em>“Did the intelligence system actually help create revenue?”</em>
        </p>
      </section>

      <section v-if="report.accuracy" class="panel">
        <h2 class="panel__title">
          Was the score right?
          <span class="panel__count">against §35's threshold of {{ report.accuracy.score_threshold }}</span>
        </h2>
        <div class="scroller">
          <table class="matrix tabular">
            <thead>
              <tr>
                <th scope="col" />
                <th scope="col">Worked</th>
                <th scope="col">Failed</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">Scored high</th>
                <td class="matrix__good">{{ report.accuracy.scored_high_and_worked }}</td>
                <td class="matrix__bad">{{ report.accuracy.scored_high_and_failed }}</td>
              </tr>
              <tr>
                <th scope="row">Scored low</th>
                <td class="matrix__bad">{{ report.accuracy.scored_low_and_worked }}</td>
                <td class="matrix__good">{{ report.accuracy.scored_low_and_failed }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <!-- Not averaged into one accuracy figure: these two errors cost
             different things. -->
        <p class="footnote">
          <strong>{{ report.accuracy.wasted_effort }}</strong> wasted effort
          (scored high, went nowhere) ·
          <strong>{{ report.accuracy.missed }}</strong> missed
          (scored low, would have worked). Different costs, so they are not
          averaged into one accuracy figure.
        </p>
      </section>

      <div class="split">
        <section class="panel">
          <h2 class="panel__title">Overestimated</h2>
          <p v-if="report.overestimated.length === 0" class="empty">
            Nothing highly scored has failed after real customer contact.
          </p>
          <ul v-else class="findings">
            <li v-for="row in report.overestimated" :key="row.opportunity_id" class="finding">
              <div class="finding__head">
                <NuxtLink :to="`/opportunities/${row.opportunity_id}`">{{ row.title }}</NuxtLink>
                <span class="finding__score tabular">{{ row.initial_score.toFixed(0) }}</span>
              </div>
              <p class="finding__meta">
                {{ row.buyer_interviews }} interviews · ended {{ label(row.outcome) }}
                <template v-if="row.implicates"> · implicates {{ label(row.implicates) }}</template>
              </p>
              <p v-if="row.reason" class="finding__reason">{{ row.reason }}</p>
            </li>
          </ul>
        </section>

        <section class="panel">
          <h2 class="panel__title">Underestimated</h2>
          <p v-if="report.underestimated.length === 0" class="empty">
            Nothing that produced money was scored below the threshold.
          </p>
          <ul v-else class="findings">
            <li v-for="row in report.underestimated" :key="row.opportunity_id" class="finding">
              <div class="finding__head">
                <NuxtLink :to="`/opportunities/${row.opportunity_id}`">{{ row.title }}</NuxtLink>
                <span class="finding__score tabular">{{ row.initial_score.toFixed(0) }}</span>
              </div>
              <p class="finding__meta">
                {{ row.paid_pilots }} paid pilot(s)
                <template v-if="row.revenue"> · {{ money(row.revenue) }}</template>
              </p>
              <p v-if="row.reason" class="finding__reason">{{ row.reason }}</p>
            </li>
          </ul>
        </section>
      </div>

      <section v-if="dimensionsWithVerdict.length" class="panel">
        <h2 class="panel__title">Dimensions that may be mis-weighted</h2>
        <div class="scroller">
          <table class="table tabular">
            <thead>
              <tr>
                <th scope="col">Dimension</th>
                <th scope="col">In failures</th>
                <th scope="col">In successes</th>
                <th scope="col">Examples</th>
                <th scope="col">Verdict</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="signal in dimensionsWithVerdict" :key="signal.name">
                <th scope="row">{{ label(signal.name) }}</th>
                <td>{{ signal.mean_in_overestimated ?? '—' }}</td>
                <td>{{ signal.mean_in_underestimated ?? '—' }}</td>
                <td>{{ signal.support }}</td>
                <td>
                  <ScoreBadge
                    :value="signal.verdict === 'over_weighted' ? 'failing' : 'degraded'"
                    kind="health"
                  />
                  {{ label(signal.verdict ?? '') }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel">
        <h2 class="panel__title">What this suggests</h2>
        <ul class="suggestions">
          <li v-for="(suggestion, index) in report.suggestions" :key="index" class="suggestion">
            <span class="suggestion__support tabular">n={{ suggestion.support }}</span>
            <span>{{ suggestion.text }}</span>
          </li>
        </ul>
        <p class="footnote">
          {{ calibration?.meta.note }}
        </p>
      </section>

      <section class="panel">
        <h2 class="panel__title">
          Recorded outcomes
          <span class="panel__count">{{ rows.length }}</span>
        </h2>
        <p v-if="rows.length === 0" class="empty">
          Nothing concluded yet. Record one with
          <code>POST /api/v1/opportunities/{id}/outcome</code> once you have taken
          an opportunity to a real business and found out.
        </p>
        <div v-else class="scroller">
          <table class="table tabular">
            <thead>
              <tr>
                <th scope="col">Opportunity</th>
                <th scope="col">Scored</th>
                <th scope="col">Outcome</th>
                <th scope="col">Interviews</th>
                <th scope="col">Pilots</th>
                <th scope="col">Revenue</th>
                <th scope="col">Concluded</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.opportunity_id">
                <th scope="row" class="table__name">
                  <NuxtLink :to="`/opportunities/${row.opportunity_id}`">{{ row.title }}</NuxtLink>
                  <span v-if="row.reason" class="table__reason">{{ row.reason }}</span>
                </th>
                <td>{{ row.initial_score === null ? '—' : row.initial_score.toFixed(0) }}</td>
                <td>{{ label(row.outcome) }}</td>
                <td>{{ row.buyer_interviews }}</td>
                <td>{{ row.paid_pilots }}</td>
                <td>{{ row.revenue ? money(row.revenue) : '—' }}</td>
                <td class="table__muted">{{ row.concluded_at }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
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

.notice {
  padding: 0.7rem 0.9rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-1);
  font-size: 0.82rem;
}

.notice--error {
  color: var(--status-critical);
}

.sample {
  display: flex;
  align-items: center;
  gap: 0.9rem;
  padding: 0.8rem 1rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 1.25rem;
}

.sample--thin {
  border-color: var(--status-warning-soft);
  background: var(--status-warning-soft);
}

.sample--ok {
  border-color: var(--status-good-soft);
  background: var(--status-good-soft);
}

.sample__count {
  font-size: 2rem;
  font-weight: 680;
  line-height: 1;
}

.sample--thin .sample__count {
  color: var(--status-warning);
}

.sample--ok .sample__count {
  color: var(--status-good);
}

.sample__label {
  margin: 0;
  font-size: 0.82rem;
  font-weight: 600;
}

.sample__note {
  margin: 0.2rem 0 0;
  font-size: 0.76rem;
  color: var(--text-secondary);
  line-height: 1.5;
  max-width: 70ch;
}

.kpi {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1.5rem;
  flex-wrap: wrap;
  padding: 1rem;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 1.75rem;
}

.kpi__figure {
  display: grid;
  gap: 0.15rem;
}

.kpi__label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.045em;
  color: var(--text-muted);
}

.kpi__value {
  font-size: 1.9rem;
  font-weight: 680;
  line-height: 1.1;
}

.kpi__meta {
  font-size: 0.74rem;
  color: var(--text-muted);
}

.kpi__question {
  margin: 0;
  font-size: 0.78rem;
  color: var(--text-secondary);
  max-width: 34ch;
}

.panel {
  margin-bottom: 1.75rem;
}

.panel__title {
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
  margin: 0 0 0.6rem;
  display: flex;
  align-items: baseline;
  gap: 0.6rem;
  flex-wrap: wrap;
}

.panel__count {
  text-transform: none;
  letter-spacing: 0;
  font-weight: 400;
  font-size: 0.75rem;
}

.split {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(290px, 1fr));
  gap: 1.75rem;
}

.empty {
  margin: 0;
  font-size: 0.8rem;
  color: var(--text-muted);
  line-height: 1.55;
}

.scroller {
  overflow-x: auto;
}

.matrix,
.table {
  border-collapse: collapse;
  font-size: 0.8rem;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.table {
  width: 100%;
  min-width: 640px;
}

.matrix th,
.matrix td,
.table th,
.table td {
  padding: 0.45rem 0.7rem;
  border-top: 1px solid var(--border);
  text-align: right;
}

.matrix th:first-child,
.matrix td:first-child,
.table th:first-child,
.table td:first-child {
  text-align: left;
}

.matrix thead th,
.table thead th {
  border-top: 0;
  color: var(--text-muted);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  font-weight: 600;
}

.matrix__good {
  color: var(--status-good);
  font-weight: 650;
}

.matrix__bad {
  color: var(--status-serious);
  font-weight: 650;
}

.table__name {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  font-weight: 600;
  white-space: normal;
  max-width: 30ch;
}

.table__name a {
  color: var(--text-primary);
  text-decoration: none;
}

.table__name a:hover {
  color: var(--accent);
}

.table__reason {
  font-size: 0.7rem;
  font-weight: 400;
  color: var(--text-muted);
  line-height: 1.4;
}

.table__muted {
  color: var(--text-muted);
}

.findings {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.5rem;
}

.finding {
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.65rem 0.8rem;
}

.finding__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.6rem;
}

.finding__head a {
  font-size: 0.88rem;
  font-weight: 600;
  text-decoration: none;
  color: var(--text-primary);
}

.finding__head a:hover {
  color: var(--accent);
}

.finding__score {
  font-size: 1.1rem;
  font-weight: 650;
  color: var(--text-muted);
}

.finding__meta {
  margin: 0.2rem 0 0;
  font-size: 0.74rem;
  color: var(--text-secondary);
}

.finding__reason {
  margin: 0.3rem 0 0;
  font-size: 0.78rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.suggestions {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.45rem;
}

.suggestion {
  display: flex;
  gap: 0.7rem;
  align-items: baseline;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.6rem 0.75rem;
  font-size: 0.82rem;
  line-height: 1.55;
  color: var(--text-secondary);
}

.suggestion__support {
  flex: none;
  font-size: 0.7rem;
  color: var(--text-muted);
  padding-top: 0.15rem;
}

.footnote {
  margin: 0.7rem 0 0;
  font-size: 0.74rem;
  color: var(--text-muted);
  line-height: 1.6;
  max-width: 76ch;
}
</style>
