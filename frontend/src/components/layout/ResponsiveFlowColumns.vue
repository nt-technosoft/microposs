<script setup lang="ts">
withDefaults(defineProps<{
  columns?: 2 | 3
}>(), {
  columns: 2,
})
</script>

<template>
  <div class="responsive-flow-columns" :style="{ '--flow-column-count': columns }">
    <slot />
  </div>
</template>

<style scoped>
.responsive-flow-columns {
  display: grid;
  gap: var(--space-3);
  min-width: 0;
}

@media (min-width: 1024px) {
  .responsive-flow-columns {
    display: block;
    columns: var(--flow-column-count);
    column-gap: var(--space-3);
  }

  .responsive-flow-columns > :slotted(*) {
    width: 100%;
    margin: 0 0 var(--space-3);
    break-inside: avoid;
  }
}
</style>
