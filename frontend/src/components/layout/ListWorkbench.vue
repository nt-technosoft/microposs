<script setup lang="ts">
withDefaults(defineProps<{
  aside?: 'narrow' | 'default' | 'wide'
  stickyAside?: boolean
}>(), {
  aside: 'default',
  stickyAside: false,
})
</script>

<template>
  <section class="list-workbench" :data-aside="aside">
    <header v-if="$slots.toolbar" class="list-workbench__toolbar">
      <slot name="toolbar" />
    </header>

    <div class="list-workbench__body" :class="{ 'list-workbench__body--with-aside': $slots.aside }">
      <aside
        v-if="$slots.aside"
        class="list-workbench__aside"
        :class="{ 'list-workbench__aside--sticky': stickyAside }"
      >
        <slot name="aside" />
      </aside>

      <div class="list-workbench__content">
        <slot />
      </div>
    </div>
  </section>
</template>

<style scoped>
.list-workbench {
  min-width: 0;
}

.list-workbench__toolbar {
  margin-bottom: var(--space-4);
}

.list-workbench__body,
.list-workbench__content {
  min-width: 0;
}

.list-workbench__aside {
  min-width: 0;
  margin-bottom: var(--space-4);
}

@media (min-width: 1024px) {
  .list-workbench__body--with-aside {
    display: grid;
    grid-template-columns: minmax(180px, 220px) minmax(0, 1fr);
    align-items: start;
    gap: clamp(1rem, 2vw, 2rem);
  }

  .list-workbench[data-aside="narrow"] .list-workbench__body--with-aside {
    grid-template-columns: minmax(160px, 190px) minmax(0, 1fr);
  }

  .list-workbench[data-aside="wide"] .list-workbench__body--with-aside {
    grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
  }

  .list-workbench__aside {
    margin-bottom: 0;
  }

  .list-workbench__aside--sticky {
    position: sticky;
    top: calc(var(--sticky-offset) + var(--space-4));
  }
}
</style>
