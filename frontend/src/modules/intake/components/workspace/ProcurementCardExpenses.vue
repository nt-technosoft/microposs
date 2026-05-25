<script setup lang="ts">
import { ref, computed } from 'vue'
import { CheckCircle, Plus, Info } from 'lucide-vue-next'
import ProcurementExpenseRow from './ProcurementExpenseRow.vue'
import ProcurementExpenseEditSheet from './ProcurementExpenseEditSheet.vue'
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
    : amount.toFixed(2)
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
  <div class="expenses-card">
    <div class="card-header">
      <span class="card-title">Расходы</span>
      <div class="header-right">
        <template v-if="isConsigned">
          <span class="disabled-badge">disabled</span>
        </template>
        <template v-else>
          <span class="item-count">{{ expenses.length }}</span>
          <CheckCircle v-if="isFilled" class="status-ok" :size="18" :stroke-width="2" />
        </template>
      </div>
    </div>

    <div v-if="isConsigned" class="consigned-notice">
      <Info :size="15" :stroke-width="2" class="notice-icon" />
      <span>Расходы недоступны для прихода на реализации.</span>
    </div>

    <template v-else>
      <div v-if="!expenses.length" class="empty-state">Нет дополнительных расходов.</div>

      <div v-else class="expenses-list">
        <ProcurementExpenseRow
          v-for="expense in expenses"
          :key="expense.id"
          :expense="expense"
          :items="items"
          :is-editable="canEdit && !expense.locked_reason"
          @click="openEdit(expense.id)"
          @delete="onSheetDelete"
        />
      </div>

      <template v-if="Object.keys(totalsByCurrency).length">
        <div v-for="(amount, currency) in totalsByCurrency" :key="currency" class="totals-row">
          <span class="totals-label">Итого расходов</span>
          <span class="totals-value">{{ formatTotal(amount, currency) }}</span>
        </div>
      </template>

      <button class="add-btn" type="button" @click="openAdd">
        <Plus :size="14" :stroke-width="2.5" />
        Добавить расход
      </button>
    </template>
  </div>

  <ProcurementExpenseEditSheet
    v-model:open="editSheetOpen"
    :procurement="procurement"
    :editing-expense-id="editingExpenseId"
    @save="onSheetSave"
    @delete="onSheetDelete"
  />
</template>

<style scoped>
.expenses-card {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
}

.card-header { display: flex; align-items: center; justify-content: space-between; }

.card-title { font-size: var(--text-base); font-weight: var(--font-semibold); color: var(--color-text-primary); }

.header-right { display: flex; align-items: center; gap: var(--space-2); }

.item-count { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-secondary); }

.disabled-badge { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: .04em; }

.status-ok { color: var(--color-success); }

.consigned-notice {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  padding: var(--space-3);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.4;
}

.notice-icon { flex-shrink: 0; margin-top: 1px; }

.empty-state { padding: var(--space-4) 0; text-align: center; color: var(--color-text-secondary); font-size: var(--text-sm); }

.expenses-list { display: grid; gap: var(--space-2); }

.totals-row { display: flex; align-items: center; justify-content: space-between; padding: var(--space-2) var(--space-3); background: var(--color-bg-secondary); border-radius: var(--radius-md); }

.totals-label { font-size: var(--text-sm); color: var(--color-text-secondary); }

.totals-value { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); font-variant-numeric: tabular-nums; }

.add-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  width: 100%;
  padding: var(--space-3);
  border: 1px dashed var(--color-border-subtle);
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-brand-700);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  cursor: pointer;
}
</style>
