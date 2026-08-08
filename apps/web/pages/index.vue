<script setup lang="ts">
const { data: health } = await useFetch('/api/health')
</script>

<template>
  <main style="font-family: system-ui, sans-serif; padding: 2rem;">
    <h1>Malaysia SME Pain Radar</h1>
    <p>Dashboard placeholder &mdash; the opportunity dashboard arrives in Milestone 5.</p>
    <p>Web service health: <strong>{{ health?.status ?? 'unknown' }}</strong></p>
    <p><NuxtLink to="/trends">Search trend signals &rarr;</NuxtLink></p>
  </main>
</template>
