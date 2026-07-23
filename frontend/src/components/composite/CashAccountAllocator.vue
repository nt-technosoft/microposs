<script setup lang="ts">
import { computed } from 'vue'
import { Plus, Trash2 } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import type { CashAccountRecord } from '@/api/finance'

export interface CashAllocationRow {
  id: string
  cash_account_id: number | null
  amount: string
  currency: string
}

const props = defineProps<{
  accounts: CashAccountRecord[]
  rows: CashAllocationRow[]
}>()

const emit = defineEmits<{
  updateRows: [rows: CashAllocationRow[]]
}>()

const { t } = useI18n()

const accountOptions = computed(() => props.accounts.filter((account) => account.is_active !== false))

function patchRow(rowId: string, patch: Partial<CashAllocationRow>): void {
  emit('updateRows', props.rows.map((row) => row.id === rowId ? { ...row, ...patch } : row))
}

function addRow(): void {
  const first = accountOptions.value[0]
  emit('updateRows', [
    ...props.rows,
    {
      id: crypto.randomUUID(),
      cash_account_id: first?.id ?? null,
      amount: '',
      currency: first?.currency ?? 'UZS',
    },
  ])
}

function removeRow(rowId: string): void {
  emit('updateRows', props.rows.filter((row) => row.id !== rowId))
}

function onAccountChange(rowId: string, rawValue: string): void {
  const accountId = Number(rawValue)
  const account = props.accounts.find((item) => item.id === accountId)
  patchRow(rowId, {
    cash_account_id: Number.isFinite(accountId) ? accountId : null,
    currency: account?.currency ?? 'UZS',
  })
}
</script>

<template>
  <section class="allocator">
    <div class="allocator-head">
      <span>{{ t('finance.cashAccounts') }}</span>
      <button type="button" @click="addRow">
        <Plus :size="14" :stroke-width="2.25" />
        {{ t('common.add') }}
      </button>
    </div>

    <div v-if="rows.length === 0" class="empty-row">
      {{ t('suppliers.allocationsEmpty') }}
    </div>

    <div v-for="row in rows" :key="row.id" class="allocation-row">
      <select
        class="input-field"
        :value="row.cash_account_id ?? ''"
        @change="onAccountChange(row.id, ($event.target as HTMLSelectElement).value)"
      >
        <option value="" disabled>{{ t('finance.cashAccount') }}</option>
        <option v-for="account in accountOptions" :key="account.id" :value="account.id">
          {{ account.name }} · {{ account.currency }}
        </option>
      </select>
      <input
        class="input-field"
        inputmode="decimal"
        type="number"
        min="0"
        step="0.01"
        :placeholder="t('common.amount')"
        :value="row.amount"
        @input="patchRow(row.id, { amount: ($event.target as HTMLInputElement).value })"
      />
      <span class="currency-pill">{{ row.currency }}</span>
      <button type="button" class="delete-btn" :aria-label="t('common.delete')" @click="removeRow(row.id)">
        <Trash2 :size="16" :stroke-width="2" />
      </button>
    </div>
  </section>
</template>

<style scoped>
.allocator {
  display: grid;
  gap: var(--space-2);
}

.allocator-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.allocator-head span {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  text-transform: uppercase;
}

.allocator-head button {
  min-height: 32px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-default);
  color: var(--color-brand-600);
  font-size: var(--text-sm);
}

.allocation-row {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(82px, 0.8fr) auto 36px;
  gap: var(--space-2);
  align-items: center;
}

.input-field {
  width: 100%;
  min-height: 40px;
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  padding: 0 var(--space-3);
  color: var(--color-text-primary);
}

.currency-pill {
  min-height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 8px;
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.delete-btn {
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  color: var(--color-text-tertiary);
}

.empty-row {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

@media (max-width: 460px) {
  .allocation-row {
    grid-template-columns: minmax(0, 1fr) 36px;
  }

  .allocation-row .input-field,
  .currency-pill {
    grid-column: 1 / -1;
  }

  .delete-btn {
    grid-column: 2;
    grid-row: 1;
    justify-self: end;
  }
}
</style>
