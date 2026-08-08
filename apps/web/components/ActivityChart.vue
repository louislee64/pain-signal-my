<script setup lang="ts">
/**
 * Mentions per day for one topic, with average severity on hover.
 *
 * One series, one axis. Severity is deliberately NOT plotted as a second line:
 * mentions are a count and severity is a 0–100 index, so putting them on one
 * y-axis would be meaningless and giving them separate axes would be worse — a
 * dual-axis chart lets any two series be made to look correlated. Severity
 * appears in the tooltip and in the table view instead.
 *
 * Bars rather than a line because the data is a count per discrete day: a line
 * implies a continuous quantity was sampled, and interpolates across days that
 * genuinely had zero mentions.
 */
interface Point {
  date: string
  mentions: number
  avg_severity: number | null
}

const props = defineProps<{ points: Point[] }>()

const WIDTH = 820
const HEIGHT = 220
const PAD = { top: 14, right: 16, bottom: 30, left: 36 }

const plotWidth = WIDTH - PAD.left - PAD.right
const plotHeight = HEIGHT - PAD.top - PAD.bottom

const hoverIndex = ref<number | null>(null)

const parsed = computed(() =>
  props.points.map((p) => ({
    ...p,
    time: new Date(p.date).getTime(),
  })),
)

const maxMentions = computed(() => Math.max(1, ...parsed.value.map((p) => p.mentions)))

const timeExtent = computed(() => {
  const times = parsed.value.map((p) => p.time)
  return { min: Math.min(...times), max: Math.max(...times) }
})

// Scaled by date, not by index, so a collection gap reads as a gap rather than
// being compressed into an even cadence.
function xFor(time: number): number {
  const { min, max } = timeExtent.value
  if (max === min) return PAD.left + plotWidth / 2
  return PAD.left + ((time - min) / (max - min)) * plotWidth
}

function yFor(mentions: number): number {
  return PAD.top + plotHeight - (mentions / maxMentions.value) * plotHeight
}

const barWidth = computed(() => {
  if (parsed.value.length <= 1) return 18
  // Leave a 2px surface gap between adjacent bars so they read as separate
  // marks rather than one continuous block.
  const span = plotWidth / parsed.value.length
  return Math.max(2, Math.min(20, span - 2))
})

const bars = computed(() =>
  parsed.value.map((point, index) => ({
    ...point,
    index,
    x: xFor(point.time) - barWidth.value / 2,
    y: yFor(point.mentions),
    height: Math.max(1, PAD.top + plotHeight - yFor(point.mentions)),
  })),
)

const yTicks = computed(() => {
  const max = maxMentions.value
  const step = Math.max(1, Math.ceil(max / 4))
  const ticks: number[] = []
  for (let v = 0; v <= max; v += step) ticks.push(v)
  return ticks
})

const xLabels = computed(() => {
  const points = parsed.value
  if (points.length === 0) return []
  // First, middle and last only — a label per bar collides at any real density.
  const indices = points.length <= 3
    ? points.map((_, i) => i)
    : [0, Math.floor(points.length / 2), points.length - 1]
  return indices.map((i) => ({ x: xFor(points[i].time), label: shortDate(points[i].date) }))
})

const hovered = computed(() => (hoverIndex.value === null ? null : bars.value[hoverIndex.value] ?? null))

function shortDate(date: string): string {
  return new Date(date).toLocaleDateString('en-MY', { day: 'numeric', month: 'short' })
}
</script>

<template>
  <figure class="chart">
    <div class="chart__scroller">
      <svg
        :viewBox="`0 0 ${WIDTH} ${HEIGHT}`"
        class="chart__svg"
        role="img"
        :aria-label="`Mentions per day, ${points.length} days`"
        @mouseleave="hoverIndex = null"
      >
        <!-- Recessive grid: present enough to read a value against, never
             competing with the data. -->
        <g class="grid">
          <line
            v-for="tick in yTicks"
            :key="`grid-${tick}`"
            :x1="PAD.left"
            :x2="WIDTH - PAD.right"
            :y1="yFor(tick)"
            :y2="yFor(tick)"
          />
        </g>

        <g class="axis">
          <text
            v-for="tick in yTicks"
            :key="`y-${tick}`"
            :x="PAD.left - 8"
            :y="yFor(tick) + 3.5"
            text-anchor="end"
          >{{ tick }}</text>
          <text
            v-for="label in xLabels"
            :key="`x-${label.label}`"
            :x="label.x"
            :y="HEIGHT - 10"
            text-anchor="middle"
          >{{ label.label }}</text>
        </g>

        <g>
          <rect
            v-for="bar in bars"
            :key="bar.date"
            :x="bar.x"
            :y="bar.y"
            :width="barWidth"
            :height="bar.height"
            rx="2"
            class="bar"
            :class="{ 'bar--active': hoverIndex === bar.index }"
          />
        </g>

        <!-- Hit targets are full-height and wider than the marks: a 3px bar is
             not something anyone can reliably point at. -->
        <g>
          <rect
            v-for="bar in bars"
            :key="`hit-${bar.date}`"
            :x="bar.x - 3"
            :y="PAD.top"
            :width="barWidth + 6"
            :height="plotHeight"
            fill="transparent"
            @mouseenter="hoverIndex = bar.index"
          />
        </g>

        <g v-if="hovered">
          <line
            :x1="hovered.x + barWidth / 2"
            :x2="hovered.x + barWidth / 2"
            :y1="PAD.top"
            :y2="PAD.top + plotHeight"
            class="crosshair"
          />
        </g>
      </svg>
    </div>

    <figcaption v-if="hovered" class="tooltip tabular">
      <strong>{{ shortDate(hovered.date) }}</strong>
      · {{ hovered.mentions }} {{ hovered.mentions === 1 ? 'mention' : 'mentions' }}
      <template v-if="hovered.avg_severity !== null">
        · avg severity {{ hovered.avg_severity }}
      </template>
    </figcaption>
    <figcaption v-else class="tooltip tooltip--idle">
      Mentions per day. Hover a bar for its average severity.
    </figcaption>
  </figure>
</template>

<style scoped>
.chart {
  margin: 0;
}

.chart__scroller {
  overflow-x: auto;
}

.chart__svg {
  width: 100%;
  min-width: 420px;
  height: auto;
  display: block;
}

.grid line {
  stroke: var(--border);
  stroke-width: 1;
}

.axis text {
  fill: var(--text-muted);
  font-size: 10px;
  font-family: system-ui, sans-serif;
}

.bar {
  fill: var(--accent);
  opacity: 0.72;
}

.bar--active {
  opacity: 1;
}

.crosshair {
  stroke: var(--border-strong);
  stroke-width: 1;
  stroke-dasharray: 3 3;
}

.tooltip {
  margin-top: 0.35rem;
  font-size: 0.75rem;
  color: var(--text-secondary);
  min-height: 1.1rem;
}

.tooltip--idle {
  color: var(--text-muted);
}
</style>
