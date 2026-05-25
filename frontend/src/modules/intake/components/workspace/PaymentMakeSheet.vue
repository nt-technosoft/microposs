<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { fetchCashAccounts, type CashAccountRecord } from '@/api/finance'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

const props = defineProps<{
  open: boolean
  procurement: ProcurementWorkspacePayload
  defaultAmount?: string
  paymentType: 'cost' | 'payable' | 'schedule-entry'
  payableId?: number
  scheduleEntryId?: number
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  dispatch: [actionKey: string, payload: Record<string, unknown>]
}>()

const router = useRouter()

const settlement = computed(() => props.procurement.documents.settlement)
const obligationCurrency = computed(() =>
  (settlement.value?.currency_of_obligation ?? 'UZS').toUpperCase()
)

const amount = ref('')
const notes = ref('')
const cashAccountId = ref<number | null>(null)
const cashAccounts = ref<CashAccountRecord[]>([])
const isLoadingAccounts = ref(false)

const selectedAccount = computed(() =>
  cashAccounts.value.find((a) => a.id === cashAccountId.value) ?? null
)
const currencyMismatch = computed(() =>
  !!selectedAccount.value &&
  selectedAccount.value.currency.toUpperCase() !== obligationCurrency.value
)

async function loadAccounts(): Promise<void> {
  isLoadingAccounts.value = true
  try { cashAccounts.value = await fetchCashAccounts() }
  catch { cashAccounts.value = [] }
  finally { isLoadingAccounts.value = false }
}

watch(() => props.open, (isOpen) => {
  if (!isOpen) return
  amount.value = props.defaultAmount ?? ''
  notes.value = ''
  cashAccountId.value = cashAccounts.value[0]?.id ?? null
  if (!cashAccounts.value.length) loadAccounts()
})

function openExchange(): void {
  const remaining = settlement.value?.remaining_amount ?? ''
  router.push({
    path: '/finance/currency-exchange',
    query: {
      from_currency: selectedAccount.value?.currency ?? 'UZS',
      to_currency: obligationCurrency.value,
      amount: String(remaining),
    },
  })
  emit('update:open', false)
}

function onSave(): void {
  const base: Record<string, unknown> = {
    cash_account_id: cashAccountId.value,
    amount: parseFloat(amount.value) || 0,
    currency: obligationCurrency.value,
    fx_rate: '1',
    notes: notes.value,
  }
  if (props.paymentType === 'cost') {
    emit('dispatch', 'PAY_COSTS', base)
  } else {
    emit('dispatch', 'PAY_SUPPLIER_PAYABLE', {
      ...base,
      payable_id: props.payableId,
      ...(props.scheduleEntryId ? { schedule_entry_id: props.scheduleEntryId } : {}),
    })
  }
  emit('update:open', false)
}

const canSave = () =>
  !!(amount.value && parseFloat(amount.value) > 0 && cashAccountId.value && !currencyMismatch.value)
</script>

<template>
  <AppBottomSheet :open="open" title="Платёж" @close="emit('update:open', false)">
    <div class="sheet-body">
      <div class="section-label">Сумма</div>
      <div class="amount-row">
        <input class="input-field amount-input" type="number" min="0" step="0.01" v-model="amount" placeholder="0.00" inputmode="decimal" />
        <span class="currency-badge">{{ obligationCurrency }}</span>
      </div>

      <div class="section-label">Касса</div>
      <div v-if="isLoadingAccounts" class="loading-text">Загрузка…</div>
      <div v-else-if="!cashAccounts.length" class="empty-text">Нет активных касс</div>
      <div v-else class="accounts-list">
        <button
          v-for="acc in cashAccounts"
          :key="acc.id"
          class="account-btn"
          :class="{ active: acc.id === cashAccountId }"
          type="button"
          @click="cashAccountId = acc.id"
        >
          <span class="acc-name">{{ acc.name }}</span>
          <span class="acc-balance">{{ parseFloat(acc.balance).toLocaleString('ru-RU') }} {{ acc.currency }}</span>
        </button>
      </div>

      <div v-if="currencyMismatch" class="mismatch-warning">
        <span>Касса в {{ selectedAccount?.currency }} — обязательство в {{ obligationCurrency }}. Сначала конвертируйте валюту.</span>
        <button class="convert-btn" type="button" @click="openExchange">Конвертировать →</button>
      </div>

      <div class="section-label">Примечание (необязательно)</div>
      <input class="input-field" type="text" v-model="notes" placeholder="Комментарий к платежу" />

      <button class="primary-btn" type="button" :disabled="!canSave()" @click="onSave">
        Сохранить платёж
      </button>
    </div>
  </AppBottomSheet>
</template>

<style scoped>
.sheet-body { display: grid; gap: var(--space-3); }
.section-label { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: .04em; }
.input-field { width: 100%; min-height: 44px; padding: 0 var(--space-3); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); font-size: var(--text-sm); }
.loading-text { font-size: var(--text-sm); color: var(--color-text-secondary); }
.empty-text { font-size: var(--text-sm); color: var(--color-text-secondary); }
.accounts-list { display: grid; gap: var(--space-2); }
.account-btn { display: flex; align-items: center; justify-content: space-between; width: 100%; padding: var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-primary); cursor: pointer; }
.account-btn.active { border-color: var(--color-brand-600); background: var(--color-brand-50); }
.acc-name { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.acc-balance { font-size: var(--text-xs); color: var(--color-text-secondary); font-variant-numeric: tabular-nums; }
.primary-btn { min-height: 48px; border: 0; border-radius: var(--radius-lg); background: var(--color-brand-500); color: var(--color-text-inverse); font-weight: var(--font-semibold); cursor: pointer; }
.primary-btn:disabled { opacity: .55; cursor: not-allowed; }
.amount-row { display: flex; align-items: center; gap: var(--space-2); }
.amount-input { flex: 1; min-height: 44px; padding: 0 var(--space-3); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); font-size: var(--text-sm); font-variant-numeric: tabular-nums; }
.currency-badge { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-secondary); min-width: 3ch; flex-shrink: 0; }
.mismatch-warning { display: grid; gap: var(--space-2); padding: var(--space-3); background: color-mix(in srgb, var(--color-warning) 10%, transparent); border-radius: var(--radius-md); border: 1px solid color-mix(in srgb, var(--color-warning) 25%, transparent); font-size: var(--text-sm); color: var(--color-text-primary); }
.convert-btn { padding: var(--space-2) var(--space-3); border: 1px solid var(--color-warning); border-radius: var(--radius-md); background: transparent; color: var(--color-warning); font-size: var(--text-sm); font-weight: var(--font-semibold); cursor: pointer; }
</style>
