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
    <div class="flex h-[var(--app-header-height)] shrink-0 items-center gap-3 border-b border-border/70 px-3">
      <span class="flex size-10 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground">
        <BriefcaseBusiness class="size-5" aria-hidden="true" />
      </span>
      <div v-if="!collapsed" class="min-w-0 flex-1">
        <p class="truncate text-sm font-semibold text-foreground">{{ businessName }}</p>
        <p class="truncate text-xs text-muted-foreground">Бизнес</p>
      </div>
      <Button
        v-if="!collapsed"
        variant="ghost"
        size="icon-sm"
        aria-label="Свернуть боковую панель"
        @click="emit('toggle')"
      >
        <PanelLeftClose />
      </Button>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain px-2 py-4">
      <AppNavigationPanel :items="items" :collapsed="collapsed" />
    </div>

    <div class="shrink-0 border-t border-border/70 p-2">
      <Button
        v-if="collapsed"
        variant="ghost"
        size="icon-lg"
        class="mb-1 w-full rounded-xl"
        aria-label="Развернуть боковую панель"
        @click="emit('toggle')"
      >
        <PanelLeftOpen />
      </Button>
      <AppAccountMenu :compact="collapsed" align="start" />
    </div>
  </aside>
</template>

<style scoped>
.app-sidebar {
  position: fixed;
  inset: 0 auto 0 0;
  z-index: var(--z-sticky);
  display: none;
  width: var(--desktop-sidebar-expanded);
  height: 100dvh;
  flex-direction: column;
  border-right: 1px solid var(--border);
  background: color-mix(in oklch, var(--surface) 96%, transparent);
  transition: width var(--duration-normal) var(--ease-out);
}

.app-sidebar[data-collapsed="true"] {
  width: var(--desktop-sidebar-collapsed);
}

@media (min-width: 1280px) {
  .app-sidebar {
    display: flex;
  }
}
</style>
