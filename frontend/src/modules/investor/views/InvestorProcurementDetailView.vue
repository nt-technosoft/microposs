<script setup lang="ts">
import { useRoute } from 'vue-router'

import BaseCard from '@/components/base/BaseCard.vue'

const route = useRoute()
</script>

<template>
  <main class="page-shell">
    <BaseCard>
      <h1>Investor Procurement Detail</h1>
      <p>Procurement ID: {{ route.params.id ?? 'unknown' }}</p>
    </BaseCard>
  </main>
</template>

<style scoped>
.page-shell {
  padding: var(--space-6);
}
</style>
