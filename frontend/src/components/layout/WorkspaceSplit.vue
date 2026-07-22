<script setup lang="ts">
withDefaults(defineProps<{
  aside?: 'narrow' | 'default' | 'balanced'
  stickyAside?: boolean
}>(), {
  aside: 'default',
  stickyAside: false,
})
</script>

<template>
  <div class="workspace-split" :data-aside="aside">
    <div class="workspace-split__main">
      <slot />
    </div>
    <aside class="workspace-split__aside" :class="{ 'workspace-split__aside--sticky': stickyAside }">
      <slot name="aside" />
    </aside>
  </div>
</template>

<style scoped>
.workspace-split,
.workspace-split__main,
.workspace-split__aside {
  min-width: 0;
}

.workspace-split {
  display: grid;
  gap: var(--space-4);
}

@media (min-width: 1024px) {
  .workspace-split {
    grid-template-columns: minmax(0, 1fr) minmax(320px, 0.8fr);
    align-items: start;
  }

  .workspace-split[data-aside="narrow"] {
    grid-template-columns: minmax(0, 1fr) minmax(280px, 360px);
  }

  .workspace-split[data-aside="balanced"] {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .workspace-split__aside--sticky {
    position: sticky;
    top: calc(var(--sticky-offset) + var(--space-4));
  }
}
</style>
