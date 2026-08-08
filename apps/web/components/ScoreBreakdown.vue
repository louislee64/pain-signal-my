<script setup lang="ts">
/**
 * Milestone 4's acceptance criterion, rendered.
 *
 * `score_components` records every dimension's raw input, normalized value,
 * weight and contribution. Normalization makes the raw inputs unrecoverable
 * from the final number, so this table is the only place a reader can see *why*
 * a score is what it is — which is the whole point of storing it.
 *
 * Contributions are shown as bars because their relative size is the thing
 * being read: whether a score came mostly from one dimension or evenly from
 * six changes how much you trust it. The weight column stays visible so a small
 * contribution can be told apart from a small weight.
 */
interface Dimension {
  raw: unknown
  normalized: number | null
  weight: number
  contribution: number
}

interface ScoreBlock {
  score: number
  dimensions: Record<string, Dimension>
  notes: string[]
}

const props = defineProps<{
  components: Record<string, ScoreBlock | string | null> | null
}>()

const TITLES: Record<string, string> = {
  pain_score: 'Pain score (§26)',
  commercial_score: 'Commercial score (§27)',
  opportunity_score: 'Opportunity score (§29)',
  confidence_score: 'Confidence score (§30)',
}

// Fixed order, not object-key order: the two component scores read first, then
// the blend, then the confidence that qualifies it. Object order would follow
// whatever the engine happened to serialise.
const ORDER = ['pain_score', 'commercial_score', 'opportunity_score', 'confidence_score']

const blocks = computed(() => {
  const components = props.components
  if (!components) return []

  return ORDER
    .filter((key) => {
      const block = components[key]
      return block && typeof block === 'object' && 'dimensions' in block
    })
    .map((key) => {
      const block = components[key] as ScoreBlock
      const dimensions = Object.entries(block.dimensions ?? {})
      const maxContribution = Math.max(1, ...dimensions.map(([, d]) => Number(d.contribution) || 0))

      return {
        key,
        title: TITLES[key] ?? key,
        score: block.score,
        notes: block.notes ?? [],
        // Largest contribution first: the reader's question is "what drove
        // this", and alphabetical order answers a question nobody asked.
        dimensions: dimensions
          .sort(([, a], [, b]) => Number(b.contribution) - Number(a.contribution))
          .map(([name, d]) => ({
            name: name.replace(/_/g, ' '),
            raw: formatRaw(d.raw),
            normalized: d.normalized === null ? '—' : Number(d.normalized).toFixed(1),
            weight: Number(d.weight).toFixed(2),
            contribution: Number(d.contribution).toFixed(2),
            share: (Number(d.contribution) / maxContribution) * 100,
          })),
      }
    })
})

function formatRaw(raw: unknown): string {
  if (raw === null || raw === undefined) return '—'
  if (typeof raw === 'number') return Number.isInteger(raw) ? String(raw) : raw.toFixed(2)
  if (typeof raw === 'string') return raw
  if (typeof raw === 'boolean') return raw ? 'yes' : 'no'
  // Composite raw inputs (e.g. commercial_evidence's four counts) print as
  // key=value pairs rather than as JSON — the reader wants the numbers, not
  // the punctuation.
  if (typeof raw === 'object') {
    return Object.entries(raw as Record<string, unknown>)
      .map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`)
      .join(', ')
  }
  return String(raw)
}
</script>

<template>
  <div v-if="blocks.length === 0" class="empty">
    No stored breakdown. Run <code>intelligence score</code> to compute one.
  </div>

  <div v-else class="breakdown">
    <section v-for="block in blocks" :key="block.key" class="block">
      <header class="block__head">
        <h3 class="block__title">{{ block.title }}</h3>
        <span class="block__score tabular">{{ Number(block.score).toFixed(2) }}</span>
      </header>

      <!-- Notes explain every zero and every adjustment. Without them a reader
           cannot tell "no data" from "measured as zero". -->
      <ul v-if="block.notes.length" class="block__notes">
        <li v-for="note in block.notes" :key="note">{{ note }}</li>
      </ul>

      <div class="scroller">
        <table class="table tabular">
          <thead>
            <tr>
              <th scope="col">Dimension</th>
              <th scope="col">Raw input</th>
              <th scope="col">0&ndash;100</th>
              <th scope="col">Weight</th>
              <th scope="col">Contribution</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="dimension in block.dimensions" :key="dimension.name">
              <th scope="row">{{ dimension.name }}</th>
              <td class="table__raw">{{ dimension.raw }}</td>
              <td>{{ dimension.normalized }}</td>
              <td class="table__weight">{{ dimension.weight }}</td>
              <td>
                <div class="contribution">
                  <span class="contribution__value">{{ dimension.contribution }}</span>
                  <span class="contribution__track">
                    <span class="contribution__fill" :style="{ width: `${dimension.share}%` }" />
                  </span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.breakdown {
  display: grid;
  gap: 1.25rem;
}

.empty {
  color: var(--text-secondary);
  font-size: 0.85rem;
}

.block__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.4rem;
}

.block__title {
  font-size: 0.85rem;
  margin: 0;
  color: var(--text-primary);
}

.block__score {
  font-size: 1rem;
  font-weight: 650;
}

.block__notes {
  margin: 0 0 0.5rem;
  padding-left: 1.1rem;
  color: var(--text-muted);
  font-size: 0.75rem;
  line-height: 1.5;
}

/* Wide content scrolls inside its own container so the page body never
   scrolls horizontally. */
.scroller {
  overflow-x: auto;
}

.table {
  width: 100%;
  min-width: 560px;
  border-collapse: collapse;
  font-size: 0.78rem;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.table th,
.table td {
  padding: 0.4rem 0.6rem;
  text-align: right;
  border-top: 1px solid var(--border);
  white-space: nowrap;
}

.table thead th {
  border-top: 0;
  color: var(--text-muted);
  font-weight: 600;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.table th:first-child,
.table td:first-child {
  text-align: left;
}

.table tbody th {
  font-weight: 600;
  color: var(--text-primary);
}

.table__raw,
.table__weight {
  color: var(--text-secondary);
  white-space: normal;
}

.contribution {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0.5rem;
}

.contribution__value {
  min-width: 2.8rem;
  text-align: right;
}

.contribution__track {
  width: 72px;
  height: 6px;
  border-radius: 3px;
  background: var(--surface-2);
  overflow: hidden;
  flex: none;
}

.contribution__fill {
  display: block;
  height: 100%;
  border-radius: 0 3px 3px 0;
  background: var(--accent);
}
</style>
