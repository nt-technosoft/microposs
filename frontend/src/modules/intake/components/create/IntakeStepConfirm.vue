<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ProcurementType } from '@/types/enums'
import IntakeTotalsSection from '@/modules/intake/components/create/IntakeTotalsSection.vue'
import type { PaymentTermsDraft } from '@/modules/intake/types'

interface SupplierOption {
  value: number
  label: string
}

const props = defineProps<{
  selectedType: ProcurementType
  supplierOptions: SupplierOption[]
  selectedSupplierId: number | null
  notes: string
  itemCount: number
  expenseCount: number
  hasForeignCurrency: boolean
  grandTotal: number
  expenseTotal: number
  procurementTotal: number
  obligationTotal: number
  terms: PaymentTermsDraft
  formatPrice: (value: number, currency?: string) => string
}>()

const { t } = useI18n()

const supplierLabel = computed(() => {
  const selected = props.supplierOptions.find((option) => option.value === props.selectedSupplierId)
  return selected?.label || t('procurements.supplierMissing')
})

const typeLabel = computed(() => t(`domain.procurementType.${props.selectedType}`))
const termsLabel = computed(() => t(`procurements.create.termsType.${props.terms.type}`))
</script>

<template>
  <div class="confirm-layout">
    <section class="summary-band">
      <div class="summary-line">
        <span>{{ t('procurements.create.summaryType') }}</span>
        <strong>{{ typeLabel }}</strong>
      </div>
      <div class="summary-line">
        <span>{{ t('suppliers.supplier') }}</span>
        <strong>{{ supplierLabel }}</strong>
      </div>
      <div class="summary-line">
        <span>{{ t('procurements.create.paymentTermsTitle') }}</span>
        <strong>{{ termsLabel }}</strong>
      </div>
      <div class="summary-grid">
        <div class="summary-chip">
          <span>{{ t('products.title') }}</span>
          <strong>{{ itemCount }}</strong>
        </div>
        <div class="summary-chip">
          <span>{{ t('procurements.expenses') }}</span>
          <strong>{{ expenseCount }}</strong>
        </div>
        <div class="summary-chip summary-chip--wide">
          <span>{{ t('procurements.create.supplierObligation') }}</span>
          <strong>{{ formatPrice(obligationTotal, terms.currency_of_obligation) }}</strong>
        </div>
      </div>
      <div v-if="notes.trim()" class="summary-note">
        <span>{{ t('procurements.create.notes') }}</span>
        <p>{{ notes }}</p>
      </div>
    </section>

    <IntakeTotalsSection
      :has-foreign-currency="hasForeignCurrency"
      :grand-total="grandTotal"
      :expense-total="expenseTotal"
      :procurement-total="procurementTotal"
      :format-price="formatPrice"
    />
  </div>
</template>

<style scoped>
.confirm-layout {
  display: grid;
  gap: var(--space-4);
}

.summary-band {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border-subtle);
  background: var(--color-bg-elevated);
}

.summary-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.summary-line span {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.summary-line strong {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  text-align: right;
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}

.summary-chip--wide {
  grid-column: 1 / -1;
}

.summary-chip {
  display: grid;
  gap: 4px;
  padding: var(--space-3);
  border-radius: var(--radius-lg);
  background: color-mix(in srgb, var(--color-brand-50) 45%, var(--color-bg-primary));
}

.summary-chip span {
  color: var(--color-text-secondary);
  font-size: 12px;
}

.summary-chip strong {
  color: var(--color-text-primary);
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
}

.summary-note {
  display: grid;
  gap: 6px;
  padding-top: var(--space-1);
  border-top: 1px solid var(--color-border-subtle);
}

.summary-note span {
  color: var(--color-text-secondary);
  font-size: 12px;
}

.summary-note p {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  line-height: 1.45;
  white-space: pre-wrap;
}
</style>
