<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useUIStore } from '@/stores/ui'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import {
  ShoppingBag,
  Package,
  Download,
  BarChart3,
  Wallet,
  Settings,
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const auth = useAuthStore()
const ui = useUIStore()

interface NavItem {
  name: string
  labelKey: string
  icon: typeof ShoppingBag
  path: string
  roles: string[]
}

const allTabs: NavItem[] = [
  { name: 'sales', labelKey: 'nav.sales', icon: ShoppingBag, path: '/sales', roles: ['owner', 'cashier'] },
  { name: 'products', labelKey: 'nav.products', icon: Package, path: '/products', roles: ['owner', 'warehouse'] },
  { name: 'procurements', labelKey: 'nav.procurements', icon: Download, path: '/procurements', roles: ['owner', 'warehouse'] },
  { name: 'reports', labelKey: 'nav.reports', icon: BarChart3, path: '/reports', roles: ['owner'] },
  { name: 'cash', labelKey: 'nav.cash', icon: Wallet, path: '/finance/cash', roles: ['owner'] },
  { name: 'more', labelKey: 'nav.more', icon: Settings, path: '/settings', roles: ['owner', 'cashier', 'warehouse'] },
]

const visibleTabs = computed(() => {
  if (ui.simpleSellerMode) {
    return allTabs.filter((tab) => tab.name === 'sales')
  }

  const role = auth.role
  if (!role) return allTabs.filter((tab) => tab.name === 'sales')
  return allTabs.filter((tab) => tab.roles.includes(role))
})

function isActive(tab: NavItem): boolean {
  return route.path.startsWith(tab.path)
}

function tabClass(tab: NavItem): string {
  return cn(
    'nav-tab relative h-14 min-w-0 flex-1 flex-col gap-1 rounded-lg px-1 pt-2.5 pb-1.5 text-muted-foreground',
    'hover:bg-muted/70 hover:text-foreground',
    'sm:h-14 sm:max-w-28 sm:px-3',
    isActive(tab) && 'bg-primary/10 text-primary hover:bg-primary/10 hover:text-primary',
  )
}

function navigate(tab: NavItem) {
  router.push(tab.path)
}
</script>

<template>
  <nav
    class="safe-area-bottom fixed inset-x-0 bottom-0 z-[var(--z-sticky)] border-t border-border bg-background/95 shadow-lg backdrop-blur supports-[backdrop-filter]:bg-background/85"
    :aria-label="t('nav.main')"
  >
    <div class="flex h-[var(--bottom-nav-height)] w-full items-center justify-center gap-1 px-1 sm:gap-2 sm:px-4">
      <Button
        v-for="tab in visibleTabs"
        :key="tab.name"
        variant="ghost"
        size="sm"
        :class="tabClass(tab)"
        :aria-label="t(tab.labelKey)"
        :aria-current="isActive(tab) ? 'page' : undefined"
        :data-active="isActive(tab) ? 'true' : undefined"
        @click="navigate(tab)"
      >
        <span
          v-if="isActive(tab)"
          class="absolute top-1 h-0.5 w-5 rounded-full bg-primary"
          aria-hidden="true"
        />
        <component :is="tab.icon" :stroke-width="1.9" data-icon="inline-start" />
        <span class="max-w-full truncate text-xs font-medium leading-none">
          {{ t(tab.labelKey) }}
        </span>
      </Button>
    </div>
  </nav>
</template>

<style scoped>
.nav-tab :deep(svg) {
  width: 22px;
  height: 22px;
}
</style>
