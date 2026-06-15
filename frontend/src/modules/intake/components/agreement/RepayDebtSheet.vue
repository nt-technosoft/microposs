<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { useToast } from '@/composables/useToast'
import { repayVentureDebt } from '@/api/partnerships'
import { formatPrice } from '@/utils/currency'
import { getApiErrorMessage } from '@/utils/errors'

// E17 T-5.3: repay a partner's negative venture position. The debt is in
// functional UZS; the debtor brings UZS into an operating cash account. Gates and
// the amount come from the backend — we never recompute them.
interface OperatingAccount {
  id: number
  name: string
  currency: string
}

interface DebtTarget {
  procurement_id: number
  partner_id: number
  partner_name: string
  debt_uzs: string
}

const props = defineProps<{
  open: boolean
  target: DebtTarget | null
  accounts: OperatingAccount[]
}>()

const emit = defineEmits<{
  close: []
  repaid: []
}>()

const toast = useToast()
const amount = ref('')
const toAccountId = ref<number | null>(null)
const isSaving = ref(false)
const error = ref<string | null>(null)

const outstanding = computed(() => Math.max(0, Number(props.target?.debt_uzs ?? 0) || 0))
const amountValue = computed(() => Number.parseFloat(String(amount.value).replace(',', '.')) || 0)
// The debt is in functional UZS — repay into a UZS operating account. Other
// currencies need an explicit exchange (sarf) first.
const uzsAccounts = computed(() => props.accounts.filter((a) => a.currency.toUpperCase() === 'UZS'))

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen && props.target) {
      amount.value = props.target.debt_uzs
      toAccountId.value = uzsAccounts.value[0]?.id ?? null
      error.value = null
    }
  },
)

async function submit() {
  if (!props.target) return
  if (amountValue.value <= 0) {
    error.value = 'Введите сумму больше 0'
    return
  }
  if (amountValue.value > outstanding.value + 1e-6) {
    error.value = `Нельзя погасить больше долга (${formatPrice(outstanding.value, 'UZS')})`
    return
  }
  if (!toAccountId.value) {
    error.value = 'Выберите операционную кассу (UZS)'
    return
  }
  isSaving.value = true
  error.value = null
  try {
    await repayVentureDebt(props.target.procurement_id, {
      partner_id: props.target.partner_id,
      amount: String(amountValue.value),
      currency: 'UZS',
      paid_to_account_id: toAccountId.value,
    })
    toast.success('Долг погашен')
    emit('repaid')
  } catch (err) {
    error.value = getApiErrorMessage(err, 'Не удалось погасить долг')
    toast.error(error.value)
  } finally {
    isSaving.value = false
  }
}
</script>

<template>
  <AppBottomSheet :open="open" title="Погасить долг перед венчуром" @close="emit('close')">
    <div v-if="target" class="sheet-body">
      <p class="who">{{ target.partner_name }} → венчур (приход #{{ target.procurement_id }})</p>
      <p class="hint">Долг перед венчуром: <strong>{{ formatPrice(outstanding, 'UZS') }}</strong></p>

      <div class="field">
        <label class="field-label">Операционная касса (UZS)</label>
        <select v-model="toAccountId" class="field-input">
          <option v-for="acc in uzsAccounts" :key="acc.id" :value="acc.id">{{ acc.name }}</option>
        </select>
        <p v-if="!uzsAccounts.length" class="seg-hint">
          Нет UZS-кассы. Долг в UZS — сделайте явный обмен (sarf), затем гасите.
        </p>
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
      </div>

      <p class="seg-hint">
        Должник вносит деньги в операционную кассу — долг закрывается, средства идут на выплату
        пострадавшей стороне.
      </p>

      <p v-if="error" class="error-text">{{ error }}</p>

      <button class="btn-primary" :disabled="isSaving || !uzsAccounts.length" @click="submit">
        {{ isSaving ? 'Погашение…' : 'Погасить долг' }}
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
.seg-hint { font-size: var(--text-xs); color: var(--color-text-tertiary); line-height: 1.4; }
.error-text { color: var(--color-danger-500); font-size: var(--text-sm); }
.btn-primary { padding: var(--space-3); border-radius: var(--radius-md); background: var(--color-primary, var(--color-brand-600)); color: #fff; font-weight: var(--font-semibold); }
.btn-primary:disabled { opacity: 0.6; }
</style>
