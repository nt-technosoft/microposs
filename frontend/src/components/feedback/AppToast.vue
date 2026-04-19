<script setup lang="ts">
defineProps<{
  message: string
}>()
</script>

<template>
  <div class="toast">{{ message }}</div>
</template>

<style scoped>
.toast {
  position: fixed;
  right: var(--space-4);
  bottom: var(--space-4);
  max-width: 20rem;
  border-radius: var(--radius-md);
  background: var(--color-text-primary);
  color: #fff;
  padding: 0.875rem 1rem;
  box-shadow: var(--shadow-card);
}
</style>
