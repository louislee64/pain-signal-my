<script setup lang="ts">
/**
 * One topic: what has been observed about it, and how.
 *
 * This page is deliberately about the *evidence*, not the score — the score
 * lives on the opportunity page and this one links to it. Separating them keeps
 * "what did the sources say" answerable without having to trust the weights.
 */
const route = useRoute()
const config = useRuntimeConfig()
const apiBase = config.public.apiBaseUrl

interface Signal {
  id: number
  date: string
  source: string
  url: string | null
  title: string | null
  excerpt: string | null
  region: string | null
  severity: number | null
  method: string
}

interface TopicDetail {
  slug: string
  name: string
  description: string | null
  parent: { slug: string; name: string } | null
  children: { slug: string; name: string }[]
  opportunity: {
    id: number
    opportunity_score: string | null
    pain_score: string | null
    commercial_score: string | null
    confidence_score: string | null
    recommendation: string | null
    status: string
  } | null
  activity: {
    signal_count: number
    series: { date: string; mentions: number; avg_severity: number | null; avg_urgency: number | null }[]
  }
  geography: Record<string, number>
  methods: Record<string, number>
  recent_signals: Signal[]
}

const { data, error } = await useFetch<{
  data: TopicDetail
  meta: { scores_are_explainable_at: string | null; scoring_note: string | null }
}>(`${apiBase}/topics/${route.params.slug}`)

const topic = computed(() => data.value?.data)
const showTable = ref(false)

function score(value: string | null | undefined): string {
  return value === null || value === undefined ? '—' : Number(value).toFixed(0)
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
      No such topic. Check <code>config/topics.yaml</code> for the slug.
    </p>

    <template v-else-if="topic">
      <nav class="crumbs">
        <NuxtLink to="/topics">Topics</NuxtLink>
        <template v-if="topic.parent">
          <span aria-hidden="true">/</span>
          <NuxtLink :to="`/topics/${topic.parent.slug}`">{{ topic.parent.name }}</NuxtLink>
        </template>
      </nav>

      <header class="head">
        <h1>{{ topic.name }}</h1>
        <p v-if="topic.description" class="head__sub">{{ topic.description }}</p>
        <p class="head__slug tabular">{{ topic.slug }}</p>
      </header>

      <section v-if="topic.opportunity" class="scorecard">
        <div class="scorecard__scores">
          <ScoreBar label="Opportunity" :value="topic.opportunity.opportunity_score" />
          <ScoreBar label="Confidence" :value="topic.opportunity.confidence_score" />
          <ScoreBar label="Pain" :value="topic.opportunity.pain_score" muted />
          <ScoreBar label="Commercial" :value="topic.opportunity.commercial_score" muted />
        </div>
        <div class="scorecard__foot">
          <ScoreBadge :value="topic.opportunity.recommendation" kind="recommendation" />
          <NuxtLink :to="`/opportunities/${topic.opportunity.id}`" class="scorecard__link">
            Full breakdown and evidence &rarr;
          </NuxtLink>
        </div>
      </section>

      <p v-else class="notice">
        {{ data?.meta.scoring_note }}
      </p>

      <section v-if="topic.children.length" class="panel">
        <h2 class="panel__title">Subtopics</h2>
        <ul class="chips">
          <li v-for="child in topic.children" :key="child.slug">
            <NuxtLink :to="`/topics/${child.slug}`" class="chip">{{ child.name }}</NuxtLink>
          </li>
        </ul>
      </section>

      <section class="panel">
        <h2 class="panel__title">
          Activity
          <span class="panel__count">{{ topic.activity.signal_count }} signals</span>
        </h2>

        <ActivityChart v-if="topic.activity.series.length" :points="topic.activity.series" />
        <p v-else class="empty">
          No signals for this topic yet. Either the sources are not discussing it,
          or the keywords in <code>config/topics.yaml</code> do not match how they
          talk about it.
        </p>

        <template v-if="topic.activity.series.length">
          <button class="toggle" @click="showTable = !showTable">
            {{ showTable ? 'Hide' : 'Show' }} data table
          </button>

          <!-- The table is the chart's accessibility fallback and the place the
               severity/urgency averages are readable as exact figures. -->
          <div v-if="showTable" class="scroller">
            <table class="table tabular">
              <caption class="table__caption">Daily signal counts for {{ topic.name }}</caption>
              <thead>
                <tr>
                  <th scope="col">Date</th>
                  <th scope="col">Mentions</th>
                  <th scope="col">Avg severity</th>
                  <th scope="col">Avg urgency</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="point in topic.activity.series" :key="point.date">
                  <td>{{ point.date }}</td>
                  <td>{{ point.mentions }}</td>
                  <td>{{ point.avg_severity ?? '—' }}</td>
                  <td>{{ point.avg_urgency ?? '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </template>
      </section>

      <div class="split">
        <section class="panel">
          <h2 class="panel__title">Geography</h2>
          <DistributionBars
            :distribution="topic.geography"
            empty-message="No state recorded on any signal for this topic."
          />
        </section>

        <section class="panel">
          <h2 class="panel__title">How these signals were produced</h2>
          <!-- §31: a keyword match and a model reading the text are different
               grades of evidence. A topic resting entirely on keyword matches
               should be read differently from one a model confirmed. -->
          <DistributionBars
            :distribution="topic.methods"
            empty-message="No signals to attribute."
          />
        </section>
      </div>

      <section v-if="topic.recent_signals.length" class="panel">
        <h2 class="panel__title">Recent signals</h2>
        <ul class="signals">
          <li v-for="signal in topic.recent_signals" :key="signal.id" class="signal">
            <div class="signal__head">
              <span class="signal__source">{{ signal.source }}</span>
              <span class="signal__date tabular">{{ String(signal.date).slice(0, 10) }}</span>
              <span class="signal__method">{{ methodLabel(signal.method) }}</span>
              <span v-if="signal.region" class="signal__region">{{ signal.region }}</span>
              <span v-if="signal.severity !== null" class="signal__severity tabular">
                severity {{ signal.severity }}
              </span>
            </div>
            <p v-if="signal.excerpt" class="signal__text">{{ signal.excerpt }}</p>
            <a v-if="signal.url" :href="signal.url" target="_blank" rel="noopener noreferrer" class="signal__link">
              source &rarr;
            </a>
          </li>
        </ul>
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

h1 {
  font-size: 1.4rem;
  margin: 0 0 0.3rem;
  letter-spacing: -0.015em;
}

.head__sub {
  margin: 0 0 0.25rem;
  color: var(--text-secondary);
  font-size: 0.85rem;
  max-width: 70ch;
  line-height: 1.55;
}

.head__slug {
  margin: 0;
  font-size: 0.72rem;
  color: var(--text-muted);
}

.scorecard {
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem;
  margin-bottom: 1.75rem;
}

.scorecard__scores {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 1rem 1.5rem;
}

.scorecard__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
  margin-top: 0.9rem;
  padding-top: 0.75rem;
  border-top: 1px solid var(--border);
}

.scorecard__link {
  font-size: 0.8rem;
  text-decoration: none;
}

.scorecard__link:hover {
  text-decoration: underline;
}

.notice {
  padding: 0.75rem 0.9rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-1);
  color: var(--text-secondary);
  font-size: 0.82rem;
  line-height: 1.5;
  margin-bottom: 1.75rem;
}

.notice--error {
  color: var(--status-critical);
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
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 1.75rem;
}

.empty {
  margin: 0;
  font-size: 0.8rem;
  color: var(--text-muted);
  line-height: 1.55;
  max-width: 68ch;
}

.chips {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  gap: 0.35rem;
  flex-wrap: wrap;
}

.chip {
  display: inline-block;
  font-size: 0.78rem;
  padding: 0.25rem 0.55rem;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 999px;
  text-decoration: none;
  color: var(--text-secondary);
}

.chip:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.toggle {
  margin-top: 0.7rem;
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

.scroller {
  overflow-x: auto;
  margin-top: 0.7rem;
}

.table {
  width: 100%;
  min-width: 420px;
  border-collapse: collapse;
  font-size: 0.78rem;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.table__caption {
  caption-side: top;
  text-align: left;
  padding: 0.5rem 0.6rem;
  color: var(--text-muted);
  font-size: 0.72rem;
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

.table thead th {
  color: var(--text-muted);
  font-weight: 600;
  font-size: 0.7rem;
  text-transform: uppercase;
}

.signals {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.5rem;
}

.signal {
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.65rem 0.75rem;
}

.signal__head {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
  align-items: baseline;
  margin-bottom: 0.3rem;
}

.signal__source {
  font-size: 0.78rem;
  font-weight: 600;
}

.signal__date,
.signal__method,
.signal__region,
.signal__severity {
  font-size: 0.72rem;
  color: var(--text-muted);
}

.signal__text {
  margin: 0 0 0.3rem;
  font-size: 0.82rem;
  line-height: 1.55;
  color: var(--text-secondary);
}

.signal__link {
  font-size: 0.72rem;
  text-decoration: none;
}

.signal__link:hover {
  text-decoration: underline;
}
</style>
