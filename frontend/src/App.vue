<script setup lang="ts">
import { computed } from 'vue'
import { RouterView } from 'vue-router'

import AppToast from '@/components/feedback/AppToast.vue'
import AppLoadingOverlay from '@/components/feedback/AppLoadingOverlay.vue'
import { useUiStore } from '@/stores/ui'

const uiStore = useUiStore()
const isBusy = computed(() => uiStore.isBusy)
const toastMessage = computed(() => uiStore.toastMessage)
</script>

<template>
  <div class="app-shell">
    <RouterView />
    <AppLoadingOverlay v-if="isBusy" />
    <AppToast v-if="toastMessage" :message="toastMessage" />
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: var(--color-background);
  color: var(--color-text-primary);
}
</style>
