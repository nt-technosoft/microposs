<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import AppFloatingCart from '@/components/layout/AppFloatingCart.vue'
import AppShell from '@/components/layout/AppShell.vue'
import AppToastContainer from '@/components/feedback/AppToastContainer.vue'
import { isBusinessWorkspaceRole } from '@/components/layout/navigation'

const route = useRoute()
const auth = useAuthStore()

const showBusinessShell = computed(() => {
  return auth.isAuthenticated
    && isBusinessWorkspaceRole(auth.role)
    && route.meta.layout !== 'blank'
    && route.meta.layout !== 'investor'
})

const showCart = computed(() => {
  if (!auth.isAuthenticated || route.meta.layout === 'investor' || route.meta.layout === 'blank') {
    return false
  }

  return route.name === 'product-detail'
})

const isFullBleedWhitePage = computed(() => route.name === 'procurement-list')
</script>

<template>
  <AppShell v-if="showBusinessShell" :full-bleed="isFullBleedWhitePage">
    <RouterView />
  </AppShell>

  <div v-else class="app-root">
    <main
      class="app-main"
      :class="{
        'app-main--full-white': isFullBleedWhitePage,
      }"
    >
      <RouterView />
    </main>

  </div>

  <AppFloatingCart v-if="showCart" />
  <AppToastContainer />
</template>

<style scoped>
.app-root {
  min-height: 100dvh;
  display: flex;
  flex-direction: column;
}

.app-main {
  flex: 1;
  width: 100%;
  max-width: var(--max-content-width);
  margin: 0 auto;
}

.app-main--full-white {
  max-width: none;
  background: #fff;
}

</style>
