<script setup lang="ts">
const { data: health } = await useFetch('/api/health')
</script>

<template>
  <main style="font-family: system-ui, sans-serif; padding: 2rem;">
    <h1>Malaysia SME Pain Radar</h1>
    <p>Dashboard placeholder &mdash; business features arrive in later milestones.</p>
    <p>Web service health: <strong>{{ health?.status ?? 'unknown' }}</strong></p>
  </main>
</template>
