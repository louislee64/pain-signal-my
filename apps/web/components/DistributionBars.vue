<script setup lang="ts">
/**
 * A labelled count distribution — states, payer types, affected roles.
 *
 * Horizontal bars, sorted descending, one hue. This is a magnitude comparison
 * across named categories, so the bar length carries the value and the label
 * carries identity; colouring each row differently would imply the categories
 * mean something to each other that they don't.
 *
 * Bars are scaled against the largest value rather than a total, because the
 * question is "which is biggest and by how much", not "what share of the whole".
 */
const props = withDefaults(defineProps<{
  distribution: Record<string, number> | null
  emptyMessage?: string
  limit?: number
}>(), {
  emptyMessage: 'No breakdown recorded.',
  limit: 12,
})

const rows = computed(() => {
  const entries = Object.entries(props.distribution ?? {})
  if (entries.length === 0) return []

  const sorted = entries.sort(([, a], [, b]) => b - a)
  const max = Math.max(1, ...sorted.map(([, v]) => v))

  const visible = sorted.slice(0, props.limit)
  const hidden = sorted.slice(props.limit)

  // A truncated list says so and says how much it dropped. Silently showing the
  // top 12 of 40 reads as "there are 12".
  const overflow = hidden.length === 0
    ? null
    : { count: hidden.length, total: hidden.reduce((sum, [, v]) => sum + v, 0) }

  return {
    items: visible.map(([label, value]) => ({
      label: label.replace(/_/g, ' '),
      value,
      share: (value / max) * 100,
    })),
    overflow,
  }
})
</script>

<template>
  <p v-if="!('items' in rows)" class="empty">{{ emptyMessage }}</p>

  <div v-else class="dist">
    <div v-for="row in rows.items" :key="row.label" class="dist__row">
      <span class="dist__label">{{ row.label }}</span>
      <span class="dist__track">
        <span class="dist__fill" :style="{ width: `${row.share}%` }" />
      </span>
      <span class="dist__value tabular">{{ row.value }}</span>
    </div>
    <p v-if="rows.overflow" class="dist__overflow">
      + {{ rows.overflow.count }} more ({{ rows.overflow.total }} signals) not shown
    </p>
  </div>
</template>

<style scoped>
.empty {
  margin: 0;
  font-size: 0.8rem;
  color: var(--text-muted);
}

.dist {
  display: grid;
  gap: 0.3rem;
}

.dist__row {
  display: grid;
  grid-template-columns: minmax(90px, 150px) 1fr auto;
  align-items: center;
  gap: 0.6rem;
  font-size: 0.78rem;
}

.dist__label {
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dist__track {
  height: 8px;
  border-radius: 4px;
  background: var(--surface-2);
  overflow: hidden;
}

.dist__fill {
  display: block;
  height: 100%;
  border-radius: 0 4px 4px 0;
  background: var(--accent);
  opacity: 0.8;
}

.dist__value {
  min-width: 2rem;
  text-align: right;
  color: var(--text-primary);
  font-weight: 600;
}

.dist__overflow {
  margin: 0.2rem 0 0;
  font-size: 0.72rem;
  color: var(--text-muted);
}
</style>
