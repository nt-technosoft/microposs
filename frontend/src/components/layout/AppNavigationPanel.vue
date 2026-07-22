<script setup lang="ts">
import { computed, onMounted, ref, useId } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronDown } from 'lucide-vue-next'
import type { AppNavItem, BusinessNavSection } from './navigation'
import { getBusinessNavigationGroups, isBusinessNavigationItemActive } from './navigation'
import { cn } from '@/lib/utils'

const props = withDefaults(defineProps<{
  items: AppNavItem[]
  collapsed?: boolean
  collapsibleSections?: boolean
}>(), {
  collapsed: false,
  collapsibleSections: false,
})

const emit = defineEmits<{
  navigate: []
}>()

const route = useRoute()
const { t } = useI18n()
const instanceId = useId().replace(/:/g, '')
const collapsedSections = ref<Set<BusinessNavSection>>(new Set())
const groups = computed(() => getBusinessNavigationGroups(props.items))
const canCollapseSections = computed(
  () => props.collapsibleSections && !props.collapsed && groups.value.length > 1,
)

const STORAGE_KEY = 'microposs:desktop-nav-sections:v1'

onMounted(() => {
  if (!canCollapseSections.value) return

  try {
    const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? '[]')
    const validSections = new Set(groups.value.map((group) => group.section.id))
    collapsedSections.value = new Set(
      Array.isArray(stored)
        ? stored.filter((section): section is BusinessNavSection => validSections.has(section))
        : [],
    )
  } catch {
    collapsedSections.value = new Set()
  }
})

function groupIsActive(section: BusinessNavSection): boolean {
  return groups.value
    .find((group) => group.section.id === section)
    ?.items.some((item) => isBusinessNavigationItemActive(item, route.name)) ?? false
}

function groupIsCollapsed(section: BusinessNavSection): boolean {
  return canCollapseSections.value
    && !groupIsActive(section)
    && collapsedSections.value.has(section)
}

function sectionContentId(section: BusinessNavSection): string {
  return `app-navigation-${instanceId}-${section}`
}

function toggleSection(section: BusinessNavSection): void {
  if (!canCollapseSections.value || groupIsActive(section)) return

  const next = new Set(collapsedSections.value)
  if (next.has(section)) next.delete(section)
  else next.add(section)
  collapsedSections.value = next

  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify([...next]))
  } catch {
    // Navigation remains usable when storage is unavailable.
  }
}

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
      v-for="group in groups"
      :key="group.section.id"
      class="app-navigation__group"
      :aria-label="t(group.section.labelKey)"
    >
      <button
        v-if="canCollapseSections"
        class="app-navigation__section-toggle"
        type="button"
        :data-section-id="group.section.id"
        :aria-controls="sectionContentId(group.section.id)"
        :aria-expanded="!groupIsCollapsed(group.section.id)"
        :disabled="groupIsActive(group.section.id)"
        @click="toggleSection(group.section.id)"
      >
        <span>{{ t(group.section.labelKey) }}</span>
        <ChevronDown
          class="app-navigation__section-chevron"
          :class="{ 'app-navigation__section-chevron--collapsed': groupIsCollapsed(group.section.id) }"
          :size="14"
          :stroke-width="1.8"
          aria-hidden="true"
        />
      </button>
      <p v-else-if="!collapsed" class="app-navigation__section-label">
        {{ t(group.section.labelKey) }}
      </p>
      <span v-else class="app-navigation__section-divider" aria-hidden="true" />
      <div
        :id="sectionContentId(group.section.id)"
        class="app-navigation__section-content"
        :data-collapsed="groupIsCollapsed(group.section.id) ? 'true' : 'false'"
        :data-section-items="group.section.id"
      >
        <div class="app-navigation__section-inner">
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
        </div>
      </div>
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

.app-navigation__section-toggle {
  display: flex;
  min-height: 1.5rem;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  border-radius: 0.375rem;
  padding: 0 0.625rem 0.25rem;
  color: var(--color-text-tertiary);
  font-size: 0.6875rem;
  font-weight: var(--font-semibold);
  line-height: 1rem;
  letter-spacing: 0.055em;
  text-align: left;
  text-transform: uppercase;
}

.app-navigation__section-toggle:hover:not(:disabled) {
  color: var(--color-text-primary);
}

.app-navigation__section-toggle:focus-visible {
  outline: 2px solid var(--color-border-focus);
  outline-offset: 1px;
}

.app-navigation__section-toggle:disabled {
  cursor: default;
}

.app-navigation__section-chevron {
  flex: none;
  transition: transform var(--duration-fast) var(--ease-out);
}

.app-navigation__section-chevron--collapsed {
  transform: rotate(-90deg);
}

.app-navigation__section-content {
  display: grid;
  grid-template-rows: 1fr;
  opacity: 1;
  transition: grid-template-rows var(--duration-fast) var(--ease-out), opacity var(--duration-fast) var(--ease-out);
}

.app-navigation__section-content[data-collapsed="true"] {
  grid-template-rows: 0fr;
  opacity: 0;
}

.app-navigation__section-inner {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
  min-height: 0;
  overflow: hidden;
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

@media (prefers-reduced-motion: reduce) {
  .app-navigation__section-chevron,
  .app-navigation__section-content {
    transition: none;
  }
}
</style>
