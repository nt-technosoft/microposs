<script setup lang="ts">
import { computed } from 'vue'
import { ChevronRight, Trash2 } from 'lucide-vue-next'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

type Expense = ProcurementWorkspacePayload['documents']['expenses'][number]
type Item = ProcurementWorkspacePayload['documents']['items'][number]

const EXPENSE_LABELS: Record<string, string> = {
  LOGISTICS: 'Логистика',
  CUSTOMS: 'Таможня',
  FEE: 'Комиссия',
  OTHER: 'Прочее',
}
const METHOD_LABELS: Record<string, string> = {
  BY_VALUE: 'по стоимости',
  BY_QUANTITY: 'по количеству',
}

const props = defineProps<{ expense: Expense; items: Item[]; isEditable: boolean }>()
const emit = defineEmits<{ click: [id: number]; delete: [id: number] }>()

const typeLabel = computed(() => EXPENSE_LABELS[props.expense.expense_type] ?? props.expense.expense_type)
const methodLabel = computed(() => METHOD_LABELS[props.expense.allocation_method] ?? props.expense.allocation_method)

const targetLabel = computed(() => {
  const ids = props.expense.target_item_ids
  if (!ids.length) return 'на все товары'
  if (ids.length <= 2) {
    return ids.map((id) => props.items.find((i) => i.id === id)?.product_variant_name ?? `#${id}`).join(', ')
  }
  return `На ${ids.length} товара`
})

const amountDisplay = computed(() => {
  const amt = parseFloat(props.expense.amount) || 0
  return `${amt.toLocaleString('ru-RU')} ${props.expense.currency}`
})

function tryDelete(): void {
  if (window.confirm(`Удалить расход «${typeLabel.value}»?`)) {
    emit('delete', props.expense.id)
  }
}
</script>

<template>
  <div class="expense-row" role="button" tabindex="0" @click="emit('click', expense.id)" @keydown.enter="emit('click', expense.id)">
    <div class="expense-main">
      <span class="expense-type">{{ typeLabel }}</span>
      <div class="expense-detail">{{ amountDisplay }} · {{ methodLabel }}</div>
      <div class="expense-target">{{ targetLabel }}</div>
    </div>
    <div class="expense-actions" @click.stop @keydown.stop>
      <button v-if="isEditable" class="delete-btn" type="button" @click="tryDelete">
        <Trash2 :size="14" :stroke-width="2" />
      </button>
      <ChevronRight class="chevron" :size="16" :stroke-width="2" />
    </div>
  </div>
</template>

<style scoped>
.expense-row { display: flex; align-items: center; gap: var(--space-3); padding: var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-primary); cursor: pointer; }
.expense-main { flex: 1; min-width: 0; display: grid; gap: 2px; }
.expense-type { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.expense-detail { font-size: var(--text-xs); color: var(--color-text-secondary); font-variant-numeric: tabular-nums; }
.expense-target { font-size: var(--text-xs); color: var(--color-text-tertiary); }
.expense-actions { display: flex; align-items: center; gap: var(--space-1); flex-shrink: 0; }
.delete-btn { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: 1px solid color-mix(in srgb, var(--color-error) 20%, transparent); border-radius: var(--radius-md); background: color-mix(in srgb, var(--color-error) 6%, transparent); color: var(--color-error); cursor: pointer; }
.chevron { color: var(--color-text-tertiary); }
</style>
