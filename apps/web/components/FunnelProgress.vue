<script setup lang="ts">
/**
 * §3's commercial funnel, showing where an opportunity is and where the
 * evidence says it could be.
 *
 * The gap between the two is the point — §52 has the engine suggest and a human
 * approve, so a suggestion running ahead of the current stage is information to
 * act on, not a state to auto-resolve. Rendering them as one marker would hide
 * exactly the thing the operator needs to see.
 *
 * Reached, current and suggested are distinguished by shape and label as well as
 * colour: the current stage is named in full beneath the track, and the
 * suggested one gets its own caption.
 */
const props = defineProps<{
  status: string
  suggestedStatus: string | null
  order: string[]
  labels: Record<string, string>
}>()

const currentIndex = computed(() => props.order.indexOf(props.status))
const suggestedIndex = computed(() =>
  props.suggestedStatus ? props.order.indexOf(props.suggestedStatus) : -1,
)

const steps = computed(() =>
  props.order.map((stage, index) => ({
    stage,
    label: props.labels[stage] ?? stage,
    reached: index <= currentIndex.value,
    current: index === currentIndex.value,
    // Only marks the stretch the evidence supports but the human has not
    // approved. Beyond the suggestion it is neither reached nor suggested.
    suggested: index > currentIndex.value && index <= suggestedIndex.value,
  })),
)

const ahead = computed(() => suggestedIndex.value > currentIndex.value)
</script>

<template>
  <div class="funnel">
    <ol class="funnel__track">
      <li
        v-for="step in steps"
        :key="step.stage"
        class="funnel__step"
        :class="{
          'funnel__step--reached': step.reached,
          'funnel__step--current': step.current,
          'funnel__step--suggested': step.suggested,
        }"
        :aria-current="step.current ? 'step' : undefined"
      >
        <span class="funnel__bar" />
        <span class="funnel__sr">{{ step.label }}</span>
      </li>
    </ol>

    <p class="funnel__legend">
      <strong>{{ labels[status] ?? status }}</strong>
      <template v-if="ahead">
        &nbsp;·&nbsp; evidence supports
        <strong class="funnel__suggested">{{ labels[suggestedStatus!] ?? suggestedStatus }}</strong>
      </template>
      <template v-else-if="suggestedStatus && suggestedStatus !== status">
        &nbsp;·&nbsp; evidence supports only
        <strong>{{ labels[suggestedStatus] ?? suggestedStatus }}</strong>
      </template>
    </p>
  </div>
</template>

<style scoped>
.funnel {
  display: grid;
  gap: 0.4rem;
}

.funnel__track {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  gap: 2px;
}

.funnel__step {
  flex: 1;
}

.funnel__bar {
  display: block;
  height: 8px;
  border-radius: 2px;
  background: var(--surface-2);
}

.funnel__step--reached .funnel__bar {
  background: var(--accent);
}

.funnel__step--current .funnel__bar {
  background: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}

/* Hatched rather than a second solid hue: this stretch is a claim about what
   COULD be approved, and a solid fill would read as already reached. */
.funnel__step--suggested .funnel__bar {
  background: repeating-linear-gradient(
    135deg,
    var(--accent-soft),
    var(--accent-soft) 3px,
    transparent 3px,
    transparent 6px
  );
  border: 1px solid var(--accent-soft);
}

.funnel__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

.funnel__legend {
  margin: 0;
  font-size: 0.78rem;
  color: var(--text-secondary);
}

.funnel__suggested {
  color: var(--accent);
}
</style>
