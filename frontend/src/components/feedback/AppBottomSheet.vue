<script setup lang="ts">
import ResponsiveOverlay from '@/components/layout/ResponsiveOverlay.vue'

withDefaults(defineProps<{
  open: boolean
  title?: string
}>(), {
  title: '',
})

const emit = defineEmits<{
  close: []
}>()
</script>

<template>
  <ResponsiveOverlay :open="open" :title="title" @close="emit('close')">
    <slot />
  </ResponsiveOverlay>
</template>
