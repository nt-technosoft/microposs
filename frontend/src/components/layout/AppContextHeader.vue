<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { Menu } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'
import { businessNavigationSections, findBusinessNavigationItem } from './navigation'
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
const title = computed(() => currentItem.value ? t(currentItem.value.labelKey) : auth.user?.tenant_name || 'MicroPOS')
const businessName = computed(() => auth.user?.active_business?.name || auth.user?.tenant_name || '')
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
      <p class="truncate text-xs text-muted-foreground">
        {{ businessName }}
        <template v-if="currentSection"> · {{ t(currentSection.labelKey) }}</template>
      </p>
      <p class="truncate text-sm font-semibold text-foreground">{{ title }}</p>
    </div>

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

@media (min-width: 768px) {
  .app-context-header {
    display: flex;
  }
}
</style>
