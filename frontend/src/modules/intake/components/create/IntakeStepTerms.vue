<script setup lang="ts">
import type { ContractRow, ExpenseRow, PaymentTermsDraft } from '@/modules/intake/types'
import IntakeExpensesSection from '@/modules/intake/components/create/IntakeExpensesSection.vue'
import IntakePaymentTermsSection from '@/modules/intake/components/create/IntakePaymentTermsSection.vue'
import IntakePartnershipSection from '@/modules/intake/components/create/IntakePartnershipSection.vue'

interface PartnerOption {
  value: number
  label: string
}

defineProps<{
  isPartnershipType: boolean
  investorOptions: PartnerOption[]
  hasLinkedInvestors: boolean
  investorContractRow: ContractRow | null
  operatorContractRow: ContractRow | null
  isContractEditable: boolean
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
  expenses: ExpenseRow[]
  expenseTypeOptions: Array<{ value: string; label: string }>
  allocationOptions: Array<{ value: string; label: string }>
  showFxField: (currency: string) => boolean
  formatCurrencyTotalLabel: (currency: string) => string
  terms: PaymentTermsDraft
  supplierSelected: boolean
  obligationTotal: number
}>()

const emit = defineEmits<{
  openInvestorInvite: []
  updateContractRole: [role: ContractRow['role'], field: 'partner_id' | 'capital_percent' | 'profit_percent', value: string | number | null]
  updateContractCurrency: [value: string]
  updatePlannedBudget: [value: string]
  toggleRecalculation: []
  setSimulationCapitalPercent: [value: string]
  resetSimulation: []
  addExpense: []
  removeExpense: [rowId: string]
  updateExpense: [rowId: string, field: keyof Omit<ExpenseRow, 'id'>, value: string]
  toggleExpenseCurrency: [rowId: string]
  updateTerms: [value: PaymentTermsDraft]
}>()
</script>

<template>
  <div class="step-layout">
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

    <IntakePaymentTermsSection
      :terms="terms"
      :supplier-selected="supplierSelected"
      :obligation-total="obligationTotal"
      :format-price="formatPrice"
      @update-terms="emit('updateTerms', $event)"
    />

    <IntakeExpensesSection
      :expenses="expenses"
      :expense-type-options="expenseTypeOptions"
      :allocation-options="allocationOptions"
      :normalize-currency="normalizeCurrency"
      :show-fx-field="showFxField"
      :format-currency-total-label="formatCurrencyTotalLabel"
      @add-expense="emit('addExpense')"
      @remove-expense="emit('removeExpense', $event)"
      @update-expense="(rowId, field, value) => emit('updateExpense', rowId, field, value)"
      @toggle-expense-currency="emit('toggleExpenseCurrency', $event)"
    />
  </div>
</template>

<style scoped>
.step-layout {
  display: grid;
  gap: var(--space-4);
}
</style>
