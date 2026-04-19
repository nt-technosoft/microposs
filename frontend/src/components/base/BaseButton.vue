<script setup lang="ts">
defineProps<{
  label: string
  type?: 'button' | 'submit'
  variant?: 'primary' | 'secondary'
}>()
</script>

<template>
  <button :type="type ?? 'button'" :class="['button', `button--${variant ?? 'primary'}`]">
    {{ label }}
  </button>
</template>

<style scoped>
.button {
  width: 100%;
  border: none;
  border-radius: var(--radius-md);
  padding: 0.875rem 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: transform 180ms ease, background-color 180ms ease;
}

.button:hover {
  transform: translateY(-1px);
}

.button--primary {
  background: var(--color-accent);
  color: #fff;
}

.button--secondary {
  background: var(--color-surface-muted);
  color: var(--color-text-primary);
}
</style>
