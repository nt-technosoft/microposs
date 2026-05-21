<script setup lang="ts">
import { ref, watch } from 'vue'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import MoneyCurrencyInput from '@/components/forms/MoneyCurrencyInput.vue'
import { fetchCashAccounts, type CashAccountRecord } from '@/api/finance'
import { useFxRate } from '@/composables/useFxRate'
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

const amount = ref('')
const currency = ref<'UZS' | 'USD'>('UZS')
const fxRateLocal = ref('1')
const notes = ref('')
const cashAccountId = ref<number | null>(null)
const cashAccounts = ref<CashAccountRecord[]>([])
const isLoadingAccounts = ref(false)

const { rate: fetchedFx, load: loadFx } = useFxRate()

async function loadAccounts(): Promise<void> {
  isLoadingAccounts.value = true
  try { cashAccounts.value = await fetchCashAccounts() }
  catch { cashAccounts.value = [] }
  finally { isLoadingAccounts.value = false }
}

watch(fetchedFx, (r) => { if (r) fxRateLocal.value = r })
watch(currency, async (cur) => {
  if (cur === 'USD') { if (fxRateLocal.value === '1' || !fxRateLocal.value) await loadFx() }
  else fxRateLocal.value = '1'
})

watch(() => props.open, (isOpen) => {
  if (!isOpen) return
  amount.value = props.defaultAmount ?? ''
  currency.value = 'UZS'
  fxRateLocal.value = '1'
  notes.value = ''
  cashAccountId.value = cashAccounts.value[0]?.id ?? null
  if (!cashAccounts.value.length) loadAccounts()
})

function onSave(): void {
  const base: Record<string, unknown> = {
    cash_account_id: cashAccountId.value,
    amount: parseFloat(amount.value) || 0,
    currency: currency.value,
    fx_rate: fxRateLocal.value,
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

const canSave = () => !!(amount.value && parseFloat(amount.value) > 0 && cashAccountId.value)
</script>

<template>
  <AppBottomSheet :open="open" title="Платёж" @close="emit('update:open', false)">
    <div class="sheet-body">
      <div class="section-label">Сумма</div>
      <MoneyCurrencyInput v-model:model-value="amount" v-model:currency="currency" />

      <template v-if="currency !== 'UZS'">
        <div class="section-label">Курс USD/UZS</div>
        <input class="input-field" type="number" min="0" step="0.01" :value="fxRateLocal" @input="fxRateLocal = ($event.target as HTMLInputElement).value" />
      </template>

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
</style>
