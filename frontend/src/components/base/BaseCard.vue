<script setup lang="ts">
interface Props {
  clickable?: boolean
  padding?: 'sm' | 'md' | 'lg'
}

withDefaults(defineProps<Props>(), {
  clickable: false,
  padding: 'md',
})
</script>

<template>
  <div
    class="card"
    :class="[
      `card--pad-${padding}`,
      { 'card--clickable': clickable },
    ]"
    :role="clickable ? 'button' : undefined"
    :tabindex="clickable ? 0 : undefined"
  >
    <slot />
  </div>
</template>

<style scoped>
.card {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  transition:
    box-shadow var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-out);
}

.card--pad-sm { padding: var(--space-3); }
.card--pad-md { padding: var(--space-5); }
.card--pad-lg { padding: var(--space-6); }

.card--clickable {
  cursor: pointer;
}

.card--clickable:hover {
  box-shadow: var(--shadow-sm);
}

.card--clickable:active {
  transform: scale(0.98);
}
</style>
