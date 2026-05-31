<script setup lang="ts">
import { ref, computed } from 'vue'
import { CheckCircle2, Plus, Info } from 'lucide-vue-next'
import ProcurementExpenseRow from './ProcurementExpenseRow.vue'
import ProcurementExpenseEditSheet from './ProcurementExpenseEditSheet.vue'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

type Expense = ProcurementWorkspacePayload['documents']['expenses'][number]
type ActionExpense = { id?: number; expense_type: string; amount: number; currency: string; fx_rate: string; allocation_method: string; target_item_ids: number[] }

const props = defineProps<{ procurement: ProcurementWorkspacePayload }>()
const emit = defineEmits<{
  'update-expenses': [expenses: ActionExpense[]]
  'delete-expense': [expenseId: number]
}>()

const editSheetOpen = ref(false)
const editingExpenseId = ref<number | null>(null)

const items = computed(() =>
  props.procurement.documents.items.filter((it) => it.lifecycle_state !== 'CANCELLED'),
)
const expenses = computed(() =>
  props.procurement.documents.expenses.filter((ex) => ex.lifecycle_state !== 'CANCELLED'),
)
const canEdit = computed(() => props.procurement.status === 'OPEN')
const isConsigned = computed(() => props.procurement.documents.settlement?.type === 'ON_SALE')
const isFilled = computed(() => expenses.value.length > 0)

const totalsByCurrency = computed(() => {
  const map: Record<string, number> = {}
  for (const ex of expenses.value) {
    const cur = (ex.currency || 'UZS').toUpperCase()
    map[cur] = (map[cur] ?? 0) + (parseFloat(ex.amount) || 0)
  }
  return map
})

function formatTotal(amount: number, currency: string): string {
  const formatted = amount % 1 === 0
    ? Math.round(amount).toLocaleString('ru-RU')
    : amount.toLocaleString('ru-RU', { maximumFractionDigits: 2 })
  return `${formatted} ${currency}`
}

function openAdd(): void { editingExpenseId.value = null; editSheetOpen.value = true }
function openEdit(id: number): void { editingExpenseId.value = id; editSheetOpen.value = true }

function toAction(ex: Expense): ActionExpense {
  return {
    id: ex.id,
    expense_type: ex.expense_type,
    amount: parseFloat(ex.amount) || 0,
    currency: ex.currency,
    fx_rate: ex.fx_rate,
    allocation_method: ex.allocation_method,
    target_item_ids: ex.target_item_ids,
  }
}

function onSheetSave(payload: ActionExpense): void {
  const base = expenses.value.map(toAction)
  if (payload.id) {
    emit('update-expenses', base.map((ex) => (ex.id === payload.id ? payload : ex)))
  } else {
    emit('update-expenses', [...base, payload])
  }
}

function onSheetDelete(expenseId: number): void {
  emit('delete-expense', expenseId)
}
</script>

<template>
  <Card class="gap-0 rounded-[14px] border-neutral-200 bg-surface py-0 shadow-none">
    <CardHeader class="flex flex-row items-center justify-between gap-3 px-4 py-3.5">
      <CardTitle class="text-base">Расходы</CardTitle>
      <div class="flex items-center gap-2">
        <span v-if="isConsigned" class="text-xs font-medium uppercase tracking-wide text-neutral-400">недоступно</span>
        <template v-else>
          <span class="text-sm font-medium tabular-nums text-neutral-500">{{ expenses.length }}</span>
          <CheckCircle2 v-if="isFilled" class="size-[18px] text-positive" />
        </template>
      </div>
    </CardHeader>

    <CardContent class="flex flex-col gap-3 px-4 pb-4">
      <div
        v-if="isConsigned"
        class="flex items-start gap-2 rounded-[10px] bg-neutral-50 px-3.5 py-3 text-sm text-neutral-500"
      >
        <Info class="mt-0.5 size-4 shrink-0" />
        <span>Расходы недоступны для прихода на реализации.</span>
      </div>

      <template v-else>
        <p v-if="!expenses.length" class="py-4 text-center text-sm text-neutral-500">
          Нет дополнительных расходов.
        </p>

        <div v-else class="flex flex-col gap-2">
          <ProcurementExpenseRow
            v-for="expense in expenses"
            :key="expense.id"
            :expense="expense"
            :items="items"
            :is-editable="canEdit && !expense.locked_reason"
            @click="openEdit(expense.id)"
          />
        </div>

        <div
          v-if="Object.keys(totalsByCurrency).length"
          class="flex items-center justify-between gap-3 border-t border-neutral-200 pt-3"
        >
          <span class="text-sm text-neutral-500">Итого расходов</span>
          <span class="text-right text-base font-semibold tabular-nums text-foreground">
            <template v-for="(amount, currency, idx) in totalsByCurrency" :key="currency">
              <span v-if="idx > 0" class="text-neutral-300"> · </span>{{ formatTotal(amount, currency) }}
            </template>
          </span>
        </div>

        <button
          type="button"
          class="flex w-full items-center justify-center gap-2 rounded-[10px] border border-dashed border-neutral-300 px-3.5 py-3 text-sm font-medium text-green-700 transition-colors hover:bg-green-50/40"
          @click="openAdd"
        >
          <Plus class="size-4" />
          Добавить расход
        </button>
      </template>
    </CardContent>
  </Card>

  <ProcurementExpenseEditSheet
    v-model:open="editSheetOpen"
    :procurement="procurement"
    :editing-expense-id="editingExpenseId"
    @save="onSheetSave"
    @delete="onSheetDelete"
  />
</template>
