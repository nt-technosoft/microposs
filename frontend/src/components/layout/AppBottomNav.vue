<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import {
  ShoppingBag,
  Package,
  Download,
  BarChart3,
  Settings,
} from 'lucide-vue-next'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

interface NavItem {
  name: string
  label: string
  icon: typeof ShoppingBag
  path: string
  roles: string[]
}

const allTabs: NavItem[] = [
  { name: 'sales', label: 'Продажа', icon: ShoppingBag, path: '/sales', roles: ['owner', 'cashier'] },
  { name: 'products', label: 'Товары', icon: Package, path: '/products', roles: ['owner', 'warehouse'] },
  { name: 'intake', label: 'Приход', icon: Download, path: '/intake', roles: ['owner', 'warehouse'] },
  { name: 'reports', label: 'Отчёты', icon: BarChart3, path: '/reports', roles: ['owner'] },
  { name: 'more', label: 'Ещё', icon: Settings, path: '/settings', roles: ['owner', 'cashier', 'warehouse'] },
]

const visibleTabs = computed(() => {
  const role = auth.role
  if (!role) return allTabs
  return allTabs.filter((tab) => tab.roles.includes(role))
})

function isActive(tab: NavItem): boolean {
  return route.path.startsWith(tab.path)
}

function navigate(tab: NavItem) {
  router.push(tab.path)
}
</script>

<template>
  <nav class="bottom-nav safe-area-bottom" aria-label="Main navigation">
    <button
      v-for="tab in visibleTabs"
      :key="tab.name"
      class="nav-item"
      :class="{ active: isActive(tab) }"
      :aria-label="tab.label"
      :aria-current="isActive(tab) ? 'page' : undefined"
      @click="navigate(tab)"
    >
      <component :is="tab.icon" :size="22" :stroke-width="1.75" class="nav-icon" />
      <span class="nav-label">{{ tab.label }}</span>
    </button>
  </nav>
</template>

<style scoped>
.bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: var(--bottom-nav-height);
  background: var(--color-bg-elevated);
  border-top: 1px solid var(--color-border-subtle);
  display: flex;
  align-items: center;
  justify-content: space-around;
  z-index: var(--z-sticky);
  box-shadow: 0 -2px 8px rgba(26, 23, 20, 0.04);
}

.nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: var(--space-1) var(--space-3);
  min-width: 64px;
  min-height: 44px;
  border-radius: var(--radius-md);
  transition: color var(--duration-fast) var(--ease-out);
  color: var(--color-text-tertiary);
}

.nav-item:active {
  transform: scale(0.95);
}

.nav-item.active {
  color: var(--color-brand-500);
}

.nav-item.active .nav-label {
  font-weight: var(--font-semibold);
}

.nav-icon {
  flex-shrink: 0;
}

.nav-label {
  font-size: var(--text-xs);
  line-height: 1;
  font-weight: var(--font-medium);
}
</style>
