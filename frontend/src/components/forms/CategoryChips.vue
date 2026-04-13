<script setup lang="ts">
import type { Category } from '@/types/models'

interface Props {
  categories: Category[]
  selected: number | null
}

defineProps<Props>()

const emit = defineEmits<{
  select: [categoryId: number | null]
}>()

function onSelect(id: number | null) {
  emit('select', id)
}
</script>

<template>
  <div class="chips-scroll-area" role="toolbar" aria-label="Фильтр по категориям">
    <div class="chips-track">
      <!-- "All" chip -->
      <button
        class="chip"
        :class="{ 'chip--active': selected === null }"
        aria-pressed="{ selected === null }"
        @click="onSelect(null)"
      >
        Все
      </button>

      <button
        v-for="cat in categories"
        :key="cat.id"
        class="chip"
        :class="{ 'chip--active': selected === cat.id }"
        :aria-pressed="selected === cat.id"
        @click="onSelect(cat.id)"
      >
        {{ cat.name }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.chips-scroll-area {
  width: 100%;
  overflow-x: auto;
  overflow-y: hidden;
  /* Hide scrollbar across browsers */
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.chips-scroll-area::-webkit-scrollbar {
  display: none;
}

.chips-track {
  display: flex;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-4);
  width: max-content;
  min-width: 100%;
}

.chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 36px;
  min-width: 44px;
  padding: 0 var(--space-4);
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  white-space: nowrap;
  cursor: pointer;
  border: 1.5px solid var(--color-border-default);
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
  transition:
    background var(--duration-fast) var(--ease-out),
    border-color var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-spring);
  -webkit-tap-highlight-color: transparent;
  user-select: none;
}

.chip:active {
  transform: scale(0.93);
}

.chip--active {
  background: var(--color-brand-500);
  border-color: var(--color-brand-500);
  color: var(--color-text-inverse);
}

.chip--active:active {
  background: var(--color-brand-600);
  border-color: var(--color-brand-600);
}
</style>
