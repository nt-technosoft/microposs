<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import AppBottomNav from '@/components/layout/AppBottomNav.vue'
import AppFloatingCart from '@/components/layout/AppFloatingCart.vue'
import AppToastContainer from '@/components/feedback/AppToastContainer.vue'

const route = useRoute()
const auth = useAuthStore()

const showNav = computed(() => {
  return auth.isAuthenticated && route.meta.layout !== 'blank' && route.meta.layout !== 'investor'
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
  <div class="app-root">
    <main
      class="app-main"
      :class="{
        'has-bottom-nav': showNav,
        'app-main--full-white': isFullBleedWhitePage,
      }"
    >
      <RouterView />
    </main>

    <AppFloatingCart v-if="showCart" />
    <AppBottomNav v-if="showNav" />
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

.app-main--full-white {
  max-width: none;
  background: #fff;
}

.app-main.has-bottom-nav {
  padding-bottom: calc(var(--bottom-nav-height) + env(safe-area-inset-bottom, 0px));
}
</style>
