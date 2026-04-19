<template>
  <main class="page-shell">
    <BaseCard>
      <h1>Settings</h1>
      <p>Shared authenticated route for all roles.</p>
    </BaseCard>
  </main>
</template>

<script setup lang="ts">
import BaseCard from '@/components/base/BaseCard.vue'
</script>

<style scoped>
.page-shell {
  padding: var(--space-6);
}
</style>
