<script setup lang="ts">
/**
 * One 0–100 score as a labelled bar.
 *
 * Four of these sit side by side on the detail page — pain, commercial,
 * opportunity, confidence. They are four separate single-value bars rather than
 * a four-series chart, which is why they need no categorical palette: each is
 * directly labelled with its own name and number, so nothing is identified by
 * colour.
 *
 * The bar is a magnitude encoding, so it uses one hue at one step. `muted`
 * recedes it for the two component scores, keeping the eye on the blended
 * opportunity score and its confidence.
 */
const props = withDefaults(defineProps<{
  label: string
  value: string | number | null
  muted?: boolean
  hint?: string
}>(), { muted: false })

const numeric = computed(() => (props.value === null ? null : Number(props.value)))
const percent = computed(() => (numeric.value === null ? 0 : Math.max(0, Math.min(100, numeric.value))))
const display = computed(() => (numeric.value === null ? '—' : numeric.value.toFixed(0)))
</script>

<template>
  <div class="score">
    <div class="score__head">
      <span class="score__label">{{ label }}</span>
      <span class="score__value tabular">{{ display }}</span>
    </div>
    <div
      class="score__track"
      role="meter"
      :aria-valuenow="numeric ?? undefined"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-label="label"
    >
      <div
        class="score__fill"
        :class="{ 'score__fill--muted': muted, 'score__fill--empty': numeric === null }"
        :style="{ width: `${percent}%` }"
      />
    </div>
    <p v-if="hint" class="score__hint">{{ hint }}</p>
  </div>
</template>

<style scoped>
.score {
  display: grid;
  gap: 0.3rem;
}

.score__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
}

.score__label {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--text-muted);
}

.score__value {
  font-size: 1.35rem;
  font-weight: 650;
  color: var(--text-primary);
  line-height: 1;
}

.score__track {
  height: 6px;
  border-radius: 3px;
  background: var(--surface-2);
  overflow: hidden;
}

.score__fill {
  height: 100%;
  /* 4px rounded data-end, anchored flat against the baseline it grows from. */
  border-radius: 0 3px 3px 0;
  background: var(--accent);
}

.score__fill--muted {
  background: var(--border-strong);
}

.score__fill--empty {
  background: transparent;
}

.score__hint {
  margin: 0;
  font-size: 0.72rem;
  color: var(--text-muted);
  line-height: 1.4;
}
</style>
