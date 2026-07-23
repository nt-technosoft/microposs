<script setup lang="ts">
withDefaults(defineProps<{
  size?: 'narrow' | 'default' | 'wide' | 'full'
  padded?: boolean
}>(), {
  size: 'default',
  padded: true,
})
</script>

<template>
  <div
    class="page-container"
    :class="[`page-container--${size}`, { 'page-container--padded': padded }]"
  >
    <slot />
  </div>
</template>

<style scoped>
.page-container {
  width: 100%;
  margin-inline: auto;
}

.page-container--narrow { max-width: 720px; }
.page-container--default { max-width: 960px; }
.page-container--wide { max-width: var(--max-content-width); }
.page-container--full { max-width: none; }

.page-container--padded {
  padding-inline: clamp(1rem, 2vw, 2rem);
}

@media (min-width: 1280px) {
  .page-container--wide,
  .page-container--full {
    max-width: none;
  }
}
</style>
