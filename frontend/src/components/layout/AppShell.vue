<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useUIStore } from '@/stores/ui'
import { getBusinessNavigation } from './navigation'
import AppBottomNav from './AppBottomNav.vue'
import AppContextHeader from './AppContextHeader.vue'
import AppNavigationDrawer from './AppNavigationDrawer.vue'
import AppSidebar from './AppSidebar.vue'

const auth = useAuthStore()
const ui = useUIStore()
const drawerOpen = ref(false)
const sidebarCollapsed = ref(localStorage.getItem('microposs_sidebar_collapsed') === 'true')

const navigationItems = computed(() => getBusinessNavigation({
  role: auth.role,
  simpleSellerMode: ui.simpleSellerMode,
  surface: 'desktop',
}))

watch(sidebarCollapsed, (value) => {
  localStorage.setItem('microposs_sidebar_collapsed', String(value))
})
</script>

<template>
  <div class="app-shell" :data-sidebar-collapsed="sidebarCollapsed ? 'true' : 'false'">
    <AppSidebar
      :items="navigationItems"
      :collapsed="sidebarCollapsed"
      @toggle="sidebarCollapsed = !sidebarCollapsed"
    />
    <AppNavigationDrawer v-model:open="drawerOpen" :items="navigationItems" />

    <div class="app-shell__content">
      <AppContextHeader @open-navigation="drawerOpen = true" />
      <main class="app-shell__main">
        <slot />
      </main>
    </div>

    <AppBottomNav />
  </div>
</template>

<style scoped>
.app-shell {
  min-height: 100dvh;
  background: var(--color-bg-primary);
}

.app-shell__content {
  min-width: 0;
  min-height: 100dvh;
  transition: margin-left var(--duration-normal) var(--ease-out);
}

.app-shell__main {
  width: 100%;
  max-width: none;
  min-height: calc(100dvh - var(--app-header-height));
  background: var(--color-bg-primary);
  padding-bottom: calc(var(--bottom-nav-height) + env(safe-area-inset-bottom, 0px));
}

@media (min-width: 768px) {
  .app-shell__main {
    padding-bottom: 0;
  }

  .app-shell__main :deep(header.sticky),
  .app-shell__main :deep(.page-header),
  .app-shell__main :deep(.catalog-header),
  .app-shell__main :deep(.detail-header),
  .app-shell__main :deep(.cart-header),
  .app-shell__main :deep(.checkout-header),
  .app-shell__main :deep(.topbar),
  .app-shell__main :deep(.workspace-topbar) {
    top: var(--sticky-offset);
  }
}

@media (min-width: 1280px) {
  .app-shell__content {
    margin-left: var(--desktop-sidebar-expanded);
  }

  .app-shell[data-sidebar-collapsed="true"] .app-shell__content {
    margin-left: var(--desktop-sidebar-collapsed);
  }
}
</style>
