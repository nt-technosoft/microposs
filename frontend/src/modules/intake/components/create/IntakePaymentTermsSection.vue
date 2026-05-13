<script setup lang="ts">
import { computed } from 'vue'
import { Plus, Trash2 } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'
import type { PaymentScheduleDraftRow, PaymentTermsDraft, ProcurementTermsType } from '@/modules/intake/types'

const props = defineProps<{
  terms: PaymentTermsDraft
  supplierSelected: boolean
  obligationTotal: number
  formatPrice: (value: number, currency?: string) => string
}>()

const emit = defineEmits<{
  updateTerms: [value: PaymentTermsDraft]
}>()

const { t } = useI18n()

const termsOptions = computed<Array<{ value: ProcurementTermsType; label: string; hint: string }>>(() => [
  { value: 'PREPAID', label: t('procurements.create.termsPrepaid'), hint: t('procurements.create.termsPrepaidHint') },
  { value: 'PARTIAL', label: t('procurements.create.termsPartial'), hint: t('procurements.create.termsPartialHint') },
  { value: 'DEFERRED', label: t('procurements.create.termsDeferred'), hint: t('procurements.create.termsDeferredHint') },
  { value: 'INSTALLMENT', label: t('procurements.create.termsInstallment'), hint: t('procurements.create.termsInstallmentHint') },
  { value: 'CONSIGNMENT', label: t('procurements.create.termsConsignment'), hint: t('procurements.create.termsConsignmentHint') },
])

function patchTerms(patch: Partial<PaymentTermsDraft>): void {
  emit('updateTerms', {
    ...props.terms,
    ...patch,
  })
}

function patchSchedule(rowId: string, patch: Partial<PaymentScheduleDraftRow>): void {
  patchTerms({
    schedule: props.terms.schedule.map((row) => row.id === rowId ? { ...row, ...patch } : row),
  })
}

function addScheduleRow(): void {
  patchTerms({
    schedule: [
      ...props.terms.schedule,
      { id: crypto.randomUUID(), due_date: '', amount: '' },
    ],
  })
}

function removeScheduleRow(rowId: string): void {
  patchTerms({
    schedule: props.terms.schedule.filter((row) => row.id !== rowId),
  })
}
</script>

<template>
  <section class="terms-section">
    <div class="section-heading">
      <div>
        <h2>{{ t('procurements.create.paymentTermsTitle') }}</h2>
        <p>{{ t('procurements.create.paymentTermsHint') }}</p>
      </div>
      <strong class="total-pill tabular-nums">{{ formatPrice(obligationTotal, terms.currency_of_obligation) }}</strong>
    </div>

    <div class="terms-grid">
      <button
        v-for="option in termsOptions"
        :key="option.value"
        type="button"
        class="term-option"
        :class="{ active: terms.type === option.value }"
        @click="patchTerms({ type: option.value })"
      >
        <strong>{{ option.label }}</strong>
        <span>{{ option.hint }}</span>
      </button>
    </div>

    <div v-if="terms.type !== 'PREPAID' && !supplierSelected" class="warning-row">
      {{ t('procurements.create.termsSupplierRequired') }}
    </div>

    <div class="terms-fields">
      <label class="field-group">
        <span>{{ t('finance.currency') }}</span>
        <select
          class="input-field"
          :value="terms.currency_of_obligation"
          @change="patchTerms({ currency_of_obligation: ($event.target as HTMLSelectElement).value })"
        >
          <option value="USD">USD</option>
          <option value="UZS">UZS</option>
        </select>
      </label>

      <label v-if="terms.currency_of_obligation !== 'UZS'" class="field-group">
        <span>{{ t('procurements.create.fxRate') }}</span>
        <input
          class="input-field"
          inputmode="decimal"
          type="number"
          min="0"
          step="0.000001"
          :value="terms.fx_rate_at_obligation"
          @input="patchTerms({ fx_rate_at_obligation: ($event.target as HTMLInputElement).value })"
        />
      </label>

      <label v-if="terms.type === 'PARTIAL'" class="field-group">
        <span>{{ t('procurements.create.paidNow') }}</span>
        <input
          class="input-field"
          inputmode="decimal"
          type="number"
          min="0"
          step="0.01"
          :value="terms.paid_amount"
          @input="patchTerms({ paid_amount: ($event.target as HTMLInputElement).value })"
        />
      </label>

      <label v-if="terms.type === 'DEFERRED'" class="field-group">
        <span>{{ t('procurements.create.deadlineDate') }}</span>
        <input
          class="input-field"
          type="date"
          :value="terms.deadline_date"
          @input="patchTerms({ deadline_date: ($event.target as HTMLInputElement).value })"
        />
      </label>
    </div>

    <div v-if="terms.type === 'INSTALLMENT'" class="schedule-box">
      <div class="schedule-head">
        <span>{{ t('procurements.create.paymentSchedule') }}</span>
        <button type="button" @click="addScheduleRow">
          <Plus :size="14" :stroke-width="2.25" />
          {{ t('common.add') }}
        </button>
      </div>
      <div v-if="terms.schedule.length === 0" class="empty-row">
        {{ t('procurements.create.paymentScheduleEmpty') }}
      </div>
      <div v-for="row in terms.schedule" :key="row.id" class="schedule-row">
        <input
          class="input-field"
          type="date"
          :value="row.due_date"
          @input="patchSchedule(row.id, { due_date: ($event.target as HTMLInputElement).value })"
        />
        <input
          class="input-field"
          inputmode="decimal"
          type="number"
          min="0"
          step="0.01"
          :placeholder="t('common.amount')"
          :value="row.amount"
          @input="patchSchedule(row.id, { amount: ($event.target as HTMLInputElement).value })"
        />
        <button type="button" class="delete-btn" :aria-label="t('common.delete')" @click="removeScheduleRow(row.id)">
          <Trash2 :size="16" :stroke-width="2" />
        </button>
      </div>
    </div>

    <label class="field-group">
      <span>{{ t('procurements.create.termsNotes') }}</span>
      <textarea
        class="textarea-field"
        rows="2"
        :value="terms.notes"
        :placeholder="t('procurements.create.termsNotesPlaceholder')"
        @input="patchTerms({ notes: ($event.target as HTMLTextAreaElement).value })"
      />
    </label>
  </section>
</template>

<style scoped>
.terms-section {
  display: grid;
  gap: var(--space-3);
}

.section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}

.section-heading h2 {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.section-heading p {
  margin-top: 4px;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.35;
}

.total-pill {
  flex: 0 0 auto;
  padding: 7px 10px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-subtle);
  background: var(--color-bg-elevated);
  font-size: var(--text-sm);
}

.terms-grid {
  display: grid;
  gap: var(--space-2);
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.term-option {
  min-height: 72px;
  display: grid;
  align-content: start;
  gap: 5px;
  padding: var(--space-3);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-subtle);
  background: var(--color-bg-elevated);
  text-align: left;
}

.term-option strong {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.term-option span {
  font-size: 12px;
  line-height: 1.25;
  color: var(--color-text-secondary);
}

.term-option.active {
  border-color: var(--color-brand-500);
  background: color-mix(in srgb, var(--color-brand-50) 72%, var(--color-bg-elevated));
}

.warning-row {
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-warning-bg);
  color: var(--color-warning);
  font-size: var(--text-sm);
}

.terms-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}

.field-group {
  display: grid;
  gap: var(--space-2);
}

.field-group span,
.schedule-head span {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  text-transform: uppercase;
}

.input-field,
.textarea-field {
  width: 100%;
  min-height: 42px;
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  padding: var(--space-2) var(--space-3);
  color: var(--color-text-primary);
}

.textarea-field {
  resize: vertical;
  line-height: 1.4;
}

.schedule-box {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
}

.schedule-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.schedule-head button {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 32px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-default);
  color: var(--color-brand-600);
  font-size: var(--text-sm);
}

.schedule-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) 38px;
  gap: var(--space-2);
  align-items: center;
}

.delete-btn {
  width: 38px;
  height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  color: var(--color-text-tertiary);
}

.delete-btn:hover {
  color: var(--color-error);
  background: var(--color-error-bg);
}

.empty-row {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

@media (max-width: 430px) {
  .terms-grid,
  .terms-fields {
    grid-template-columns: 1fr;
  }

  .section-heading {
    align-items: stretch;
    flex-direction: column;
  }

  .total-pill {
    width: fit-content;
  }
}
</style>
