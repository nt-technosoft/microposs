<script setup lang="ts">
import { computed } from 'vue'
import { ChevronRight } from 'lucide-vue-next'
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
  BY_WEIGHT: 'по весу',
}

const props = defineProps<{ expense: Expense; items: Item[]; isEditable?: boolean }>()
const emit = defineEmits<{ click: [id: number] }>()

const typeLabel = computed(() => EXPENSE_LABELS[props.expense.expense_type] ?? props.expense.expense_type)
const methodLabel = computed(() => METHOD_LABELS[props.expense.allocation_method] ?? props.expense.allocation_method)

const targetLabel = computed(() => {
  const ids = props.expense.target_item_ids
  if (!ids.length) return 'на все товары'
  if (ids.length <= 2) {
    return ids.map((id) => props.items.find((i) => i.id === id)?.product_variant_name ?? `#${id}`).join(', ')
  }
  return `на ${ids.length} товара`
})

const amountDisplay = computed(
  () => `${(parseFloat(props.expense.amount) || 0).toLocaleString('ru-RU')} ${props.expense.currency}`,
)
</script>

<template>
  <button
    type="button"
    class="flex w-full items-center gap-3 rounded-[10px] border border-neutral-200 px-3.5 py-3 text-left transition-colors hover:border-green-300 hover:bg-green-50/40"
    @click="emit('click', expense.id)"
  >
    <div class="min-w-0 flex-1">
      <span class="block truncate text-sm font-medium text-foreground">{{ typeLabel }}</span>
      <span class="mt-0.5 block truncate text-xs text-neutral-500">{{ methodLabel }} · {{ targetLabel }}</span>
    </div>
    <span class="shrink-0 text-sm font-semibold tabular-nums text-foreground">{{ amountDisplay }}</span>
    <ChevronRight class="size-4 shrink-0 text-neutral-400" />
  </button>
</template>
