<script setup lang="ts">
import type { Component } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ProcurementType } from '@/types/enums'
import type { ContractRow } from '@/modules/intake/types'
import IntakeLinkedAgreementStrip from '@/modules/intake/components/create/IntakeLinkedAgreementStrip.vue'
import IntakePartnershipSection from '@/modules/intake/components/create/IntakePartnershipSection.vue'
import IntakeSupplierSection from '@/modules/intake/components/create/IntakeSupplierSection.vue'
import IntakeTypeSelector from '@/modules/intake/components/create/IntakeTypeSelector.vue'

interface TypeCard {
  type: ProcurementType
  labelKey: string
  descriptionKey: string
  icon: Component
  disabled?: boolean
}

interface SupplierOption {
  value: number
  label: string
}

interface PartnerOption {
  value: number
  label: string
}

defineProps<{
  linkedAgreementId?: number | null
  cards: TypeCard[]
  selectedType: ProcurementType
  isLinkedAgreementMode: boolean
  isPartnershipType: boolean
  isContractEditable: boolean
  supplierOptions: SupplierOption[]
  selectedSupplierId: number | null
  isLoadingRefs: boolean
  notes: string
  investorOptions: PartnerOption[]
  hasLinkedInvestors: boolean
  investorContractRow: ContractRow | null
  operatorContractRow: ContractRow | null
  contractCurrency: string
  plannedBudget: string
  isEditMode: boolean
  procurementTotalInContractCurrency: number
  mudarabaRatio: number
  isRecalculationOpen: boolean
  simulatedInvestorCapitalPercent: number
  simulationRangeStyle: Record<string, string>
  simulatedInvestorProfitPercent: number
  simulatedOperatorProfitPercent: number
  hasSimulationDelta: boolean
  simulationCapitalDelta: number
  simulationProfitDelta: number
  normalizeCurrency: (value: unknown) => string
  nextCurrency: (currency: string) => string
  formatPrice: (value: number, currency?: string) => string
  formatPercent: (value: number) => string
  formatSignedPercent: (value: number) => string
  updatePairPercent: (role: ContractRow['role'], field: 'capital_percent' | 'profit_percent', rawValue: string) => void
}>()

const emit = defineEmits<{
  selectType: [type: ProcurementType]
  openQuickSupplier: []
  openInvestorInvite: []
  updateSelectedSupplierId: [value: number | null]
  updateNotes: [value: string]
  updateContractRole: [role: ContractRow['role'], field: 'partner_id' | 'capital_percent' | 'profit_percent', value: string | number | null]
  updateContractCurrency: [value: string]
  updatePlannedBudget: [value: string]
  toggleRecalculation: []
  setSimulationCapitalPercent: [value: string]
  resetSimulation: []
}>()

const { t } = useI18n()
</script>

<template>
  <div class="step-layout">
    <IntakeLinkedAgreementStrip
      v-if="linkedAgreementId"
      :agreement-id="linkedAgreementId"
    />

    <IntakeTypeSelector
      :cards="cards"
      :selected-type="selectedType"
      :disabled="isLinkedAgreementMode || !isContractEditable"
      @select="emit('selectType', $event)"
    />

    <IntakeSupplierSection
      :supplier-options="supplierOptions"
      :selected-supplier-id="selectedSupplierId"
      :is-loading-refs="isLoadingRefs"
      @open-quick-supplier="emit('openQuickSupplier')"
      @update-selected-supplier-id="emit('updateSelectedSupplierId', $event)"
    />

    <IntakePartnershipSection
      v-if="isPartnershipType"
      :investor-options="investorOptions"
      :has-linked-investors="hasLinkedInvestors"
      :investor-contract-row="investorContractRow"
      :operator-contract-row="operatorContractRow"
      :is-contract-editable="isContractEditable"
      :contract-currency="contractCurrency"
      :planned-budget="plannedBudget"
      :is-edit-mode="isEditMode"
      :procurement-total-in-contract-currency="procurementTotalInContractCurrency"
      :mudaraba-ratio="mudarabaRatio"
      :is-recalculation-open="isRecalculationOpen"
      :simulated-investor-capital-percent="simulatedInvestorCapitalPercent"
      :simulation-range-style="simulationRangeStyle"
      :simulated-investor-profit-percent="simulatedInvestorProfitPercent"
      :simulated-operator-profit-percent="simulatedOperatorProfitPercent"
      :has-simulation-delta="hasSimulationDelta"
      :simulation-capital-delta="simulationCapitalDelta"
      :simulation-profit-delta="simulationProfitDelta"
      :normalize-currency="normalizeCurrency"
      :next-currency="nextCurrency"
      :format-price="formatPrice"
      :format-percent="formatPercent"
      :format-signed-percent="formatSignedPercent"
      :update-pair-percent="updatePairPercent"
      @open-investor-invite="emit('openInvestorInvite')"
      @update-contract-role="(role, field, value) => emit('updateContractRole', role, field, value)"
      @update-contract-currency="emit('updateContractCurrency', $event)"
      @update-planned-budget="emit('updatePlannedBudget', $event)"
      @toggle-recalculation="emit('toggleRecalculation')"
      @set-simulation-capital-percent="emit('setSimulationCapitalPercent', $event)"
      @reset-simulation="emit('resetSimulation')"
    />

    <section class="form-section">
      <div class="section-header">
        <h2 class="section-title">{{ t('procurements.create.notes') }}</h2>
        <span class="section-hint">{{ t('procurements.create.stepBasicsHint') }}</span>
      </div>
      <textarea
        :value="notes"
        class="textarea-field"
        rows="4"
        :placeholder="t('procurements.create.notesPlaceholder')"
        @input="emit('updateNotes', ($event.target as HTMLTextAreaElement).value)"
      />
    </section>
  </div>
</template>

<style scoped>
.step-layout,
.form-section {
  display: grid;
  gap: var(--space-4);
}

.section-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.section-title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.section-hint {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.textarea-field {
  width: 100%;
  min-height: 112px;
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
  padding: var(--space-4);
  resize: vertical;
  line-height: 1.45;
}
</style>
