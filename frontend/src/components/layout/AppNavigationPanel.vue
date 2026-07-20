<script setup lang="ts">
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { AppNavItem } from './navigation'
import { getBusinessNavigationGroups, isBusinessNavigationItemActive } from './navigation'
import { cn } from '@/lib/utils'

const props = withDefaults(defineProps<{
  items: AppNavItem[]
  collapsed?: boolean
}>(), {
  collapsed: false,
})

const emit = defineEmits<{
  navigate: []
}>()

const route = useRoute()
const { t } = useI18n()

function itemClass(item: AppNavItem): string {
  return cn(
    'group flex min-h-10 items-center gap-3 rounded-xl px-3 text-sm font-medium text-muted-foreground transition-colors',
    'hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
    props.collapsed && 'justify-center px-0',
    isBusinessNavigationItemActive(item, route.name)
      && 'bg-primary/10 text-primary hover:bg-primary/10 hover:text-primary',
  )
}
</script>

<template>
  <nav :aria-label="t('nav.main')" class="flex flex-col gap-5">
    <section
      v-for="group in getBusinessNavigationGroups(items)"
      :key="group.section.id"
      class="flex flex-col gap-1"
    >
      <h2
        v-if="!collapsed"
        class="px-3 pb-1 text-[0.68rem] font-semibold uppercase tracking-[0.12em] text-muted-foreground/80"
      >
        {{ t(group.section.labelKey) }}
      </h2>
      <RouterLink
        v-for="item in group.items"
        :key="item.id"
        :to="item.to"
        :class="itemClass(item)"
        :title="collapsed ? t(item.labelKey) : undefined"
        :aria-label="collapsed ? t(item.labelKey) : undefined"
        :aria-current="isBusinessNavigationItemActive(item, route.name) ? 'page' : undefined"
        @click="emit('navigate')"
      >
        <component :is="item.icon" class="size-[1.1rem] shrink-0" :stroke-width="1.8" />
        <span v-if="!collapsed" class="truncate">{{ t(item.labelKey) }}</span>
      </RouterLink>
    </section>
  </nav>
</template>
