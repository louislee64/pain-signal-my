<script setup lang="ts">
/**
 * Shared shell for every dashboard page.
 *
 * The nav order follows the question §33 says the dashboard must answer —
 * "What should I investigate or sell this week?" — so Overview is first and
 * Sources (the "can I trust these numbers" page) is last rather than absent.
 */
const links = [
  { to: '/', label: 'Overview' },
  { to: '/topics', label: 'Topics' },
  { to: '/trends', label: 'Search trends' },
  { to: '/reports', label: 'Reports' },
  { to: '/outcomes', label: 'Outcomes' },
  { to: '/sources', label: 'Sources' },
]

const route = useRoute()

function isActive(to: string): boolean {
  if (to === '/') return route.path === '/'
  return route.path.startsWith(to)
}
</script>

<template>
  <div class="shell">
    <header class="shell__bar">
      <div class="shell__inner">
        <NuxtLink to="/" class="shell__brand">
          Malaysia SME Pain Radar
        </NuxtLink>
        <nav class="shell__nav" aria-label="Main">
          <NuxtLink
            v-for="link in links"
            :key="link.to"
            :to="link.to"
            class="shell__link"
            :class="{ 'shell__link--active': isActive(link.to) }"
            :aria-current="isActive(link.to) ? 'page' : undefined"
          >
            {{ link.label }}
          </NuxtLink>
        </nav>
      </div>
    </header>

    <main class="shell__main">
      <slot />
    </main>
  </div>
</template>

<style scoped>
.shell {
  min-height: 100vh;
  background: var(--plane);
}

.shell__bar {
  border-bottom: 1px solid var(--border);
  background: var(--surface-1);
  position: sticky;
  top: 0;
  z-index: 10;
}

.shell__inner {
  max-width: var(--max-width);
  margin: 0 auto;
  padding: 0.7rem 1.5rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.5rem;
  flex-wrap: wrap;
}

.shell__brand {
  font-weight: 650;
  font-size: 0.92rem;
  color: var(--text-primary);
  text-decoration: none;
  letter-spacing: -0.01em;
}

.shell__nav {
  display: flex;
  gap: 0.25rem;
  flex-wrap: wrap;
}

.shell__link {
  color: var(--text-secondary);
  text-decoration: none;
  font-size: 0.85rem;
  padding: 0.35rem 0.6rem;
  border-radius: var(--radius-sm);
}

.shell__link:hover {
  background: var(--surface-2);
  color: var(--text-primary);
}

.shell__link--active {
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 600;
}

.shell__main {
  max-width: var(--max-width);
  margin: 0 auto;
  padding: 1.75rem 1.5rem 4rem;
}
</style>
