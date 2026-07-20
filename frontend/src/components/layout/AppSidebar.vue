<script setup lang="ts">
import { computed } from 'vue'
import { BriefcaseBusiness, PanelLeftClose, PanelLeftOpen } from 'lucide-vue-next'
import type { AppNavItem } from './navigation'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'
import AppAccountMenu from './AppAccountMenu.vue'
import AppNavigationPanel from './AppNavigationPanel.vue'

defineProps<{
  items: AppNavItem[]
  collapsed: boolean
}>()

const emit = defineEmits<{
  toggle: []
}>()

const auth = useAuthStore()
const businessName = computed(() => auth.user?.active_business?.name || auth.user?.tenant_name || 'MicroPOS')
</script>

<template>
  <aside class="app-sidebar" :data-collapsed="collapsed ? 'true' : 'false'">
    <Button
      variant="outline"
      size="icon-sm"
      class="app-sidebar__toggle"
      :aria-label="collapsed ? 'Развернуть боковую панель' : 'Свернуть боковую панель'"
      @click="emit('toggle')"
    >
      <PanelLeftOpen v-if="collapsed" />
      <PanelLeftClose v-else />
    </Button>

    <div class="app-sidebar__brand">
      <span class="app-sidebar__mark flex shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground">
        <BriefcaseBusiness class="size-5" aria-hidden="true" />
      </span>
      <div v-if="!collapsed" class="min-w-0 flex-1">
        <p class="truncate text-sm font-semibold text-foreground">{{ businessName }}</p>
        <p class="truncate text-xs text-muted-foreground">Рабочая книга</p>
      </div>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 py-3">
      <AppNavigationPanel :items="items" :collapsed="collapsed" />
    </div>

    <div class="shrink-0 border-t border-border/70 p-2">
      <AppAccountMenu :compact="collapsed" align="start" />
    </div>
  </aside>
</template>

<style scoped>
.app-sidebar {
  position: fixed;
  inset: 0 auto 0 0;
  z-index: var(--z-float);
  display: none;
  width: var(--desktop-sidebar-expanded);
  height: 100dvh;
  flex-direction: column;
  border-right: 1px solid var(--border);
  background: var(--color-bg-elevated);
  transition: width var(--duration-normal) var(--ease-out);
}

.app-sidebar[data-collapsed="true"] {
  width: var(--desktop-sidebar-collapsed);
}

.app-sidebar__brand {
  display: flex;
  height: var(--app-header-height);
  flex: none;
  align-items: center;
  gap: 0.75rem;
  border-bottom: 1px solid var(--border);
  padding: 0 0.75rem;
}

.app-sidebar__mark {
  width: 2.5rem;
  height: 2.5rem;
  transition: width var(--duration-normal) var(--ease-out), height var(--duration-normal) var(--ease-out);
}

.app-sidebar[data-collapsed="true"] .app-sidebar__mark {
  width: 2rem;
  height: 2rem;
}

.app-sidebar__toggle {
  position: absolute;
  top: calc((var(--app-header-height) - 1.75rem) / 2);
  right: -0.875rem;
  z-index: 1;
  width: 1.75rem;
  height: 1.75rem;
  border-color: var(--color-border-default);
  border-radius: var(--radius-full);
  background: var(--color-bg-elevated);
  box-shadow: var(--shadow-sm);
  color: var(--color-text-secondary);
}

.app-sidebar__toggle:hover {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

@media (min-width: 1280px) {
  .app-sidebar {
    display: flex;
  }
}
</style>
