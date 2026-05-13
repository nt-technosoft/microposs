<script setup lang="ts">
import { Plus, RefreshCcw, Trash2 } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import BaseSelect from '@/components/base/BaseSelect.vue'
import type { ExpenseRow } from '@/modules/intake/types'

interface Option {
  value: string
  label: string
}

const props = defineProps<{
  expenses: ExpenseRow[]
  expenseTypeOptions: Option[]
  allocationOptions: Option[]
  normalizeCurrency: (value: unknown) => string
  showFxField: (currency: string) => boolean
  formatCurrencyTotalLabel: (currency: string) => string
}>()

const emit = defineEmits<{
  addExpense: []
  removeExpense: [rowId: string]
  updateExpense: [rowId: string, field: keyof Omit<ExpenseRow, 'id'>, value: string]
  toggleExpenseCurrency: [rowId: string]
}>()

const { t } = useI18n()
</script>

<template>
  <section class="form-section">
    <div class="section-header">
      <h2 class="section-title">{{ t('procurements.create.procurementExpenses') }}</h2>
      <button class="btn-add-small" type="button" @click="emit('addExpense')">
        <Plus :size="14" :stroke-width="2.5" />
        {{ t('common.add') }}
      </button>
    </div>

    <div v-if="expenses.length === 0" class="empty-inline">
      {{ t('procurements.create.noExtraExpenses') }}
    </div>

    <div v-for="expense in expenses" :key="expense.id" class="participant-card">
      <div class="participant-header">
        <span class="participant-num">{{ t('procurements.create.expense') }}</span>
        <button class="btn-delete" type="button" :aria-label="t('procurements.create.removeExpense')" @click="emit('removeExpense', expense.id)">
          <Trash2 :size="16" :stroke-width="2" />
        </button>
      </div>
      <div class="field-row">
        <div class="field-group flex-1">
          <label class="field-label">{{ t('common.type') }}</label>
          <BaseSelect
            :model-value="expense.expense_type"
            :options="expenseTypeOptions"
            :title="t('procurements.create.expenseType')"
            @update:model-value="(value) => emit('updateExpense', expense.id, 'expense_type', String(value))"
          />
        </div>
        <div class="field-group flex-1">
          <label class="field-label">{{ t('procurements.create.allocateBy') }}</label>
          <BaseSelect
            :model-value="expense.allocation_method"
            :options="allocationOptions"
            :title="t('procurements.create.allocationMethod')"
            @update:model-value="(value) => emit('updateExpense', expense.id, 'allocation_method', String(value))"
          />
        </div>
      </div>
      <div class="field-group">
        <label class="field-label">{{ t('common.amount') }}</label>
        <div class="money-field">
          <input
            type="number"
            class="input-field money-input"
            :value="expense.amount"
            min="0"
            placeholder="0"
            @input="emit('updateExpense', expense.id, 'amount', ($event.target as HTMLInputElement).value)"
          />
          <button
            type="button"
            class="currency-toggle"
            :aria-label="t('procurements.create.changeExpenseCurrency', { currency: normalizeCurrency(expense.currency) })"
            @click="emit('toggleExpenseCurrency', expense.id)"
          >
            <span class="currency-toggle-code">{{ normalizeCurrency(expense.currency) }}</span>
            <RefreshCcw :size="14" :stroke-width="2" />
          </button>
        </div>
      </div>
      <div v-if="showFxField(expense.currency)" class="field-group">
        <label class="field-label">{{ t('procurements.create.rateLabel', { currency: formatCurrencyTotalLabel(expense.currency) }) }}</label>
        <input
          type="number"
          class="input-field"
          :value="expense.fx_rate"
          min="0"
          step="0.0001"
          :placeholder="t('procurements.create.enterRate')"
          @input="emit('updateExpense', expense.id, 'fx_rate', ($event.target as HTMLInputElement).value)"
        />
      </div>
      <div class="field-group">
        <label class="field-label">{{ t('common.comment') }}</label>
        <input class="input-field" :value="expense.notes" @input="emit('updateExpense', expense.id, 'notes', ($event.target as HTMLInputElement).value)" />
      </div>
    </div>
  </section>
</template>

<style scoped>
.form-section { display:grid; gap: var(--space-3); }
.section-header, .participant-header { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); flex-wrap: wrap; }
.section-title { font-size: var(--text-base); font-weight: var(--font-semibold); }
.btn-add-small { min-height: 36px; display:inline-flex; align-items:center; justify-content:center; gap: var(--space-1); padding: 0 var(--space-3); border-radius: var(--radius-md); border:1px solid var(--color-border-default); background: var(--color-bg-elevated); color: var(--color-brand-600); font-size: var(--text-sm); font-weight: var(--font-medium); white-space: nowrap; }
.empty-inline { color: var(--color-text-secondary); font-size: var(--text-sm); }
.participant-card { display:grid; gap: var(--space-3); padding: var(--space-4); border-radius: var(--radius-lg); border:1px solid var(--color-border-subtle); background: var(--color-bg-elevated); }
.participant-num { font-weight: var(--font-semibold); }
.btn-delete { display:inline-flex; align-items:center; gap: var(--space-1); color: var(--color-brand-500); }
.field-row { display:flex; gap: var(--space-3); }
.field-group { display:grid; gap: var(--space-2); }
.field-label { color: var(--color-text-secondary); font-size: var(--text-sm); }
.flex-1 { flex:1; }
.input-field { width:100%; min-height:44px; border:1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-elevated); padding: var(--space-3) var(--space-4); text-align:left; }
.money-field { position: relative; }
.money-input { padding-right: 88px; }
.currency-toggle { position: absolute; top: 50%; right: 6px; transform: translateY(-50%); height: 30px; display:inline-flex; align-items:center; justify-content:center; gap: 6px; padding: 0 10px; border:1px solid var(--color-border-default); border-radius: calc(var(--radius-md) - 2px); background: var(--color-bg-primary); color: var(--color-text-primary); font-weight: var(--font-semibold); white-space: nowrap; z-index: 1; }
.currency-toggle-code { font-size: var(--text-sm); line-height: 1; }

@media (max-width: 520px) {
  .field-row { flex-direction: column; }
  .money-input { padding-right: 82px; }
  .currency-toggle { right: 5px; padding: 0 8px; }
}
</style>
