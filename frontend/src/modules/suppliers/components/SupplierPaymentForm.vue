<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { paySupplierPayable, type SupplierPayable } from '@/api/suppliers'
import type { Supplier } from '@/types/models'
import type { CashAccountRecord } from '@/api/finance'
import { formatPrice } from '@/utils/currency'
import { useToast } from '@/composables/useToast'
import BaseButton from '@/components/base/BaseButton.vue'
import CashAccountAllocator, { type CashAllocationRow } from '@/components/composite/CashAccountAllocator.vue'

const props = defineProps<{
  supplier: Supplier | null
  payable: SupplierPayable | null
  accounts: CashAccountRecord[]
}>()

const emit = defineEmits<{
  paid: []
}>()

const { t } = useI18n()
const toast = useToast()
const rows = ref<CashAllocationRow[]>([])
const notes = ref('')
const scheduleEntryId = ref<number | null>(null)
const isSubmitting = ref(false)

const payableCurrency = computed(() => props.payable?.currency_of_obligation || 'UZS')
const allocationTotal = computed(() =>
  rows.value.reduce((sum, row) => sum + (Number(row.amount) || 0), 0),
)
const canSubmit = computed(() => (
  Boolean(props.payable)
  && rows.value.some((row) => row.cash_account_id !== null && Number(row.amount) > 0)
  && !isSubmitting.value
))

function defaultRows(): CashAllocationRow[] {
  const currency = payableCurrency.value
  const account = props.accounts.find((item) => item.currency === currency && item.is_active !== false)
    ?? props.accounts.find((item) => item.is_active !== false)
  return [{
    id: crypto.randomUUID(),
    cash_account_id: account?.id ?? null,
    amount: props.payable?.remaining_amount ?? '',
    currency: account?.currency ?? currency,
  }]
}

async function submit(): Promise<void> {
  if (!props.payable || !canSubmit.value) return
  isSubmitting.value = true
  try {
    const allocations = rows.value
      .filter((row) => row.cash_account_id !== null && Number(row.amount) > 0)
      .map((row) => ({
        cash_account_id: row.cash_account_id as number,
        amount: row.amount,
        currency: row.currency,
      }))

    await paySupplierPayable(props.payable.id, {
      allocations,
      schedule_entry_id: scheduleEntryId.value,
      notes: notes.value.trim(),
    })
    toast.success(t('suppliers.paymentRecorded'))
    emit('paid')
  } catch (error: unknown) {
    toast.error(error instanceof Error ? error.message : t('suppliers.paymentFailed'))
  } finally {
    isSubmitting.value = false
  }
}

watch(
  () => [props.payable?.id, props.accounts.length],
  () => {
    rows.value = props.payable ? defaultRows() : []
    notes.value = ''
    scheduleEntryId.value = props.payable?.schedule?.find((row) => row.status !== 'PAID')?.id ?? null
  },
  { immediate: true },
)
</script>

<template>
  <form class="payment-form" @submit.prevent="submit">
    <section v-if="payable" class="payment-summary">
      <div>
        <span>{{ t('suppliers.payableSource') }}</span>
        <strong>{{ supplier?.name || payable.supplier_name }}</strong>
      </div>
      <div>
        <span>{{ t('suppliers.toPay') }}</span>
        <strong class="tabular-nums">{{ payable.remaining_amount }} {{ payable.currency_of_obligation }}</strong>
      </div>
      <div v-if="payable.deadline_date">
        <span>{{ t('suppliers.deadline') }}</span>
        <strong>{{ payable.deadline_date }}</strong>
      </div>
    </section>

    <CashAccountAllocator
      :accounts="accounts"
      :rows="rows"
      @update-rows="rows = $event"
    />

    <label v-if="payable?.schedule?.length" class="field-group">
      <span>{{ t('suppliers.scheduleEntry') }}</span>
      <select v-model="scheduleEntryId" class="input-field">
        <option :value="null">{{ t('suppliers.scheduleAuto') }}</option>
        <option v-for="row in payable.schedule" :key="row.id" :value="row.id">
          #{{ row.sequence_number }} · {{ row.due_date }} · {{ row.amount }} {{ row.currency }}
        </option>
      </select>
    </label>

    <label class="field-group">
      <span>{{ t('suppliers.notes') }}</span>
      <textarea
        v-model="notes"
        class="textarea-field"
        rows="2"
        :placeholder="t('suppliers.paymentNotesPlaceholder')"
      />
    </label>

    <div class="payment-check">
      <span>{{ t('suppliers.enteredAmount') }}</span>
      <strong class="tabular-nums">
        {{ formatPrice(allocationTotal, payableCurrency) }}
      </strong>
    </div>

    <BaseButton
      type="submit"
      variant="primary"
      size="lg"
      :full-width="true"
      :loading="isSubmitting"
      :disabled="!canSubmit"
    >
      {{ t('suppliers.recordPayment') }}
    </BaseButton>
  </form>
</template>

<style scoped>
.payment-form {
  display: grid;
  gap: var(--space-3);
}

.payment-summary {
  display: grid;
  gap: var(--space-2);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-secondary);
  padding: var(--space-3);
}

.payment-summary > div,
.payment-check {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.payment-summary span,
.payment-check span,
.field-group span {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  text-transform: uppercase;
}

.payment-summary strong,
.payment-check strong {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  text-align: right;
}

.field-group {
  display: grid;
  gap: var(--space-2);
}

.input-field,
.textarea-field {
  width: 100%;
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
}

.input-field {
  min-height: 42px;
  padding: 0 var(--space-3);
}

.textarea-field {
  min-height: 72px;
  padding: var(--space-3);
  resize: vertical;
}

.payment-check {
  padding: var(--space-2) 0;
  border-top: 1px solid var(--color-border-subtle);
}
</style>
