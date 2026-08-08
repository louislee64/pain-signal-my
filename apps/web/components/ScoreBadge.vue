<script setup lang="ts">
/**
 * A §35 recommendation or a source-health status, as a labelled chip.
 *
 * The label is always rendered. Status colour carries emphasis, never identity —
 * a reader who cannot distinguish the hues still reads the word, and the words
 * are the actual states the recommendation engine emits.
 */
const props = defineProps<{
  value: string | null
  kind?: 'recommendation' | 'health' | 'status'
}>()

// §35's six states, ordered by how much action they demand. IGNORE is neutral
// rather than "bad": it is a decision that has been made, not a failure.
const RECOMMENDATION_TONE: Record<string, string> = {
  PRODUCTIZE: 'good',
  SELL_PILOT: 'good',
  VALIDATE: 'warning',
  INVESTIGATE: 'warning',
  WATCH: 'neutral',
  IGNORE: 'neutral',
}

const HEALTH_TONE: Record<string, string> = {
  ok: 'good',
  degraded: 'warning',
  stale: 'warning',
  failing: 'critical',
  never_run: 'neutral',
  disabled: 'neutral',
}

const tone = computed(() => {
  if (!props.value) return 'neutral'
  if (props.kind === 'health') return HEALTH_TONE[props.value] ?? 'neutral'
  if (props.kind === 'recommendation') return RECOMMENDATION_TONE[props.value] ?? 'neutral'
  return 'neutral'
})

const label = computed(() => (props.value ?? 'unscored').replace(/_/g, ' '))
</script>

<template>
  <span class="badge" :class="`badge--${tone}`">{{ label }}</span>
</template>

<style scoped>
.badge {
  display: inline-block;
  font-size: 0.7rem;
  font-weight: 650;
  letter-spacing: 0.03em;
  text-transform: uppercase;
  padding: 0.16rem 0.42rem;
  border-radius: 4px;
  white-space: nowrap;
}

.badge--good {
  color: var(--status-good);
  background: var(--status-good-soft);
}

.badge--warning {
  color: var(--status-warning);
  background: var(--status-warning-soft);
}

.badge--serious {
  color: var(--status-serious);
  background: var(--status-serious-soft);
}

.badge--critical {
  color: var(--status-critical);
  background: var(--status-critical-soft);
}

.badge--neutral {
  color: var(--status-neutral);
  background: var(--status-neutral-soft);
}
</style>
