<script setup lang="ts">
/**
 * Interest-over-time line chart for one keyword.
 *
 * Two series on ONE axis, which is correct rather than a compromise: raw
 * interest and its 30-day rolling average are the same 0-100 relative scale
 * (PROJECT_SPEC.md §16), so they share a y-axis honestly. The domain is fixed
 * at 0-100 rather than fitted to the data — Google Trends values are already
 * normalised to their own peak, and auto-fitting would silently magnify noise
 * in a flat series into what looks like a dramatic climb.
 *
 * The smoothing line is the 30-day average, not the 7-day one, because the
 * windows are calendar ranges: on a weekly series (what Google's longer date
 * ranges return) a 7-day window holds exactly one observation, so rolling_7d
 * equals the raw value and the two lines would sit exactly on top of each
 * other. rolling_30d spans ~4 weekly points or 30 daily ones, so it actually
 * smooths at either granularity. Both figures remain visible in the table view.
 */

interface SeriesPoint {
  date: string
  interest: number
  rolling_30d: string | number | null
}

const props = defineProps<{
  points: SeriesPoint[]
  keyword: string
}>()

const WIDTH = 820
const HEIGHT = 300
const PAD = { top: 16, right: 20, bottom: 34, left: 40 }

const plotWidth = WIDTH - PAD.left - PAD.right
const plotHeight = HEIGHT - PAD.top - PAD.bottom

const hoverIndex = ref<number | null>(null)

const parsed = computed(() =>
  props.points.map((p) => ({
    date: p.date,
    time: new Date(p.date).getTime(),
    interest: p.interest,
    rolling: p.rolling_30d === null ? null : Number(p.rolling_30d),
  })),
)

const timeExtent = computed(() => {
  const times = parsed.value.map((p) => p.time)
  return { min: Math.min(...times), max: Math.max(...times) }
})

// x is scaled by actual date, not by array index, so a gap in collection shows
// as a gap rather than being silently compressed into an even cadence.
function xFor(time: number): number {
  const { min, max } = timeExtent.value
  if (max === min) return PAD.left + plotWidth / 2
  return PAD.left + ((time - min) / (max - min)) * plotWidth
}

function yFor(value: number): number {
  return PAD.top + plotHeight - (value / 100) * plotHeight
}

const coords = computed(() =>
  parsed.value.map((p) => ({
    ...p,
    x: xFor(p.time),
    yInterest: yFor(p.interest),
    yRolling: p.rolling === null ? null : yFor(p.rolling),
  })),
)

function pathFrom(key: 'yInterest' | 'yRolling'): string {
  const segments: string[] = []
  let started = false
  for (const c of coords.value) {
    const y = c[key]
    if (y === null) {
      started = false
      continue
    }
    segments.push(`${started ? 'L' : 'M'}${c.x.toFixed(2)} ${y.toFixed(2)}`)
    started = true
  }
  return segments.join(' ')
}

const interestPath = computed(() => pathFrom('yInterest'))
const rollingPath = computed(() => pathFrom('yRolling'))

const gridValues = [0, 25, 50, 75, 100]

// Label the ends plus a midpoint rather than every point — a tick per
// observation would collide and add no information.
const xLabels = computed(() => {
  const c = coords.value
  if (c.length === 0) return []
  if (c.length <= 2) return c.map((p) => ({ x: p.x, label: p.date }))
  return [c[0], c[Math.floor(c.length / 2)], c[c.length - 1]].map((p) => ({
    x: p.x,
    label: p.date,
  }))
})

const hovered = computed(() =>
  hoverIndex.value === null ? null : coords.value[hoverIndex.value] ?? null,
)

function onPointerMove(event: PointerEvent) {
  const svg = event.currentTarget as SVGSVGElement
  const rect = svg.getBoundingClientRect()
  // Map client px back into viewBox units so hit-testing stays correct at any
  // rendered width.
  const x = ((event.clientX - rect.left) / rect.width) * WIDTH

  let nearest = 0
  let best = Infinity
  coords.value.forEach((c, i) => {
    const distance = Math.abs(c.x - x)
    if (distance < best) {
      best = distance
      nearest = i
    }
  })
  hoverIndex.value = nearest
}

const tooltipX = computed(() => {
  if (!hovered.value) return 0
  // Flip the tooltip to the left of the crosshair near the right edge so it
  // never overflows the plot.
  return hovered.value.x > WIDTH - 170 ? hovered.value.x - 158 : hovered.value.x + 10
})
</script>

<template>
  <figure class="chart">
    <svg
      :viewBox="`0 0 ${WIDTH} ${HEIGHT}`"
      class="chart__svg"
      role="img"
      :aria-label="`Relative search interest over time for ${keyword}. Full values are listed in the table below.`"
      @pointermove="onPointerMove"
      @pointerleave="hoverIndex = null"
    >
      <!-- Recessive grid: hairlines behind the data, never competing with it. -->
      <g class="chart__grid">
        <line
          v-for="value in gridValues"
          :key="`grid-${value}`"
          :x1="PAD.left"
          :x2="WIDTH - PAD.right"
          :y1="yFor(value)"
          :y2="yFor(value)"
        />
      </g>

      <g class="chart__axis-text">
        <text
          v-for="value in gridValues"
          :key="`ylab-${value}`"
          :x="PAD.left - 8"
          :y="yFor(value) + 4"
          text-anchor="end"
        >
          {{ value }}
        </text>
        <text
          v-for="label in xLabels"
          :key="`xlab-${label.label}`"
          :x="label.x"
          :y="HEIGHT - 12"
          text-anchor="middle"
        >
          {{ label.label }}
        </text>
      </g>

      <line
        class="chart__baseline"
        :x1="PAD.left"
        :x2="WIDTH - PAD.right"
        :y1="yFor(0)"
        :y2="yFor(0)"
      />

      <path v-if="rollingPath" class="chart__line chart__line--rolling" :d="rollingPath" />
      <path v-if="interestPath" class="chart__line chart__line--interest" :d="interestPath" />

      <g v-if="hovered">
        <line
          class="chart__crosshair"
          :x1="hovered.x"
          :x2="hovered.x"
          :y1="PAD.top"
          :y2="PAD.top + plotHeight"
        />
        <!-- 2px surface ring keeps the marker legible where the two lines cross. -->
        <circle
          class="chart__marker chart__marker--interest"
          :cx="hovered.x"
          :cy="hovered.yInterest"
          r="5"
        />
        <circle
          v-if="hovered.yRolling !== null"
          class="chart__marker chart__marker--rolling"
          :cx="hovered.x"
          :cy="hovered.yRolling"
          r="5"
        />

        <g :transform="`translate(${tooltipX}, ${PAD.top + 6})`">
          <rect class="chart__tooltip" width="148" height="64" rx="6" />
          <text class="chart__tooltip-date" x="10" y="20">{{ hovered.date }}</text>
          <text class="chart__tooltip-row" x="10" y="38">
            Interest: {{ hovered.interest }}
          </text>
          <text class="chart__tooltip-row" x="10" y="54">
            30-day avg: {{ hovered.rolling === null ? '—' : hovered.rolling.toFixed(1) }}
          </text>
        </g>
      </g>
    </svg>

    <figcaption class="chart__legend">
      <span class="chart__key">
        <span class="chart__swatch chart__swatch--interest" aria-hidden="true" />
        Interest
      </span>
      <span class="chart__key">
        <span class="chart__swatch chart__swatch--rolling" aria-hidden="true" />
        30-day rolling average
      </span>
    </figcaption>
  </figure>
</template>

<style scoped>
/*
 * Palette from the validated reference instance. Both series slots pass every
 * gate in light and dark (worst-pair CVD ΔE 24.7 light / 26.8 dark against a
 * >=8 target). Dark values are separately-chosen steps for the dark surface,
 * declared under BOTH the OS media query and the explicit theme stamp so a
 * viewer's toggle wins either way.
 */
.chart {
  color-scheme: light;
  --surface-1: #fcfcfb;
  --text-secondary: #52514e;
  --text-muted: #898781;
  --gridline: #e1e0d9;
  --baseline: #c3c2b7;
  --border: rgba(11, 11, 11, 0.1);
  --series-interest: #2a78d6;
  --series-rolling: #eb6834;

  margin: 0;
}

@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme='light'])) .chart {
    color-scheme: dark;
    --surface-1: #1a1a19;
    --text-secondary: #c3c2b7;
    --text-muted: #898781;
    --gridline: #2c2c2a;
    --baseline: #383835;
    --border: rgba(255, 255, 255, 0.1);
    --series-interest: #3987e5;
    --series-rolling: #d95926;
  }
}

:root[data-theme='dark'] .chart {
  color-scheme: dark;
  --surface-1: #1a1a19;
  --text-secondary: #c3c2b7;
  --text-muted: #898781;
  --gridline: #2c2c2a;
  --baseline: #383835;
  --border: rgba(255, 255, 255, 0.1);
  --series-interest: #3987e5;
  --series-rolling: #d95926;
}

.chart__svg {
  width: 100%;
  height: auto;
  max-width: 820px;
  display: block;
  background: var(--surface-1);
  border: 1px solid var(--border);
  border-radius: 8px;
  touch-action: none;
}

.chart__grid line {
  stroke: var(--gridline);
  stroke-width: 1;
}

.chart__baseline {
  stroke: var(--baseline);
  stroke-width: 1;
}

.chart__axis-text text {
  fill: var(--text-muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.chart__line {
  fill: none;
  stroke-width: 2;
  stroke-linejoin: round;
  stroke-linecap: round;
}

.chart__line--interest {
  stroke: var(--series-interest);
}

.chart__line--rolling {
  stroke: var(--series-rolling);
}

.chart__crosshair {
  stroke: var(--baseline);
  stroke-width: 1;
  stroke-dasharray: 3 3;
}

.chart__marker {
  stroke: var(--surface-1);
  stroke-width: 2;
}

.chart__marker--interest {
  fill: var(--series-interest);
}

.chart__marker--rolling {
  fill: var(--series-rolling);
}

.chart__tooltip {
  fill: var(--surface-1);
  stroke: var(--border);
}

/* Tooltip text wears ink tokens, never a series color. */
.chart__tooltip-date {
  fill: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.chart__tooltip-row {
  fill: var(--text-secondary);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.chart__legend {
  display: flex;
  gap: 1.25rem;
  margin-top: 0.6rem;
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.chart__key {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.chart__swatch {
  width: 14px;
  height: 3px;
  border-radius: 2px;
  display: inline-block;
}

.chart__swatch--interest {
  background: var(--series-interest);
}

.chart__swatch--rolling {
  background: var(--series-rolling);
}
</style>
