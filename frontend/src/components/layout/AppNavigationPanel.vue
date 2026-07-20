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
    'app-navigation__item',
    props.collapsed && 'app-navigation__item--collapsed',
    isBusinessNavigationItemActive(item, route.name) && 'app-navigation__item--active',
  )
}
</script>

<template>
  <nav :aria-label="t('nav.main')" class="app-navigation">
    <section
      v-for="group in getBusinessNavigationGroups(items)"
      :key="group.section.id"
      class="app-navigation__group"
      :aria-label="t(group.section.labelKey)"
    >
      <p
        v-if="!collapsed"
        class="app-navigation__section-label"
      >
        {{ t(group.section.labelKey) }}
      </p>
      <span v-else class="app-navigation__section-divider" aria-hidden="true" />
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
        <component :is="item.icon" class="app-navigation__icon" :stroke-width="1.8" />
        <span v-if="!collapsed" class="app-navigation__label">{{ t(item.labelKey) }}</span>
      </RouterLink>
    </section>
  </nav>
</template>

<style scoped>
.app-navigation {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.app-navigation__group {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.app-navigation__section-label {
  overflow: hidden;
  padding: 0 0.625rem 0.25rem;
  color: var(--color-text-tertiary);
  font-size: 0.6875rem;
  font-weight: var(--font-semibold);
  line-height: 1rem;
  letter-spacing: 0.055em;
  text-overflow: ellipsis;
  text-transform: uppercase;
  white-space: nowrap;
}

.app-navigation__section-divider {
  width: 1.25rem;
  height: 1px;
  margin: 0.125rem auto 0.25rem;
  background: var(--color-border-subtle);
}

.app-navigation__item {
  position: relative;
  display: flex;
  min-height: 2.25rem;
  align-items: center;
  gap: 0.625rem;
  border-radius: 0.5rem;
  padding: 0 0.625rem;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  line-height: 1.25rem;
  transition: background-color var(--duration-fast) var(--ease-out), color var(--duration-fast) var(--ease-out);
}

.app-navigation__item:hover {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

.app-navigation__item:focus-visible {
  outline: 2px solid var(--color-border-focus);
  outline-offset: 1px;
}

.app-navigation__item--active {
  background: var(--color-brand-50);
  color: var(--color-brand-700);
  box-shadow: inset 2px 0 0 var(--color-brand-500);
}

.app-navigation__item--active:hover {
  background: var(--color-brand-50);
  color: var(--color-brand-700);
}

.app-navigation__item--collapsed {
  justify-content: center;
  min-height: 2.25rem;
  padding: 0;
}

.app-navigation__icon {
  width: 1.0625rem;
  height: 1.0625rem;
  flex: none;
}

.app-navigation__label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
