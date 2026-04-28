<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useBreakpoint } from '@/composables/useBreakpoint'
import AppBottomNav from '@/components/layout/AppBottomNav.vue'
import AppFloatingCart from '@/components/layout/AppFloatingCart.vue'
import AppToastContainer from '@/components/feedback/AppToastContainer.vue'

const route = useRoute()
const auth = useAuthStore()
const { isDesktop } = useBreakpoint()

const showNav = computed(() => {
  return auth.isAuthenticated && route.meta.layout !== 'blank' && route.meta.layout !== 'investor'
})

const showCart = computed(() => {
  if (!auth.isAuthenticated || route.meta.layout === 'investor' || route.meta.layout === 'blank') {
    return false
  }

  return route.name === 'product-detail'
})
</script>

<template>
  <div class="app-root">
    <main class="app-main" :class="{ 'has-bottom-nav': showNav && !isDesktop }">
      <RouterView />
    </main>

    <AppFloatingCart v-if="showCart" />
    <AppBottomNav v-if="showNav && !isDesktop" />
    <AppToastContainer />
  </div>
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

.app-main.has-bottom-nav {
  padding-bottom: calc(var(--bottom-nav-height) + env(safe-area-inset-bottom, 0px));
}
</style>
