<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { Menu } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'
import { businessNavigationSections, findBusinessNavigationItem } from './navigation'
import { pageChromeState } from './pageChrome'
import AppAccountMenu from './AppAccountMenu.vue'

const emit = defineEmits<{
  openNavigation: []
}>()

const route = useRoute()
const auth = useAuthStore()
const { t } = useI18n()

const currentItem = computed(() => findBusinessNavigationItem(route.name))
const currentSection = computed(() => {
  const item = currentItem.value
  return item ? businessNavigationSections.find((section) => section.id === item.section) : undefined
})
const title = computed(() => pageChromeState.title || (currentItem.value ? t(currentItem.value.labelKey) : auth.user?.tenant_name || 'MicroPOS'))
const businessName = computed(() => auth.user?.active_business?.name || auth.user?.tenant_name || '')
const eyebrow = computed(() => {
  if (pageChromeState.eyebrow) return pageChromeState.eyebrow
  return currentSection.value ? `${businessName.value} · ${t(currentSection.value.labelKey)}` : businessName.value
})
</script>

<template>
  <header class="app-context-header">
    <Button
      variant="ghost"
      size="icon-lg"
      class="xl:hidden"
      aria-label="Открыть навигацию"
      @click="emit('openNavigation')"
    >
      <Menu />
    </Button>

    <div class="min-w-0 flex-1">
      <p class="truncate text-xs text-muted-foreground">{{ eyebrow }}</p>
      <div class="flex min-w-0 items-center gap-2">
        <h1 class="truncate text-sm font-semibold text-foreground">{{ title }}</h1>
        <span
          v-if="pageChromeState.status"
          class="app-context-header__status"
          :data-tone="pageChromeState.statusTone"
        >
          {{ pageChromeState.status }}
        </span>
      </div>
    </div>

    <div id="app-context-actions" class="flex shrink-0 items-center gap-2" />

    <AppAccountMenu compact />
  </header>
</template>

<style scoped>
.app-context-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: none;
  height: var(--app-header-height);
  align-items: center;
  gap: var(--space-3);
  border-bottom: 1px solid var(--border);
  background: color-mix(in oklch, var(--background) 92%, transparent);
  padding: 0 clamp(1rem, 2vw, 2rem);
  backdrop-filter: blur(16px);
}

.app-context-header__status {
  flex: none;
  border-radius: var(--radius-full);
  background: var(--neutral-100);
  padding: 0.15rem 0.45rem;
  color: var(--neutral-600);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
}

.app-context-header__status[data-tone="positive"] { color: var(--positive); }
.app-context-header__status[data-tone="warning"] { color: color-mix(in oklch, var(--warning) 72%, var(--neutral-900)); }
.app-context-header__status[data-tone="negative"] { color: var(--negative); }

@media (min-width: 768px) {
  .app-context-header {
    display: flex;
  }
}
</style>
