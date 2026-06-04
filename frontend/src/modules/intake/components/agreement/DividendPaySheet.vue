<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { useToast } from '@/composables/useToast'
import { payDividend, type AgreementProfitRow } from '@/api/partnerships'
import { formatPrice } from '@/utils/currency'
import { getApiErrorMessage } from '@/utils/errors'

interface OperatingAccount {
  id: number
  name: string
  currency: string
}

const props = defineProps<{
  open: boolean
  rows: AgreementProfitRow[]
  accounts: OperatingAccount[]
}>()

const emit = defineEmits<{
  close: []
  paid: []
}>()

const toast = useToast()
const selectedKey = ref<string>('')
const amount = ref('')
const fromAccountId = ref<number | null>(null)
const isSaving = ref(false)
const error = ref<string | null>(null)

// Profit is realised in functional UZS, so it is paid out from a UZS account.
const eligibleAccounts = computed(() => props.accounts.filter((a) => a.currency.toUpperCase() === 'UZS'))

function keyOf(row: AgreementProfitRow): string {
  return `${row.procurement_id}:${row.partner_id}`
}

const selectedRow = computed(() => props.rows.find((r) => keyOf(r) === selectedKey.value) ?? null)
const pending = computed(() => Number(selectedRow.value?.pending ?? 0) || 0)
const amountValue = computed(() => Number.parseFloat(String(amount.value).replace(',', '.')) || 0)

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      const first = props.rows[0]
      selectedKey.value = first ? keyOf(first) : ''
      amount.value = first?.pending ?? ''
      fromAccountId.value = eligibleAccounts.value[0]?.id ?? null
      error.value = null
    }
  },
)

watch(selectedKey, () => {
  amount.value = selectedRow.value?.pending ?? ''
})

async function submit() {
  const row = selectedRow.value
  if (!row) {
    error.value = 'Нет накопленной прибыли к выплате'
    return
  }
  if (amountValue.value <= 0) {
    error.value = 'Введите сумму больше 0'
    return
  }
  if (amountValue.value > pending.value + 1e-6) {
    error.value = `Нельзя выплатить больше накопленного (${formatPrice(pending.value, 'UZS')})`
    return
  }
  if (!fromAccountId.value) {
    error.value = 'Выберите операционный счёт-источник'
    return
  }
  isSaving.value = true
  error.value = null
  try {
    await payDividend({
      partner_id: row.partner_id,
      procurement_id: row.procurement_id,
      amount: String(amountValue.value),
      currency: 'UZS',
      paid_from_account_id: fromAccountId.value,
    })
    toast.success('Прибыль выплачена')
    emit('paid')
  } catch (err) {
    error.value = getApiErrorMessage(err, 'Не удалось выплатить прибыль')
    toast.error(error.value)
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <AppBottomSheet :open="open" title="Распределить прибыль" @close="emit('close')">
    <div class="sheet-body">
      <div v-if="!rows.length" class="empty">
        Накопленной прибыли к выплате пока нет.
      </div>

      <template v-else>
        <div class="field">
          <label class="field-label">Кому и по какому приходу</label>
          <select v-model="selectedKey" class="field-input">
            <option v-for="row in rows" :key="keyOf(row)" :value="keyOf(row)">
              {{ row.partner_name }} · приход #{{ row.procurement_id }} · {{ formatPrice(row.pending, 'UZS') }}
            </option>
          </select>
        </div>

        <div class="field">
          <label class="field-label">Операционный счёт (источник)</label>
          <select v-model="fromAccountId" class="field-input">
            <option v-for="acc in eligibleAccounts" :key="acc.id" :value="acc.id">{{ acc.name }}</option>
          </select>
          <p v-if="!eligibleAccounts.length" class="hint">Нет операционного UZS-счёта для выплаты.</p>
        </div>

        <div class="field">
          <label class="field-label">Сумма (UZS)</label>
          <input
            v-model="amount"
            type="number"
            min="0.01"
            step="0.01"
            class="field-input"
            placeholder="0.00"
            inputmode="decimal"
          />
          <p class="hint">Накоплено к выплате: {{ formatPrice(pending, 'UZS') }}</p>
        </div>

        <p v-if="error" class="error-text">{{ error }}</p>

        <button class="btn-primary" :disabled="isSaving" @click="submit">
          {{ isSaving ? 'Выплата…' : 'Выплатить' }}
        </button>
      </template>
    </div>
  </AppBottomSheet>
</template>

<style scoped>
.sheet-body { display: flex; flex-direction: column; gap: var(--space-4); padding: var(--space-4); }
.empty { border: 1px dashed var(--color-border); border-radius: var(--radius-md); padding: var(--space-6); text-align: center; font-size: var(--text-sm); color: var(--color-text-secondary); }
.field { display: flex; flex-direction: column; gap: var(--space-1); }
.field-label { font-size: var(--text-sm); color: var(--color-text-secondary); }
.field-input { padding: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-md); font-size: var(--text-base); background: var(--color-bg-base); }
.hint { font-size: var(--text-xs); color: var(--color-text-tertiary); }
.error-text { color: var(--color-danger-500); font-size: var(--text-sm); }
.btn-primary { padding: var(--space-3); border-radius: var(--radius-md); background: var(--color-primary, var(--color-brand-600)); color: #fff; font-weight: var(--font-semibold); }
.btn-primary:disabled { opacity: 0.6; }
</style>
