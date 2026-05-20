<script setup lang="ts">
import { ref } from 'vue'
import { ArrowLeft, MoreHorizontal } from 'lucide-vue-next'
import { procurementStatusLabel, procurementStatusMeta } from '@/utils/domainLabels'
import { ProcurementStatus } from '@/types/enums'

const props = defineProps<{
  procurementId: number | null
  status: string | null
  title: string
  subtitle: string | null
}>()

const emit = defineEmits<{
  back: []
  'menu-action': [actionKey: string]
}>()

const menuOpen = ref(false)

function toggleMenu(): void { menuOpen.value = !menuOpen.value }
function closeMenu(): void { menuOpen.value = false }
function onMenuAction(key: string): void { closeMenu(); emit('menu-action', key) }

function statusColorClass(status: string | null): string | undefined {
  return status ? procurementStatusMeta[status as ProcurementStatus]?.colorClass : undefined
}

const MENU_ACTIONS = [
  { key: 'attach', label: 'Прикрепить документ' },
  { key: 'amend', label: 'Изменить состав' },
  { key: 'cancel', label: 'Отменить приход' },
  { key: 'reverse_receive', label: 'Отменить приёмку' },
] as const
</script>

<template>
  <header class="workspace-header">
    <button class="header-btn" type="button" aria-label="Назад" @click="emit('back')">
      <ArrowLeft :size="18" :stroke-width="2" />
    </button>

    <div class="header-center">
      <div class="header-title-row">
        <span class="header-title">{{ title }}</span>
        <span
          v-if="status && statusColorClass(status)"
          class="badge-status"
          :class="statusColorClass(status)"
        >{{ procurementStatusLabel(status) }}</span>
      </div>
      <p v-if="subtitle" class="header-subtitle">{{ subtitle }}</p>
    </div>

    <div class="header-menu-wrap">
      <button class="header-btn" type="button" aria-label="Действия" @click="toggleMenu">
        <MoreHorizontal :size="18" :stroke-width="2" />
      </button>
      <div v-if="menuOpen" class="menu-overlay" @click="closeMenu" />
      <ul v-if="menuOpen" class="menu-dropdown" role="menu">
        <li
          v-for="action in MENU_ACTIONS"
          :key="action.key"
          class="menu-item"
          role="menuitem"
          @click="onMenuAction(action.key)"
        >{{ action.label }}</li>
      </ul>
    </div>
  </header>
</template>

<style scoped>
.workspace-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: grid;
  grid-template-columns: 40px 1fr 40px;
  align-items: center;
  gap: var(--space-2);
  min-height: var(--header-height);
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-bg-secondary) 92%, transparent);
  backdrop-filter: blur(14px);
}

.header-btn {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border: 0;
  background: transparent;
  color: var(--color-text-primary);
  cursor: pointer;
  border-radius: var(--radius-md);
}

.header-btn:active { opacity: 0.7; }

.header-center {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  overflow: hidden;
}

.header-title-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.header-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-subtitle {
  margin: 0;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.header-menu-wrap { position: relative; }

.menu-overlay {
  position: fixed;
  inset: 0;
  z-index: 1;
}

.menu-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: 2;
  min-width: 200px;
  margin: 0;
  padding: var(--space-2) 0;
  list-style: none;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
}

.menu-item {
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-sm, 0.875rem);
  color: var(--color-text-primary);
  cursor: pointer;
}

.menu-item:hover { background: var(--color-bg-secondary); }
</style>
