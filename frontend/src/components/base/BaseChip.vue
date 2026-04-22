<script setup lang="ts">
interface Props {
  active?: boolean
  disabled?: boolean
  size?: 'sm' | 'md'
}

withDefaults(defineProps<Props>(), {
  active: false,
  disabled: false,
  size: 'md',
})

defineEmits<{
  click: []
}>()
</script>

<template>
  <button
    class="chip"
    :class="[
      `chip--${size}`,
      { 'chip--active': active, 'chip--disabled': disabled },
    ]"
    :disabled="disabled"
    @click="$emit('click')"
  >
    <slot />
  </button>
</template>

<style scoped>
.chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  border-radius: var(--radius-full);
  font-weight: var(--font-medium);
  white-space: nowrap;
  cursor: pointer;
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
  transition:
    background var(--duration-fast) var(--ease-out),
    border-color var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
}

.chip--sm {
  height: 32px;
  padding: 0 var(--space-3);
  font-size: var(--text-xs);
}

.chip--md {
  height: 36px;
  padding: 0 var(--space-4);
  font-size: var(--text-sm);
  min-width: 44px;
}

.chip:active:not(:disabled) {
  transform: scale(0.96);
}

.chip--active {
  background: var(--color-brand-500);
  border-color: var(--color-brand-500);
  color: var(--color-text-inverse);
}

.chip--disabled {
  opacity: 0.4;
  cursor: not-allowed;
  text-decoration: line-through;
  background: var(--color-bg-sunken);
}
</style>
