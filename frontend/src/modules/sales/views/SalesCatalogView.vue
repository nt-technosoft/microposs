<template>
  <main class="page-shell">
    <BaseCard>
      <h1>Sales Catalog</h1>
      <p>P0 sales route is ready for real API integration.</p>
    </BaseCard>
    <AppEmptyState
      title="Catalog scaffolded"
      description="Next step is product loading, filters, and cart interactions."
    />
  </main>
</template>

<script setup lang="ts">
import BaseCard from '@/components/base/BaseCard.vue'
import AppEmptyState from '@/components/feedback/AppEmptyState.vue'
</script>

<style scoped>
.page-shell {
  display: grid;
  gap: var(--space-6);
  padding: var(--space-6);
}
</style>
