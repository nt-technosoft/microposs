<script setup lang="ts">
defineProps<{
  title: string
  description: string
}>()
</script>

<template>
  <section class="empty-state">
    <h2>{{ title }}</h2>
    <p>{{ description }}</p>
  </section>
</template>

<style scoped>
.empty-state {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-8);
  text-align: center;
  color: var(--color-text-secondary);
}
</style>
