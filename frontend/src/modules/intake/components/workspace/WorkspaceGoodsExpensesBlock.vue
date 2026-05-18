<script setup lang="ts">
import { AlertCircle, Plus } from 'lucide-vue-next'
import type { ProductVariant } from '@/types/models'
import { formatPrice } from '@/utils/currency'
import WorkspaceExpenseCard from './WorkspaceExpenseCard.vue'
import WorkspaceItemRow from './WorkspaceItemRow.vue'
import type { DraftExpenseRow, DraftLineRow, ItemTarget, SelectOption } from './types'

defineProps<{
  lines: DraftLineRow[]
  expenses: DraftExpenseRow[]
  primaryCurrency: 'UZS' | 'USD'
  lineErrors: Record<string, string>
  expenseErrors: Record<string, string>
  goodsTotal: number
  expensesTotal: number
  procurementTotal: number
  isLoading: boolean
  isSaving: boolean
  error: string | null
  expenseTypeOptions: SelectOption[]
  allocationOptions: SelectOption[]
  itemTargets: ItemTarget[]
  hasUnsavedLines: boolean
  variantDisplay: (variant: ProductVariant) => string
  showFxField: (currency: string) => boolean
  formatCurrencyTotalLabel: (currency: string) => string
}>()

const emit = defineEmits<{
  updatePrimaryCurrency: [currency: 'UZS' | 'USD']
  addLine: []
  addExpense: []
  openQuickProduct: []
  openVariantPicker: [lineId: string]
  removeLine: [lineId: string]
  updateLine: [lineId: string, field: 'variant' | 'quantity' | 'cost_per_unit' | 'currency' | 'fx_rate', value: string | ProductVariant | null]
  toggleLineCurrency: [lineId: string]
  removeExpense: [expenseId: string]
  updateExpense: [expenseId: string, field: 'expense_type' | 'amount' | 'currency' | 'fx_rate' | 'allocation_method' | 'notes' | 'target_item_ids', value: string | number[]]
  toggleExpenseCurrency: [expenseId: string]
  toggleExpenseTarget: [expenseId: string, itemId: number]
  setExpenseAllTargets: [expenseId: string]
  save: []
}>()
</script>

<template>
  <div class="goods-block">
    <div class="goods-summary">
      <div>
        <span>Валюта прихода</span>
        <div class="currency-choice" role="group" aria-label="Валюта прихода">
          <button type="button" :class="{ active: primaryCurrency === 'UZS' }" @click="emit('updatePrimaryCurrency', 'UZS')">UZS</button>
          <button type="button" :class="{ active: primaryCurrency === 'USD' }" @click="emit('updatePrimaryCurrency', 'USD')">USD</button>
        </div>
      </div>
      <div>
        <span>Товары</span>
        <strong>{{ lines.length }}</strong>
      </div>
      <div>
        <span>Расходы</span>
        <strong>{{ expenses.length }}</strong>
      </div>
      <div>
        <span>Итого</span>
        <strong>{{ formatPrice(procurementTotal, primaryCurrency) }}</strong>
      </div>
    </div>

    <div v-if="isLoading" class="inline-state">Загрузка прихода…</div>

    <section class="workspace-section">
      <div class="section-header">
        <h2>Товары</h2>
      </div>

      <div v-if="lines.length === 0" class="empty-inline">Товары пока не добавлены.</div>

      <div v-else class="line-list">
        <WorkspaceItemRow
          v-for="line in lines"
          :key="line.id"
          :line="line"
          :error="lineErrors[line.id]"
          :can-remove="lines.length > 1"
          :variant-display="variantDisplay"
          @open-variant-picker="emit('openVariantPicker', $event)"
          @remove="emit('removeLine', $event)"
          @update="(...args) => emit('updateLine', ...args)"
          @toggle-currency="emit('toggleLineCurrency', $event)"
        />
      </div>

      <div class="bottom-actions">
        <button class="soft-action action-wide" type="button" @click="emit('addLine')">
          <Plus :size="14" :stroke-width="2.4" />
          Добавить товар
        </button>
        <button class="soft-action action-wide" type="button" @click="emit('openQuickProduct')">
          <Plus :size="14" :stroke-width="2.4" />
          Новый товар
        </button>
      </div>
    </section>

    <section class="workspace-section">
      <div class="section-header">
        <h2>Расходы прихода</h2>
      </div>

      <div v-if="expenses.length === 0" class="empty-inline">Дополнительных расходов нет.</div>

      <div v-else class="expense-list">
        <WorkspaceExpenseCard
          v-for="expense in expenses"
          :key="expense.id"
          :expense="expense"
          :error="expenseErrors[expense.id]"
          :expense-type-options="expenseTypeOptions"
          :allocation-options="allocationOptions"
          :item-targets="itemTargets"
          :has-unsaved-lines="hasUnsavedLines"
          :show-fx-field="showFxField"
          :format-currency-total-label="formatCurrencyTotalLabel"
          @remove="emit('removeExpense', $event)"
          @update="(...args) => emit('updateExpense', ...args)"
          @toggle-currency="emit('toggleExpenseCurrency', $event)"
          @toggle-target="(...args) => emit('toggleExpenseTarget', ...args)"
          @set-all-targets="emit('setExpenseAllTargets', $event)"
        />
      </div>

      <div class="bottom-actions bottom-actions-single">
        <button class="soft-action action-wide" type="button" @click="emit('addExpense')">
          <Plus :size="14" :stroke-width="2.4" />
          Добавить расход
        </button>
      </div>
    </section>

    <section class="totals-panel">
      <div>
        <span>Товары</span>
        <strong>{{ formatPrice(goodsTotal, primaryCurrency) }}</strong>
      </div>
      <div>
        <span>Расходы</span>
        <strong>{{ formatPrice(expensesTotal, primaryCurrency) }}</strong>
      </div>
      <div class="grand">
        <span>Общая себестоимость</span>
        <strong>{{ formatPrice(procurementTotal, primaryCurrency) }}</strong>
      </div>
    </section>

    <div v-if="error" class="error-box">
      <AlertCircle :size="18" :stroke-width="1.75" />
      <span>{{ error }}</span>
    </div>

    <button class="primary-action" type="button" :disabled="isSaving" @click="emit('save')">
      {{ isSaving ? 'Сохранение…' : 'Сохранить товары и расходы' }}
    </button>
  </div>
</template>

<style scoped>
.goods-block,
.workspace-section,
.line-list,
.expense-list {
  display: grid;
  gap: 12px;
}

.goods-summary,
.totals-panel {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
}

.goods-summary > div,
.totals-panel > div {
  display: grid;
  gap: 4px;
  padding: 12px;
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
}

.goods-summary span,
.totals-panel span {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.goods-summary strong,
.totals-panel strong {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-variant-numeric: tabular-nums;
}

.currency-choice {
  display: inline-grid;
  grid-template-columns: repeat(2, minmax(44px, 1fr));
  gap: 4px;
  padding: 3px;
  border: 1px solid var(--color-border-subtle);
  border-radius: 999px;
  background: var(--color-bg-primary);
}

.currency-choice button {
  min-height: 28px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.currency-choice button.active {
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.section-header h2 {
  margin: 0;
  color: var(--color-text-primary);
  font-size: var(--text-lg);
}

.bottom-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  padding-top: 6px;
}

.bottom-actions-single {
  grid-template-columns: 1fr;
}

.soft-action {
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 10px;
  border: 1px solid var(--color-border-subtle);
  border-radius: 999px;
  background: var(--color-bg-primary);
  color: var(--color-brand-700);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.action-wide {
  width: 100%;
}

.empty-inline,
.inline-state {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.4;
}

.totals-panel .grand {
  background: var(--color-brand-50);
}

.error-box {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--color-danger-bg);
  color: var(--color-danger);
  font-size: var(--text-sm);
  line-height: 1.4;
}

.primary-action {
  min-height: 48px;
  border: 0;
  border-radius: var(--radius-lg);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  font-weight: var(--font-semibold);
}

.primary-action:disabled {
  opacity: 0.62;
}

@media (max-width: 640px) {
  .goods-summary,
  .totals-panel {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .section-header {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
