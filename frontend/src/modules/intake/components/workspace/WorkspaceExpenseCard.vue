<script setup lang="ts">
import { RefreshCcw, Trash2 } from 'lucide-vue-next'
import BaseSelect from '@/components/base/BaseSelect.vue'
import type { DraftExpenseRow, ItemTarget, SelectOption } from './types'

defineProps<{
  expense: DraftExpenseRow
  error?: string | null
  expenseTypeOptions: SelectOption[]
  allocationOptions: SelectOption[]
  itemTargets: ItemTarget[]
  hasUnsavedLines: boolean
  showFxField: (currency: string) => boolean
  formatCurrencyTotalLabel: (currency: string) => string
}>()

const emit = defineEmits<{
  remove: [expenseId: string]
  update: [expenseId: string, field: 'expense_type' | 'amount' | 'currency' | 'fx_rate' | 'allocation_method' | 'notes' | 'target_item_ids', value: string | number[]]
  toggleCurrency: [expenseId: string]
  toggleTarget: [expenseId: string, itemId: number]
  setAllTargets: [expenseId: string]
}>()
</script>

<template>
  <div class="expense-card" :class="{ locked: expense.locked_reason, invalid: Boolean(error) }">
    <div class="expense-head">
      <strong>Расход</strong>
      <button
        v-if="!expense.locked_reason"
        class="icon-danger"
        type="button"
        aria-label="Удалить расход"
        @click="emit('remove', expense.id)"
      >
        <Trash2 :size="16" :stroke-width="2" />
      </button>
    </div>

    <label class="field-group">
      <span class="field-label">Тип</span>
      <BaseSelect
        :model-value="expense.expense_type"
        :options="expenseTypeOptions"
        title="Тип расхода"
        :disabled="Boolean(expense.locked_reason)"
        @update:model-value="(value) => emit('update', expense.id, 'expense_type', String(value))"
      />
    </label>

    <div class="field-row">
      <label class="field-group">
        <span class="field-label">Разносить</span>
        <BaseSelect
          :model-value="expense.allocation_method"
          :options="allocationOptions"
          title="Метод распределения"
          :disabled="Boolean(expense.locked_reason)"
          @update:model-value="(value) => emit('update', expense.id, 'allocation_method', String(value))"
        />
      </label>

      <label class="field-group">
        <span class="field-label">Сумма</span>
        <div class="money-field">
          <input
            class="input-field money-input"
            type="number"
            min="0"
            placeholder="0"
            :value="expense.amount"
            :disabled="Boolean(expense.locked_reason)"
            @input="(event) => emit('update', expense.id, 'amount', (event.target as HTMLInputElement).value)"
          />
          <button class="currency-toggle" type="button" :disabled="Boolean(expense.locked_reason)" @click="emit('toggleCurrency', expense.id)">
            <span>{{ expense.currency }}</span>
            <RefreshCcw :size="13" :stroke-width="2" />
          </button>
        </div>
      </label>
    </div>

    <label v-if="showFxField(expense.currency)" class="field-group">
      <span class="field-label">Курс {{ formatCurrencyTotalLabel(expense.currency) }}</span>
      <input
        class="input-field"
        type="number"
        min="0"
        step="0.0001"
        :value="expense.fx_rate"
        :disabled="Boolean(expense.locked_reason)"
        @input="(event) => emit('update', expense.id, 'fx_rate', (event.target as HTMLInputElement).value)"
      />
    </label>

    <label class="field-group">
      <span class="field-label">Комментарий</span>
      <input
        class="input-field"
        type="text"
        :value="expense.notes"
        :disabled="Boolean(expense.locked_reason)"
        @input="(event) => emit('update', expense.id, 'notes', (event.target as HTMLInputElement).value)"
      />
    </label>

    <div class="target-box">
      <div class="target-head">
        <strong>Распределение по товарам</strong>
        <button class="text-action" type="button" :disabled="Boolean(expense.locked_reason)" @click="emit('setAllTargets', expense.id)">
          На все товары
        </button>
      </div>
      <p v-if="hasUnsavedLines" class="target-hint">Для точного выбора товаров сначала сохраните их, чтобы они получили ID.</p>
      <div v-if="itemTargets.length" class="target-chips">
        <button
          v-for="target in itemTargets"
          :key="target.id"
          class="target-chip"
          :class="{ active: expense.target_item_ids.includes(target.id) }"
          type="button"
          :disabled="Boolean(expense.locked_reason)"
          @click="emit('toggleTarget', expense.id, target.id)"
        >
          {{ target.label }}
        </button>
      </div>
      <p v-else class="target-hint">Сейчас расход будет распределён на все сохранённые товары.</p>
    </div>

    <p v-if="expense.locked_reason" class="locked-note">Расход уже имеет финансовые или складские факты и не редактируется напрямую.</p>
    <p v-if="error" class="error-note">{{ error }}</p>
  </div>
</template>

<style scoped>
.expense-card {
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-primary);
}

.expense-card.locked {
  background: var(--color-bg-elevated);
}

.expense-card.invalid {
  border-color: rgba(239, 68, 68, 0.42);
}

.expense-head,
.target-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.icon-danger {
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid rgba(239, 68, 68, 0.18);
  border-radius: var(--radius-md);
  background: rgba(239, 68, 68, 0.06);
  color: var(--color-danger);
  flex: 0 0 auto;
}

.field-row {
  display: grid;
  grid-template-columns: minmax(112px, 0.86fr) minmax(0, 1.14fr);
  gap: 8px;
}

.field-group {
  min-width: 0;
  display: grid;
  gap: 6px;
}

.field-label {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.input-field {
  width: 100%;
  min-height: 44px;
  padding: 0 12px;
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
}

.input-field:disabled {
  opacity: 0.72;
  background: var(--color-bg-sunken);
}

.money-field {
  position: relative;
}

.money-input {
  padding-right: 82px;
}

.currency-toggle {
  position: absolute;
  top: 50%;
  right: 6px;
  transform: translateY(-50%);
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 0 8px;
  border: 1px solid var(--color-border-default);
  border-radius: calc(var(--radius-md) - 2px);
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  font-weight: var(--font-semibold);
}

.target-box {
  display: grid;
  gap: 8px;
  padding: 10px;
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
}

.target-head strong {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
}

.text-action {
  min-height: auto;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--color-brand-700);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.target-hint,
.locked-note,
.error-note {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.4;
}

.error-note {
  color: var(--color-danger);
}

.target-chips {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.target-chip {
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid var(--color-border-subtle);
  border-radius: 999px;
  background: var(--color-bg-primary);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.target-chip.active {
  border-color: var(--color-brand-500);
  background: var(--color-brand-50);
  color: var(--color-brand-700);
}
</style>
