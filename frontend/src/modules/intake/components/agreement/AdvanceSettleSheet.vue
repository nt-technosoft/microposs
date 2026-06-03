<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { useToast } from '@/composables/useToast'
import { settleAgreementAdvance, type CapitalAdvanceRecord } from '@/api/partnerships'
import { formatPrice } from '@/utils/currency'
import { getApiErrorMessage } from '@/utils/errors'

interface OperatingAccount {
  id: number
  name: string
  currency: string
}

const props = defineProps<{
  open: boolean
  agreementId: number
  advance: CapitalAdvanceRecord | null
  accounts: OperatingAccount[]
}>()

const emit = defineEmits<{
  close: []
  settled: []
}>()

const toast = useToast()
const amount = ref('')
const source = ref<'CASH' | 'FROM_PROFIT'>('CASH')
const fromAccountId = ref<number | null>(null)
const isSaving = ref(false)
const error = ref<string | null>(null)

const outstanding = computed(() => Number(props.advance?.outstanding_balance ?? 0) || 0)
const amountValue = computed(() => Number.parseFloat(String(amount.value).replace(',', '.')) || 0)

// FROM_PROFIT is repaid in functional UZS from operating cash, so only UZS accounts apply.
const eligibleAccounts = computed(() => props.accounts.filter((a) => a.currency.toUpperCase() === 'UZS'))

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen && props.advance) {
      amount.value = props.advance.outstanding_balance
      source.value = props.advance.repayment_mode === 'FROM_PROFIT' ? 'FROM_PROFIT' : 'CASH'
      fromAccountId.value = eligibleAccounts.value[0]?.id ?? null
      error.value = null
    }
  },
)

function onClose() {
  emit('close')
}

async function submit() {
  if (!props.advance) return
  if (amountValue.value <= 0) {
    error.value = 'Введите сумму больше 0'
    return
  }
  if (amountValue.value > outstanding.value + 1e-6) {
    error.value = `Нельзя погасить больше остатка (${formatPrice(outstanding.value, props.advance.currency)})`
    return
  }
  if (source.value === 'FROM_PROFIT' && !fromAccountId.value) {
    error.value = 'Выберите операционный счёт для выплаты из прибыли'
    return
  }
  isSaving.value = true
  error.value = null
  try {
    await settleAgreementAdvance(props.agreementId, {
      advance_id: props.advance.id,
      amount: String(amountValue.value),
      source: source.value,
      from_account_id: source.value === 'FROM_PROFIT' ? fromAccountId.value : null,
    })
    toast.success('Долг погашен')
    emit('settled')
  } catch (err) {
    error.value = getApiErrorMessage(err, 'Не удалось погасить долг')
    toast.error(error.value)
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <AppBottomSheet :open="open" title="Погасить взаиморасчёт" @close="onClose">
    <div v-if="advance" class="sheet-body">
      <p class="who">
        {{ advance.debtor_name }} → {{ advance.creditor_name || 'Пул' }}
      </p>
      <p class="hint">Остаток долга: <strong>{{ formatPrice(outstanding, advance.currency) }}</strong></p>

      <div class="field">
        <span class="field-label">Чем гасим</span>
        <div class="seg" role="group">
          <button type="button" class="seg-btn" :class="{ active: source === 'CASH' }" @click="source = 'CASH'">
            Деньгами
          </button>
          <button type="button" class="seg-btn" :class="{ active: source === 'FROM_PROFIT' }" @click="source = 'FROM_PROFIT'">
            Из прибыли
          </button>
        </div>
        <p class="seg-hint">
          {{ source === 'CASH'
            ? 'Должник вносит деньги — его капитал достраивается, кредитору возвращается тело.'
            : 'Накопленная прибыль должника закрывает долг; кредитору возврат из операционной кассы.' }}
        </p>
      </div>

      <div v-if="source === 'FROM_PROFIT'" class="field">
        <label class="field-label">Операционный счёт</label>
        <select v-model="fromAccountId" class="field-input">
          <option v-for="acc in eligibleAccounts" :key="acc.id" :value="acc.id">{{ acc.name }}</option>
        </select>
        <p v-if="!eligibleAccounts.length" class="seg-hint">Нет операционного UZS-счёта для выплаты.</p>
      </div>

      <div class="field">
        <label class="field-label">Сумма ({{ advance.currency }})</label>
        <input
          v-model="amount"
          type="number"
          min="0.01"
          step="0.01"
          class="field-input"
          placeholder="0.00"
          inputmode="decimal"
        />
      </div>

      <p v-if="error" class="error-text">{{ error }}</p>

      <button class="btn-primary" :disabled="isSaving" @click="submit">
        {{ isSaving ? 'Погашение…' : 'Погасить' }}
      </button>
    </div>
  </AppBottomSheet>
</template>

<style scoped>
.sheet-body { display: flex; flex-direction: column; gap: var(--space-4); padding: var(--space-4); }
.who { font-weight: var(--font-semibold); font-size: var(--text-base); }
.hint { font-size: var(--text-sm); color: var(--color-text-secondary); }
.field { display: flex; flex-direction: column; gap: var(--space-1); }
.field-label { font-size: var(--text-sm); color: var(--color-text-secondary); }
.field-input { padding: var(--space-3); border: 1px solid var(--color-border); border-radius: var(--radius-md); font-size: var(--text-base); background: var(--color-bg-base); }
.seg { display: flex; gap: var(--space-1); padding: var(--space-1); background: var(--color-bg-subtle); border-radius: var(--radius-md); }
.seg-btn { flex: 1; padding: var(--space-2) var(--space-3); border-radius: var(--radius-sm); font-size: var(--text-sm); font-weight: var(--font-medium); color: var(--color-text-secondary); }
.seg-btn.active { background: var(--color-bg-elevated); color: var(--color-text-primary); font-weight: var(--font-semibold); box-shadow: var(--shadow-sm); }
.seg-hint { font-size: var(--text-xs); color: var(--color-text-tertiary); line-height: 1.4; }
.error-text { color: var(--color-danger-500); font-size: var(--text-sm); }
.btn-primary { padding: var(--space-3); border-radius: var(--radius-md); background: var(--color-primary, var(--color-brand-600)); color: #fff; font-weight: var(--font-semibold); }
.btn-primary:disabled { opacity: 0.6; }
</style>
