<script setup lang="ts">
/**
 * Milestone 6's working page: where an opportunity moves from internet signal to
 * paid-pilot tracking.
 *
 * The gates lead, because the operator's question is "what do I need to go and
 * find out next", and a list of what has already been recorded does not answer
 * it. Every gate is shown whether satisfied or not, with the requirement
 * attached.
 *
 * Promotion is a deliberate act (§52). The button appears only when the evidence
 * supports it, and the override path is separate and labelled so a bypassed gate
 * can never be mistaken for a satisfied one.
 */
const route = useRoute()
const config = useRuntimeConfig()
const apiBase = config.public.apiBaseUrl
const id = route.params.id

interface Gate {
  satisfied: boolean
  requirement: string
  blocking_reason: string | null
}

interface StageMeta {
  status: string
  suggested_status: string
  suggestion_is_ahead: boolean
  stage_order: string[]
  stage_labels: Record<string, string>
  gates: Record<string, Gate>
  evidence: Record<string, number | boolean>
}

interface Interview {
  id: number
  company_ref: string | null
  industry: string | null
  company_size: string | null
  respondent_role: string | null
  problem_confirmed: boolean | null
  pilot_interest: boolean | null
  willingness_to_pay: string | null
  current_workaround: string | null
  notes: string | null
  interviewed_at: string
}

interface Evidence {
  id: number
  evidence_type: string
  strength: string
  value: string | null
  currency: string
  company_ref: string | null
  notes: string | null
  occurred_at: string
}

interface ExperimentRow {
  id: number
  hypothesis: string
  experiment_type: string
  success_metric: string
  status: string
  result: string | null
  succeeded: boolean | null
  started_at: string | null
  completed_at: string | null
}

interface Transition {
  id: number
  from_status: string | null
  to_status: string
  suggested_status_at_time: string | null
  note: string | null
  created_at: string
}

const { data, error, refresh } = await useFetch<{
  data: {
    opportunity_id: number
    title: string
    interviews: Interview[]
    commercial_evidence: Evidence[]
    experiments: ExperimentRow[]
    transitions: Transition[]
  }
  meta: StageMeta
}>(`${apiBase}/opportunities/${id}/validation`)

const meta = computed(() => data.value?.meta)
const record = computed(() => data.value?.data)

const feedback = ref<{ tone: 'ok' | 'error'; message: string } | null>(null)
const busy = ref(false)

const EVIDENCE_TYPES = [
  'customer_request',
  'interview',
  'pilot_interest',
  'proposal',
  'existing_spend',
  'purchase_order',
  'deposit',
  'paid_pilot',
  'repeat_customer',
]

const EXPERIMENT_TYPES = [
  'landing_page',
  'customer_interview',
  'cold_outreach',
  'manual_service',
  'paid_report',
  'paid_pilot',
  'prototype',
]

const today = () => new Date().toISOString().slice(0, 10)

const interviewForm = reactive({
  company_ref: '',
  industry: '',
  company_size: '',
  respondent_role: '',
  problem_confirmed: '',
  pilot_interest: '',
  current_workaround: '',
  willingness_to_pay: '',
  notes: '',
  interviewed_at: today(),
})

const evidenceForm = reactive({
  evidence_type: 'pilot_interest',
  strength: 'medium',
  company_ref: '',
  value: '',
  notes: '',
  occurred_at: today(),
})

const experimentForm = reactive({
  hypothesis: '',
  experiment_type: 'customer_interview',
  success_metric: '',
  status: 'planned',
  started_at: today(),
})

const narrativeForm = reactive({
  target_buyer: '',
  problem_statement: '',
})

const stageForm = reactive({
  status: '',
  note: '',
  override_gate: false,
})

watchEffect(() => {
  if (!stageForm.status && meta.value) {
    // Defaults to the suggestion when it is ahead: that is the move the operator
    // most likely came here to make.
    stageForm.status = meta.value.suggestion_is_ahead
      ? meta.value.suggested_status
      : meta.value.status
  }
})

/** Strips empty strings so the API sees absent fields rather than blanks. */
function clean(form: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(form)) {
    if (value === '' || value === null) continue
    if (value === 'true') out[key] = true
    else if (value === 'false') out[key] = false
    else out[key] = value
  }
  return out
}

async function post(path: string, body: Record<string, unknown>, successMessage: string) {
  busy.value = true
  feedback.value = null
  try {
    const response = await $fetch<{ meta?: { warnings?: string[] } }>(
      `${apiBase}/opportunities/${id}${path}`,
      { method: 'POST', body },
    )
    const warnings = response?.meta?.warnings ?? []
    feedback.value = {
      tone: 'ok',
      message: warnings.length ? `${successMessage} ${warnings.join(' ')}` : successMessage,
    }
    await refresh()
  } catch (e: any) {
    // Surface the API's own message: it names the gate or the field, which is
    // the whole value of the response.
    const payload = e?.data
    feedback.value = {
      tone: 'error',
      message: payload?.error
        ?? Object.values(payload?.errors ?? {}).flat().join(' ')
        ?? 'Request failed.',
    }
  } finally {
    busy.value = false
  }
}

async function submitInterview() {
  await post('/interviews', clean(interviewForm), 'Interview recorded.')
  Object.assign(interviewForm, {
    company_ref: '', industry: '', company_size: '', respondent_role: '',
    problem_confirmed: '', pilot_interest: '', current_workaround: '',
    willingness_to_pay: '', notes: '', interviewed_at: today(),
  })
}

async function submitEvidence() {
  await post('/evidence', clean(evidenceForm), 'Evidence recorded.')
  Object.assign(evidenceForm, {
    evidence_type: 'pilot_interest', strength: 'medium', company_ref: '',
    value: '', notes: '', occurred_at: today(),
  })
}

async function submitExperiment() {
  await post('/experiments', clean(experimentForm), 'Experiment recorded.')
  Object.assign(experimentForm, {
    hypothesis: '', experiment_type: 'customer_interview', success_metric: '',
    status: 'planned', started_at: today(),
  })
}

async function submitNarrative() {
  busy.value = true
  feedback.value = null
  try {
    await $fetch(`${apiBase}/opportunities/${id}`, {
      method: 'PATCH',
      body: clean(narrativeForm),
    })
    feedback.value = { tone: 'ok', message: 'Buyer hypothesis saved.' }
    await refresh()
  } catch (e: any) {
    feedback.value = {
      tone: 'error',
      message: e?.data?.error
        ?? Object.values(e?.data?.errors ?? {}).flat().join(' ')
        ?? 'Could not save.',
    }
  } finally {
    busy.value = false
  }
}

async function submitStage() {
  busy.value = true
  feedback.value = null
  try {
    const response = await $fetch<{ data: { gate_overridden: boolean } }>(
      `${apiBase}/opportunities/${id}/stage`,
      { method: 'PATCH', body: clean(stageForm) },
    )
    feedback.value = {
      tone: 'ok',
      message: response.data.gate_overridden
        ? `Moved to ${stageForm.status} with the gate overridden — recorded as an override.`
        : `Moved to ${stageForm.status}.`,
    }
    stageForm.note = ''
    stageForm.override_gate = false
    await refresh()
  } catch (e: any) {
    feedback.value = { tone: 'error', message: e?.data?.error ?? 'Could not change stage.' }
  } finally {
    busy.value = false
  }
}

const gateList = computed(() =>
  Object.entries(meta.value?.gates ?? {}).map(([stage, gate], index) => ({
    stage,
    label: meta.value?.stage_labels[stage] ?? stage,
    gateNumber: index + 1,
    ...gate,
  })),
)

const stageIsAdvance = computed(() => {
  const order = meta.value?.stage_order ?? []
  return order.indexOf(stageForm.status) > order.indexOf(meta.value?.status ?? '')
})

const targetGateBlocked = computed(() => {
  const gate = meta.value?.gates?.[stageForm.status]
  return stageIsAdvance.value && gate && !gate.satisfied
})

function money(value: string | null, currency: string): string {
  if (value === null) return '—'
  return `${currency} ${Number(value).toLocaleString('en-MY', { minimumFractionDigits: 2 })}`
}

function bool(value: boolean | null): string {
  if (value === null) return 'not established'
  return value ? 'yes' : 'no'
}
</script>

<template>
  <div>
    <p v-if="error" class="notice notice--error">Could not load this opportunity.</p>

    <template v-else-if="record && meta">
      <nav class="crumbs">
        <NuxtLink to="/">Overview</NuxtLink>
        <span aria-hidden="true">/</span>
        <NuxtLink :to="`/opportunities/${id}`">{{ record.title }}</NuxtLink>
      </nav>

      <header class="head">
        <h1>Commercial validation</h1>
        <p class="head__sub">
          §7's gates for <strong>{{ record.title }}</strong>. Recording evidence
          updates the suggestion; moving the stage is always your call.
        </p>
      </header>

      <FunnelProgress
        :status="meta.status"
        :suggested-status="meta.suggested_status"
        :order="meta.stage_order"
        :labels="meta.stage_labels"
      />

      <p v-if="feedback" class="notice" :class="feedback.tone === 'error' ? 'notice--error' : 'notice--ok'">
        {{ feedback.message }}
      </p>

      <!-- Gates first: the question is "what next", not "what already happened". -->
      <section class="panel">
        <h2 class="panel__title">Gates</h2>
        <ul class="gates">
          <li v-for="gate in gateList" :key="gate.stage" class="gate" :class="{ 'gate--met': gate.satisfied }">
            <div class="gate__head">
              <span class="gate__marker" :aria-hidden="true">{{ gate.satisfied ? '✓' : '·' }}</span>
              <span class="gate__label">{{ gate.label }}</span>
              <ScoreBadge :value="gate.satisfied ? 'ok' : 'never_run'" kind="health" />
            </div>
            <p class="gate__requirement">{{ gate.requirement }}</p>
          </li>
        </ul>
      </section>

      <!-- Gate 1's only route. Nothing else in the system writes target_buyer:
           the scoring engine deliberately never touches it, because inferring a
           buyer from signal payer_type would make the gate pass itself. -->
      <section class="panel">
        <h2 class="panel__title">
          Buyer hypothesis
          <span class="panel__count">§7 Gate 1</span>
        </h2>
        <form class="form form--inline" @submit.prevent="submitNarrative">
          <label class="field">
            <span class="field__label">Who would pay</span>
            <input v-model="narrativeForm.target_buyer" class="control" type="text" placeholder="business_owner" >
          </label>
          <label class="field field--grow">
            <span class="field__label">Problem statement</span>
            <input v-model="narrativeForm.problem_statement" class="control" type="text" placeholder="Month-end reconciliation costs three admin days" >
          </label>
          <button class="button" type="submit" :disabled="busy">Save</button>
        </form>
      </section>

      <section class="panel">
        <h2 class="panel__title">Change stage</h2>
        <form class="form form--inline" @submit.prevent="submitStage">
          <label class="field">
            <span class="field__label">Move to</span>
            <select v-model="stageForm.status" class="control">
              <option v-for="stage in meta.stage_order" :key="stage" :value="stage">
                {{ meta.stage_labels[stage] }}
              </option>
            </select>
          </label>

          <label class="field field--grow">
            <span class="field__label">Why (recorded on the transition)</span>
            <input v-model="stageForm.note" class="control" type="text" placeholder="Two independent confirmations, one proposal signed" >
          </label>

          <button class="button" type="submit" :disabled="busy || stageForm.status === meta.status">
            {{ busy ? 'Working…' : 'Move stage' }}
          </button>
        </form>

        <!-- The override is a separate, explicit act. A gate bypassed silently
             is indistinguishable from a gate satisfied. -->
        <div v-if="targetGateBlocked" class="override">
          <p class="override__text">
            {{ meta.gates[stageForm.status].blocking_reason }}.
          </p>
          <label class="check">
            <input v-model="stageForm.override_gate" type="checkbox" >
            The evidence exists outside this system — override and record it as an override
          </label>
        </div>
      </section>

      <div class="split">
        <section class="panel">
          <h2 class="panel__title">
            Record an interview
            <span class="panel__count">§7 Gate 2</span>
          </h2>
          <form class="form" @submit.prevent="submitInterview">
            <label class="field">
              <span class="field__label">
                Business reference
                <!-- The pseudonymity of this field is what keeps the whole table
                     free of personal data (§21). Said here, not just in a doc. -->
                <span class="field__hint">pseudonymous label, never a company name</span>
              </span>
              <input v-model="interviewForm.company_ref" class="control" type="text" placeholder="retailer-a" pattern="[A-Za-z0-9][A-Za-z0-9_-]*" >
            </label>

            <div class="row">
              <label class="field">
                <span class="field__label">Problem confirmed?</span>
                <select v-model="interviewForm.problem_confirmed" class="control">
                  <option value="">Not established</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
              <label class="field">
                <span class="field__label">Pilot interest?</span>
                <select v-model="interviewForm.pilot_interest" class="control">
                  <option value="">Not established</option>
                  <option value="true">Yes</option>
                  <option value="false">No</option>
                </select>
              </label>
            </div>

            <div class="row">
              <label class="field">
                <span class="field__label">Industry</span>
                <input v-model="interviewForm.industry" class="control" type="text" placeholder="retail" >
              </label>
              <label class="field">
                <span class="field__label">Company size</span>
                <input v-model="interviewForm.company_size" class="control" type="text" placeholder="5-20 staff" >
              </label>
            </div>

            <div class="row">
              <label class="field">
                <span class="field__label">Respondent role</span>
                <input v-model="interviewForm.respondent_role" class="control" type="text" placeholder="owner" >
              </label>
              <label class="field">
                <span class="field__label">Willingness to pay</span>
                <input v-model="interviewForm.willingness_to_pay" class="control" type="text" placeholder="RM200-500/mo" >
              </label>
            </div>

            <label class="field">
              <span class="field__label">Current workaround</span>
              <input v-model="interviewForm.current_workaround" class="control" type="text" placeholder="Excel plus manual checking" >
            </label>

            <label class="field">
              <span class="field__label">Notes</span>
              <textarea v-model="interviewForm.notes" class="control" rows="2" />
            </label>

            <label class="field">
              <span class="field__label">Interviewed on</span>
              <input v-model="interviewForm.interviewed_at" class="control" type="date" required >
            </label>

            <button class="button" type="submit" :disabled="busy">Record interview</button>
          </form>
        </section>

        <section class="panel">
          <h2 class="panel__title">
            Record commercial evidence
            <span class="panel__count">§7 Gates 3&ndash;5</span>
          </h2>
          <form class="form" @submit.prevent="submitEvidence">
            <label class="field">
              <span class="field__label">Type</span>
              <select v-model="evidenceForm.evidence_type" class="control">
                <option v-for="type in EVIDENCE_TYPES" :key="type" :value="type">
                  {{ type.replace(/_/g, ' ') }}
                </option>
              </select>
            </label>

            <div class="row">
              <label class="field">
                <span class="field__label">Strength</span>
                <select v-model="evidenceForm.strength" class="control">
                  <option value="weak">Weak</option>
                  <option value="medium">Medium</option>
                  <option value="strong">Strong</option>
                </select>
              </label>
              <label class="field">
                <span class="field__label">Value (MYR)</span>
                <input v-model="evidenceForm.value" class="control" type="number" min="0" step="0.01" placeholder="4500" >
              </label>
            </div>

            <label class="field">
              <span class="field__label">
                Business reference
                <span class="field__hint">needed for Gate 5 repeatability</span>
              </span>
              <input v-model="evidenceForm.company_ref" class="control" type="text" placeholder="retailer-a" pattern="[A-Za-z0-9][A-Za-z0-9_-]*" >
            </label>

            <label class="field">
              <span class="field__label">Notes</span>
              <textarea v-model="evidenceForm.notes" class="control" rows="2" />
            </label>

            <label class="field">
              <span class="field__label">Occurred on</span>
              <input v-model="evidenceForm.occurred_at" class="control" type="date" required >
            </label>

            <button class="button" type="submit" :disabled="busy">Record evidence</button>
          </form>
        </section>
      </div>

      <section class="panel">
        <h2 class="panel__title">Plan an experiment</h2>
        <form class="form" @submit.prevent="submitExperiment">
          <div class="row">
            <label class="field field--grow">
              <span class="field__label">
                Hypothesis
                <span class="field__hint">what you expect, written before you know</span>
              </span>
              <input v-model="experimentForm.hypothesis" class="control" type="text" required placeholder="SME owners will pay to automate month-end reconciliation" >
            </label>
            <label class="field">
              <span class="field__label">Type</span>
              <select v-model="experimentForm.experiment_type" class="control">
                <option v-for="type in EXPERIMENT_TYPES" :key="type" :value="type">
                  {{ type.replace(/_/g, ' ') }}
                </option>
              </select>
            </label>
          </div>

          <label class="field">
            <span class="field__label">
              Success metric
              <span class="field__hint">an experiment with no bar for success cannot fail</span>
            </span>
            <input v-model="experimentForm.success_metric" class="control" type="text" required placeholder="3 of 10 approached agree to a paid pilot" >
          </label>

          <div class="row">
            <label class="field">
              <span class="field__label">Status</span>
              <select v-model="experimentForm.status" class="control">
                <option value="planned">Planned</option>
                <option value="running">Running</option>
              </select>
            </label>
            <label class="field">
              <span class="field__label">Started on</span>
              <input v-model="experimentForm.started_at" class="control" type="date" >
            </label>
          </div>

          <button class="button" type="submit" :disabled="busy">Record experiment</button>
        </form>
      </section>

      <section class="panel">
        <h2 class="panel__title">
          Interviews
          <span class="panel__count">
            {{ record.interviews.length }} recorded ·
            {{ meta.evidence.independent_confirmations }} independent confirmations
          </span>
        </h2>
        <p v-if="record.interviews.length === 0" class="empty">Nothing recorded yet.</p>
        <ul v-else class="records">
          <li v-for="interview in record.interviews" :key="interview.id" class="record">
            <div class="record__head">
              <span class="record__ref">{{ interview.company_ref ?? 'unattributed' }}</span>
              <span class="record__date tabular">{{ interview.interviewed_at.slice(0, 10) }}</span>
              <span class="record__fact">problem confirmed: {{ bool(interview.problem_confirmed) }}</span>
              <span class="record__fact">pilot interest: {{ bool(interview.pilot_interest) }}</span>
            </div>
            <p class="record__meta">
              <template v-if="interview.industry">{{ interview.industry }} · </template>
              <template v-if="interview.company_size">{{ interview.company_size }} · </template>
              <template v-if="interview.respondent_role">{{ interview.respondent_role }}</template>
              <template v-if="interview.willingness_to_pay"> · pays {{ interview.willingness_to_pay }}</template>
            </p>
            <p v-if="interview.current_workaround" class="record__text">
              Workaround: {{ interview.current_workaround }}
            </p>
            <p v-if="interview.notes" class="record__text">{{ interview.notes }}</p>
          </li>
        </ul>
      </section>

      <section class="panel">
        <h2 class="panel__title">
          Commercial evidence
          <span class="panel__count">
            {{ record.commercial_evidence.length }} recorded ·
            {{ meta.evidence.paying_business_count }} paying
            {{ meta.evidence.paying_business_count === 1 ? 'business' : 'businesses' }}
          </span>
        </h2>
        <p v-if="record.commercial_evidence.length === 0" class="empty">
          Nothing recorded yet — the opportunity score stays capped at 79 (§29).
        </p>
        <div v-else class="scroller">
          <table class="table tabular">
            <thead>
              <tr>
                <th scope="col">Occurred</th>
                <th scope="col">Type</th>
                <th scope="col">Strength</th>
                <th scope="col">Business</th>
                <th scope="col">Value</th>
                <th scope="col">Notes</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in record.commercial_evidence" :key="row.id">
                <td>{{ row.occurred_at.slice(0, 10) }}</td>
                <td class="table__strong">{{ row.evidence_type.replace(/_/g, ' ') }}</td>
                <td class="table__muted">{{ row.strength }}</td>
                <td>{{ row.company_ref ?? '—' }}</td>
                <td>{{ money(row.value, row.currency) }}</td>
                <td class="table__notes">{{ row.notes ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="panel">
        <h2 class="panel__title">Experiments</h2>
        <p v-if="record.experiments.length === 0" class="empty">Nothing recorded yet.</p>
        <ul v-else class="records">
          <li v-for="experiment in record.experiments" :key="experiment.id" class="record">
            <div class="record__head">
              <span class="record__ref">{{ experiment.experiment_type.replace(/_/g, ' ') }}</span>
              <ScoreBadge
                :value="experiment.status === 'completed' ? (experiment.succeeded ? 'ok' : 'failing') : 'never_run'"
                kind="health"
              />
              <span class="record__fact">{{ experiment.status }}</span>
            </div>
            <p class="record__text"><strong>Hypothesis:</strong> {{ experiment.hypothesis }}</p>
            <p class="record__text"><strong>Success:</strong> {{ experiment.success_metric }}</p>
            <p v-if="experiment.result" class="record__text"><strong>Result:</strong> {{ experiment.result }}</p>
          </li>
        </ul>
      </section>

      <section class="panel">
        <h2 class="panel__title">Stage history</h2>
        <p v-if="record.transitions.length === 0" class="empty">No stage changes recorded.</p>
        <ol v-else class="history">
          <li v-for="transition in record.transitions" :key="transition.id" class="history__item">
            <span class="history__date tabular">{{ transition.created_at.slice(0, 10) }}</span>
            <span class="history__move">
              {{ meta.stage_labels[transition.from_status ?? ''] ?? transition.from_status ?? 'new' }}
              &rarr;
              <strong>{{ meta.stage_labels[transition.to_status] ?? transition.to_status }}</strong>
            </span>
            <span v-if="transition.suggested_status_at_time" class="history__suggested">
              engine suggested {{ meta.stage_labels[transition.suggested_status_at_time] ?? transition.suggested_status_at_time }}
            </span>
            <span v-if="transition.note" class="history__note">{{ transition.note }}</span>
          </li>
        </ol>
      </section>
    </template>
  </div>
</template>

<style scoped>
.crumbs {
  display: flex;
  gap: 0.4rem;
  font-size: 0.78rem;
  color: var(--text-muted);
  margin-bottom: 0.75rem;
}

.crumbs a {
  text-decoration: none;
}

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
  margin: 1rem 0 0;
  padding: 0.65rem 0.85rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-1);
  font-size: 0.82rem;
  line-height: 1.5;
}

.notice--error {
  color: var(--status-critical);
  border-color: var(--status-critical-soft);
  background: var(--status-critical-soft);
}

.notice--ok {
  color: var(--status-good);
  border-color: var(--status-good-soft);
  background: var(--status-good-soft);
}

.panel {
  margin-top: 1.75rem;
}

.panel__title {
  font-size: 0.78rem
  ;text-transform: uppercase;
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
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.75rem;
}

.gates {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.4rem;
}

.gate {
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.6rem 0.75rem;
}

.gate--met {
  border-color: var(--status-good-soft);
}

.gate__head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.gate__marker {
  width: 1.1rem;
  text-align: center;
  color: var(--text-muted);
  font-weight: 700;
}

.gate--met .gate__marker {
  color: var(--status-good);
}

.gate__label {
  font-size: 0.85rem;
  font-weight: 600;
}

.gate__requirement {
  margin: 0.25rem 0 0 1.6rem;
  font-size: 0.75rem;
  color: var(--text-muted);
  line-height: 1.5;
}

.form {
  display: grid;
  gap: 0.6rem;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.85rem;
}

.form--inline {
  grid-template-columns: auto 1fr auto;
  align-items: end;
}

@media (max-width: 700px) {
  .form--inline {
    grid-template-columns: 1fr;
  }
}

.row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 0.6rem;
}

.field {
  display: grid;
  gap: 0.2rem;
}

.field--grow {
  min-width: 0;
}

.field__label {
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.035em;
  color: var(--text-muted);
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}

.field__hint {
  text-transform: none;
  letter-spacing: 0;
  font-size: 0.68rem;
  color: var(--text-muted);
  font-style: italic;
}

.control {
  font: inherit;
  font-size: 0.82rem;
  padding: 0.35rem 0.45rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--plane);
  color: var(--text-primary);
  width: 100%;
}

.control:focus {
  outline: 2px solid var(--accent-soft);
  border-color: var(--accent);
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
  justify-self: start;
}

.button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.override {
  margin-top: 0.6rem;
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--status-warning-soft);
  background: var(--status-warning-soft);
  border-radius: var(--radius);
}

.override__text {
  margin: 0 0 0.4rem;
  font-size: 0.78rem;
  color: var(--status-warning);
}

.check {
  display: flex;
  align-items: flex-start;
  gap: 0.4rem;
  font-size: 0.78rem;
  color: var(--text-secondary);
  cursor: pointer;
  line-height: 1.45;
}

.empty {
  margin: 0;
  font-size: 0.8rem;
  color: var(--text-muted);
}

.records {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.5rem;
}

.record {
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.65rem 0.8rem;
}

.record__head {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 0.25rem;
}

.record__ref {
  font-size: 0.82rem;
  font-weight: 650;
}

.record__date,
.record__fact {
  font-size: 0.72rem;
  color: var(--text-muted);
}

.record__meta {
  margin: 0 0 0.25rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.record__text {
  margin: 0 0 0.2rem;
  font-size: 0.8rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.scroller {
  overflow-x: auto;
}

.table {
  width: 100%;
  min-width: 620px;
  border-collapse: collapse;
  font-size: 0.78rem;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.table th,
.table td {
  padding: 0.42rem 0.6rem;
  text-align: left;
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

.table__strong {
  font-weight: 600;
}

.table__muted {
  color: var(--text-muted);
}

.table__notes {
  white-space: normal;
  color: var(--text-secondary);
  max-width: 24ch;
}

.history {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.35rem;
}

.history__item {
  display: flex;
  gap: 0.7rem;
  flex-wrap: wrap;
  align-items: baseline;
  font-size: 0.8rem;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 0.45rem 0.65rem;
}

.history__date {
  color: var(--text-muted);
  font-size: 0.74rem;
}

.history__suggested,
.history__note {
  font-size: 0.74rem;
  color: var(--text-muted);
}
</style>
