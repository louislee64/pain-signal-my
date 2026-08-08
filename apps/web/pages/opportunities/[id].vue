<script setup lang="ts">
/**
 * §34's opportunity detail page — the "and why" half of Milestone 5's
 * acceptance criterion.
 *
 * Section order follows §34: problem, why it matters, evidence, trend,
 * geography, buyer, existing solutions, opportunity, monetization, validation,
 * recommendation. Sections whose data arrives in Milestone 6 (interviews,
 * commercial evidence, experiments) are rendered as declared-empty rather than
 * omitted — a missing section reads as "no interviews were done", which is a
 * claim about the work rather than about the schema.
 */
const route = useRoute()
const config = useRuntimeConfig()
const apiBase = config.public.apiBaseUrl

interface Example {
  id: number
  date: string
  source: string
  source_name: string | null
  source_reliability: number | null
  url: string | null
  title: string | null
  excerpt: string | null
  region: string | null
  severity: number | null
  urgency: number | null
  economic_impact: number | null
  frequency: string | null
  payer_type: string | null
  method: string
  extraction: Record<string, unknown> | null
}

interface Detail {
  id: number
  title: string
  topic: string | null
  topic_name: string | null
  topic_description: string | null
  status: string
  recommendation: string | null
  pain_score: string | null
  commercial_score: string | null
  opportunity_score: string | null
  confidence_score: string | null
  description: string | null
  problem_statement: string | null
  existing_workaround: string | null
  possible_solution: string | null
  monetization_model: string | null
  target_buyer: string | null
  score_components: Record<string, any> | null
  evidence: { signal_count: number; distinct_sources: number; examples: Example[] }
  geography: Record<string, number>
  trend: {
    series: { date: string; mentions: number; avg_severity: number | null }[]
    windows: { mentions_7d: number; mentions_30d: number; mentions_90d: number }
    search_interest_available: boolean
  }
  buyer_evidence: {
    suggested_buyer: string | null
    payer_types: Record<string, number>
    affected_roles: Record<string, number>
  }
}

const { data, error } = await useFetch<{
  data: Detail
  meta: {
    scoring_config_version: string | null
    scored_at: string | null
    sections_not_yet_available: Record<string, string>
  }
}>(`${apiBase}/opportunities/${route.params.id}`)

const detail = computed(() => data.value?.data)
const meta = computed(() => data.value?.meta)

const showAllExamples = ref(false)
const visibleExamples = computed(() => {
  const examples = detail.value?.evidence.examples ?? []
  return showAllExamples.value ? examples : examples.slice(0, 3)
})

function score(value: string | null | undefined): string | null {
  return value === null || value === undefined ? null : Number(value).toFixed(0)
}

function methodLabel(method: string): string {
  if (method.startsWith('llm_')) return 'model read the text'
  if (method.startsWith('rule_based')) return 'keyword match'
  return method
}
</script>

<template>
  <div>
    <p v-if="error" class="notice notice--error">
      Could not load this opportunity. It may not exist.
    </p>

    <template v-else-if="detail">
      <nav class="crumbs">
        <NuxtLink to="/">Overview</NuxtLink>
        <span aria-hidden="true">/</span>
        <NuxtLink v-if="detail.topic" :to="`/topics/${detail.topic}`">
          {{ detail.topic_name ?? detail.topic }}
        </NuxtLink>
      </nav>

      <header class="head">
        <div class="head__row">
          <h1>{{ detail.title }}</h1>
          <ScoreBadge :value="detail.recommendation" kind="recommendation" />
        </div>
        <p class="head__meta">
          Stage <strong>{{ detail.status.replace(/_/g, ' ') }}</strong>
          <template v-if="meta?.scored_at">
            · scored {{ meta.scored_at.slice(0, 10) }}
          </template>
          <template v-if="meta?.scoring_config_version">
            · weights v{{ meta.scoring_config_version }}
          </template>
        </p>
      </header>

      <section class="scores" aria-label="Scores">
        <ScoreBar label="Opportunity" :value="detail.opportunity_score" />
        <ScoreBar
          label="Confidence"
          :value="detail.confidence_score"
          hint="How much to believe the score beside it (§30)"
        />
        <ScoreBar label="Pain" :value="detail.pain_score" muted />
        <ScoreBar label="Commercial" :value="detail.commercial_score" muted />
      </section>

      <section class="panel">
        <h2 class="panel__title">Problem</h2>
        <p v-if="detail.problem_statement" class="prose">{{ detail.problem_statement }}</p>
        <p v-else-if="detail.topic_description" class="prose prose--muted">
          {{ detail.topic_description }}
          <span class="inline-note">
            (topic description — no problem statement written yet)
          </span>
        </p>
        <p v-else class="empty">
          No problem statement yet. §52 keeps this human-authored: the scoring
          engine never writes narrative fields.
        </p>
      </section>

      <section class="panel">
        <h2 class="panel__title">Why it matters</h2>
        <p v-if="detail.description" class="prose">{{ detail.description }}</p>
        <p v-else class="empty">
          Not written yet. The economic case is in the commercial score
          breakdown below in the meantime.
        </p>
      </section>

      <section class="panel">
        <h2 class="panel__title">
          Evidence
          <span class="panel__count">
            {{ detail.evidence.signal_count }} signals from
            {{ detail.evidence.distinct_sources }}
            {{ detail.evidence.distinct_sources === 1 ? 'source' : 'sources' }}
          </span>
        </h2>

        <p v-if="detail.evidence.examples.length === 0" class="empty">
          No signals recorded for this topic yet.
        </p>

        <template v-else>
          <!-- §31: independent corroboration is what separates weak evidence
               from strong, so the source count is stated before the examples. -->
          <ul class="examples">
            <li v-for="example in visibleExamples" :key="example.id" class="example">
              <div class="example__head">
                <span class="example__source">{{ example.source_name ?? example.source }}</span>
                <span class="example__date tabular">{{ String(example.date).slice(0, 10) }}</span>
                <span class="example__method">{{ methodLabel(example.method) }}</span>
              </div>
              <p v-if="example.excerpt" class="example__text">{{ example.excerpt }}</p>
              <div class="example__figures tabular">
                <span v-if="example.severity !== null">severity {{ example.severity }}</span>
                <span v-if="example.urgency !== null">urgency {{ example.urgency }}</span>
                <span v-if="example.economic_impact !== null">
                  economic impact {{ example.economic_impact }}
                </span>
                <span v-if="example.region">{{ example.region }}</span>
                <span v-if="example.frequency && example.frequency !== 'unknown'">
                  {{ example.frequency }}
                </span>
                <a v-if="example.url" :href="example.url" target="_blank" rel="noopener noreferrer">
                  source &rarr;
                </a>
              </div>
            </li>
          </ul>

          <button
            v-if="detail.evidence.examples.length > 3"
            class="toggle"
            @click="showAllExamples = !showAllExamples"
          >
            {{ showAllExamples ? 'Show fewer' : `Show all ${detail.evidence.examples.length} examples` }}
          </button>
        </template>
      </section>

      <section class="panel">
        <h2 class="panel__title">
          Trend
          <span class="panel__count tabular">
            {{ detail.trend.windows.mentions_7d }} in 7d ·
            {{ detail.trend.windows.mentions_30d }} in 30d ·
            {{ detail.trend.windows.mentions_90d }} in 90d
          </span>
        </h2>

        <ActivityChart v-if="detail.trend.series.length" :points="detail.trend.series" />
        <p v-else class="empty">No dated signals to plot.</p>

        <p v-if="detail.trend.search_interest_available" class="footnote">
          Search interest is tracked per keyword rather than per topic and is
          plotted separately &mdash;
          <NuxtLink to="/trends">search trends &rarr;</NuxtLink>
        </p>
      </section>

      <div class="split">
        <section class="panel">
          <h2 class="panel__title">Geography</h2>
          <DistributionBars
            :distribution="detail.geography"
            empty-message="No state recorded on any signal for this topic."
          />
        </section>

        <section class="panel">
          <h2 class="panel__title">Buyer</h2>
          <p class="buyer__suggested">
            Suggested economic buyer:
            <strong>{{ (detail.buyer_evidence.suggested_buyer ?? 'unknown').replace(/_/g, ' ') }}</strong>
          </p>
          <!-- §5: the payer is often not the sufferer. Both are shown, never
               collapsed — pointing the commercial model at the person with no
               budget is the failure this separation prevents. -->
          <h3 class="subhead">Who would pay</h3>
          <DistributionBars
            :distribution="detail.buyer_evidence.payer_types"
            empty-message="No payer type inferred from any signal."
          />
          <h3 class="subhead">Who suffers it</h3>
          <DistributionBars
            :distribution="detail.buyer_evidence.affected_roles"
            empty-message="No affected role extracted. Rule-based signals do not carry one; LLM extraction does."
          />
        </section>
      </div>

      <div class="split">
        <section class="panel">
          <h2 class="panel__title">Existing solutions</h2>
          <p v-if="detail.existing_workaround" class="prose">{{ detail.existing_workaround }}</p>
          <p v-else class="empty">Not recorded yet.</p>
        </section>

        <section class="panel">
          <h2 class="panel__title">Possible solution &amp; monetization</h2>
          <p v-if="detail.possible_solution" class="prose">{{ detail.possible_solution }}</p>
          <p v-else class="empty">Not recorded yet.</p>
          <p v-if="detail.monetization_model" class="prose">
            <strong>Charging model:</strong> {{ detail.monetization_model }}
          </p>
        </section>
      </div>

      <section class="panel">
        <h2 class="panel__title">Validation</h2>
        <ul class="deferred">
          <li v-for="(when, section) in meta?.sections_not_yet_available ?? {}" :key="section">
            <span class="deferred__name">{{ String(section).replace(/_/g, ' ') }}</span>
            <span class="deferred__when">{{ when }}</span>
          </li>
        </ul>
        <p class="footnote">
          Until these exist, the opportunity score is capped at 79: §29 stops
          inferred signals outranking actual paying customers.
        </p>
      </section>

      <section class="panel panel--wide">
        <h2 class="panel__title">Score breakdown</h2>
        <p class="panel__lede">
          Every dimension as stored at scoring time &mdash; raw input, its
          normalized 0&ndash;100 value, its weight, and what it contributed.
        </p>
        <ScoreBreakdown :components="detail.score_components" />
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

.crumbs a:hover {
  text-decoration: underline;
}

.head {
  margin-bottom: 1.5rem;
}

.head__row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  flex-wrap: wrap;
}

h1 {
  font-size: 1.4rem;
  margin: 0;
  letter-spacing: -0.015em;
}

.head__meta {
  margin: 0.3rem 0 0;
  font-size: 0.78rem;
  color: var(--text-muted);
}

.scores {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 1rem 1.5rem;
  padding: 1rem;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  margin-bottom: 1.75rem;
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

.panel__lede {
  margin: 0 0 0.75rem;
  font-size: 0.8rem;
  color: var(--text-secondary);
  line-height: 1.5;
}

.split {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.75rem;
}

.prose {
  margin: 0 0 0.5rem;
  font-size: 0.88rem;
  line-height: 1.6;
  color: var(--text-primary);
  max-width: 68ch;
}

.prose--muted {
  color: var(--text-secondary);
}

.inline-note {
  color: var(--text-muted);
  font-size: 0.78rem;
}

.empty {
  margin: 0;
  font-size: 0.8rem;
  color: var(--text-muted);
  line-height: 1.5;
  max-width: 68ch;
}

.examples {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.6rem;
}

.example {
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.7rem 0.8rem;
}

.example__head {
  display: flex;
  align-items: baseline;
  gap: 0.6rem;
  flex-wrap: wrap;
  margin-bottom: 0.35rem;
}

.example__source {
  font-size: 0.78rem;
  font-weight: 600;
}

.example__date,
.example__method {
  font-size: 0.72rem;
  color: var(--text-muted);
}

.example__text {
  margin: 0 0 0.4rem;
  font-size: 0.82rem;
  line-height: 1.55;
  color: var(--text-secondary);
}

.example__figures {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
  font-size: 0.72rem;
  color: var(--text-muted);
}

.toggle {
  margin-top: 0.6rem;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 0.35rem 0.7rem;
  font: inherit;
  font-size: 0.78rem;
  color: var(--text-secondary);
  cursor: pointer;
}

.toggle:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.subhead {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.035em;
  color: var(--text-muted);
  margin: 0.9rem 0 0.4rem;
}

.buyer__suggested {
  margin: 0 0 0.4rem;
  font-size: 0.85rem;
}

.deferred {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.3rem;
}

.deferred li {
  display: flex;
  gap: 0.6rem;
  align-items: baseline;
  font-size: 0.8rem;
  flex-wrap: wrap;
}

.deferred__name {
  font-weight: 600;
  text-transform: capitalize;
}

.deferred__when {
  color: var(--text-muted);
  font-size: 0.75rem;
}

.footnote {
  margin: 0.6rem 0 0;
  font-size: 0.74rem;
  color: var(--text-muted);
  line-height: 1.5;
  max-width: 68ch;
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
</style>
