<script setup lang="ts">
interface Props {
  variant?: 'success' | 'warning' | 'error' | 'info' | 'default'
  size?: 'sm' | 'md'
}

withDefaults(defineProps<Props>(), {
  variant: 'default',
  size: 'sm',
})
</script>

<template>
  <span
    class="badge"
    :class="[`badge--${variant}`, `badge--${size}`]"
  >
    <slot />
  </span>
</template>

<style scoped>
.badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  font-weight: var(--font-semibold);
  white-space: nowrap;
  line-height: 1;
}

/* Sizes */
.badge--sm {
  height: 20px;
  padding: 0 var(--space-2);
  font-size: var(--text-xs);
}

.badge--md {
  height: 24px;
  padding: 0 var(--space-3);
  font-size: var(--text-sm);
}

/* Variants */
.badge--default {
  background: var(--color-bg-sunken);
  color: var(--color-text-secondary);
}

.badge--success {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.badge--warning {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.badge--error {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.badge--info {
  background: var(--color-info-bg);
  color: var(--color-info);
}
</style>
