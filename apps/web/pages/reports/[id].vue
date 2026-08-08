<script setup lang="ts">
/**
 * One stored report.
 *
 * The Markdown is rendered client-side from the *stored* string, never rebuilt
 * from live data. A report that changed under the reader would be useless as a
 * record of what was known when a decision was made — which is the whole reason
 * the markdown column exists rather than being regenerated on view.
 *
 * The reproducibility check is offered as a button rather than run on load: it
 * rebuilds the whole period, which is real work, and the answer is only
 * interesting when someone is asking the question.
 */
const route = useRoute()
const config = useRuntimeConfig()
const apiBase = config.public.apiBaseUrl

interface ReportDetail {
  id: number
  title: string
  period_start: string
  period_end: string
  generated_at: string | null
  content_hash: string
  markdown: string
  inputs: {
    scoring_config_versions?: string[]
    builder_version?: string
    counts?: Record<string, number>
  } | null
}

const { data, error } = await useFetch<{ data: ReportDetail }>(
  `${apiBase}/reports/${route.params.id}`,
)

const report = computed(() => data.value?.data)

const verifying = ref(false)
const verification = ref<{ reproducible: boolean; rebuilt_hash: string } | null>(null)

async function verify() {
  verifying.value = true
  try {
    const response = await $fetch<{ data: { reproducible: boolean; rebuilt_hash: string } }>(
      `${apiBase}/reports/${route.params.id}/verify`,
    )
    verification.value = response.data
  } finally {
    verifying.value = false
  }
}

/**
 * Minimal Markdown → HTML for the subset the renderer emits: headings, tables,
 * lists, bold, italics, code, rules.
 *
 * Hand-rolled rather than pulled in as a dependency because the input is not
 * arbitrary Markdown — it is one known generator's output, and the set of
 * constructs is fixed and small. Everything is HTML-escaped first, so a stray
 * angle bracket in an interview note cannot become markup.
 */
function toHtml(markdown: string): string {
  const escape = (text: string) =>
    text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

  const inline = (text: string) =>
    escape(text)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\*([^*]+)\*/g, '<em>$1</em>')

  const lines = markdown.split('\n')
  const html: string[] = []
  let listOpen = false
  let tableRows: string[][] = []

  const closeList = () => {
    if (listOpen) {
      html.push('</ul>')
      listOpen = false
    }
  }

  const flushTable = () => {
    if (tableRows.length === 0) return
    const [header, ...body] = tableRows
    html.push('<div class="table-scroll"><table>')
    html.push('<thead><tr>' + header.map((c) => `<th>${inline(c)}</th>`).join('') + '</tr></thead>')
    html.push('<tbody>')
    for (const row of body) {
      html.push('<tr>' + row.map((c) => `<td>${inline(c)}</td>`).join('') + '</tr>')
    }
    html.push('</tbody></table></div>')
    tableRows = []
  }

  for (const line of lines) {
    const trimmed = line.trim()

    if (trimmed.startsWith('|')) {
      const cells = trimmed.slice(1, -1).split('|').map((c) => c.trim())
      // The |---|---| separator row carries no data.
      if (!cells.every((c) => /^:?-+:?$/.test(c))) {
        tableRows.push(cells)
      }
      continue
    }
    flushTable()

    if (trimmed === '') {
      closeList()
      continue
    }

    if (trimmed === '---') {
      closeList()
      html.push('<hr>')
      continue
    }

    const heading = trimmed.match(/^(#{1,4})\s+(.*)$/)
    if (heading) {
      closeList()
      const level = heading[1].length
      html.push(`<h${level}>${inline(heading[2])}</h${level}>`)
      continue
    }

    if (trimmed.startsWith('- ')) {
      if (!listOpen) {
        html.push('<ul>')
        listOpen = true
      }
      html.push(`<li>${inline(trimmed.slice(2))}</li>`)
      continue
    }

    const numbered = trimmed.match(/^(\d+)\.\s+(.*)$/)
    if (numbered) {
      if (!listOpen) {
        html.push('<ul>')
        listOpen = true
      }
      html.push(`<li>${inline(numbered[2])}</li>`)
      continue
    }

    closeList()
    html.push(`<p>${inline(trimmed)}</p>`)
  }

  flushTable()
  closeList()

  return html.join('\n')
}

const rendered = computed(() => (report.value ? toHtml(report.value.markdown) : ''))

function copyMarkdown() {
  if (report.value) navigator.clipboard?.writeText(report.value.markdown)
}
</script>

<template>
  <div>
    <p v-if="error" class="notice notice--error">No such report.</p>

    <template v-else-if="report">
      <nav class="crumbs">
        <NuxtLink to="/reports">Reports</NuxtLink>
      </nav>

      <header class="head">
        <h1>{{ report.title }}</h1>
        <p class="head__sub tabular">
          {{ report.period_start }} &rarr; {{ report.period_end }}
          <template v-if="report.generated_at">
            · generated {{ report.generated_at.slice(0, 16).replace('T', ' ') }}
          </template>
        </p>
      </header>

      <div class="toolbar">
        <button class="chip" :disabled="verifying" @click="verify">
          {{ verifying ? 'Rebuilding…' : 'Check reproducibility' }}
        </button>
        <button class="chip" @click="copyMarkdown">Copy Markdown</button>
        <span class="hash tabular">{{ report.content_hash.slice(0, 20) }}…</span>
      </div>

      <p
        v-if="verification"
        class="notice"
        :class="verification.reproducible ? 'notice--ok' : 'notice--warn'"
      >
        <template v-if="verification.reproducible">
          Rebuilding this period from stored data produced identical findings.
        </template>
        <template v-else>
          Findings differ from the stored report ({{ verification.rebuilt_hash.slice(0, 12) }}…).
          Either evidence for this period was recorded after the report was
          generated, or the builder is not deterministic.
        </template>
      </p>

      <!-- eslint-disable-next-line vue/no-v-html -- input is our own renderer's
           output, HTML-escaped in toHtml() before any markup is added. -->
      <article class="prose" v-html="rendered" />

      <footer v-if="report.inputs" class="inputs">
        <h2 class="inputs__title">Built from</h2>
        <dl class="inputs__grid tabular">
          <div v-for="(value, key) in report.inputs.counts ?? {}" :key="key">
            <dt>{{ String(key).replace(/_/g, ' ') }}</dt>
            <dd>{{ value }}</dd>
          </div>
        </dl>
        <p class="inputs__note">
          Scoring weights
          <strong>{{ (report.inputs.scoring_config_versions ?? []).map((v) => `v${v}`).join(', ') || 'none recorded' }}</strong>,
          builder <strong>{{ report.inputs.builder_version }}</strong>.
          The same window under different weights is genuinely a different report.
        </p>
      </footer>
    </template>
  </div>
</template>

<style scoped>
.crumbs {
  font-size: 0.78rem;
  color: var(--text-muted);
  margin-bottom: 0.75rem;
}

.crumbs a {
  text-decoration: none;
}

.head {
  margin-bottom: 1rem;
}

h1 {
  font-size: 1.4rem;
  margin: 0;
  letter-spacing: -0.015em;
}

.head__sub {
  margin: 0.25rem 0 0;
  color: var(--text-secondary);
  font-size: 0.8rem;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  margin-bottom: 1rem;
}

.chip {
  font: inherit;
  font-size: 0.78rem;
  padding: 0.3rem 0.65rem;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-1);
  color: var(--text-secondary);
  cursor: pointer;
}

.chip:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}

.chip:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.hash {
  font-size: 0.7rem;
  color: var(--text-muted);
}

.notice {
  margin: 0 0 1rem;
  padding: 0.7rem 0.9rem;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-1);
  font-size: 0.82rem;
  line-height: 1.5;
}

.notice--error {
  color: var(--status-critical);
}

.notice--ok {
  color: var(--status-good);
  background: var(--status-good-soft);
  border-color: var(--status-good-soft);
}

.notice--warn {
  color: var(--status-warning);
  background: var(--status-warning-soft);
  border-color: var(--status-warning-soft);
}

.prose {
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 1.25rem 1.4rem;
  font-size: 0.88rem;
  line-height: 1.65;
  color: var(--text-primary);
}

.prose :deep(h1) {
  font-size: 1.25rem;
  margin: 0 0 0.75rem;
  letter-spacing: -0.015em;
}

.prose :deep(h2) {
  font-size: 0.95rem;
  margin: 1.6rem 0 0.5rem;
  padding-top: 0.9rem;
  border-top: 1px solid var(--border);
}

.prose :deep(h2:first-of-type) {
  border-top: 0;
  padding-top: 0;
}

.prose :deep(p) {
  margin: 0 0 0.7rem;
  max-width: 76ch;
}

.prose :deep(ul) {
  margin: 0 0 0.8rem;
  padding-left: 1.2rem;
}

.prose :deep(li) {
  margin-bottom: 0.3rem;
  max-width: 76ch;
}

.prose :deep(hr) {
  border: 0;
  border-top: 1px solid var(--border);
  margin: 1.4rem 0;
}

.prose :deep(code) {
  font-size: 0.82em;
  background: var(--surface-2);
  padding: 0.1em 0.3em;
  border-radius: 3px;
}

/* Wide tables scroll inside their own container so the page never scrolls
   horizontally. */
.prose :deep(.table-scroll) {
  overflow-x: auto;
  margin: 0 0 0.9rem;
}

.prose :deep(table) {
  border-collapse: collapse;
  font-size: 0.8rem;
  font-variant-numeric: tabular-nums;
  min-width: 100%;
}

.prose :deep(th),
.prose :deep(td) {
  padding: 0.35rem 0.6rem;
  border-top: 1px solid var(--border);
  text-align: left;
  white-space: nowrap;
}

.prose :deep(thead th) {
  border-top: 0;
  color: var(--text-muted);
  font-size: 0.7rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.inputs {
  margin-top: 1.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border);
}

.inputs__title {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
  margin: 0 0 0.6rem;
}

.inputs__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 0.7rem;
  margin: 0 0 0.7rem;
}

.inputs__grid dt {
  font-size: 0.68rem;
  color: var(--text-muted);
}

.inputs__grid dd {
  margin: 0.1rem 0 0;
  font-size: 1rem;
  font-weight: 650;
}

.inputs__note {
  margin: 0;
  font-size: 0.74rem;
  color: var(--text-muted);
  line-height: 1.55;
  max-width: 74ch;
}
</style>
