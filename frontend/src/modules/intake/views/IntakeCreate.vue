<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, Wallet, Handshake, Users, AlertCircle } from 'lucide-vue-next'
import BaseButton from '@/components/base/BaseButton.vue'
import { useToast } from '@/composables/useToast'
import { useIdempotency } from '@/composables/useIdempotency'
import { formatPrice } from '@/utils/currency'
import { PricingMode, ProcurementType } from '@/types/enums'
import type { Category, Product, ProductVariant, Supplier } from '@/types/models'
import { createSupplier, fetchSuppliers } from '@/api/suppliers'
import { createProduct, fetchCategories, fetchProductVariants, fetchVariantsPaginated } from '@/api/catalog'
import {
  createProcurement,
  fetchInvestmentAgreement,
  fetchProcurement,
  updateProcurement,
  type InvestmentAgreementDetail,
  type ProcurementDetail,
} from '@/api/partnerships'
import { fetchPartners, type Partner } from '@/api/core'
import { useFxRate } from '@/composables/useFxRate'
import { useIntakeCurrency } from '@/modules/intake/composables/useIntakeCurrency'
import { useIntakeDraftSetup } from '@/modules/intake/composables/useIntakeDraftSetup'
import { useIntakePartnershipMath } from '@/modules/intake/composables/useIntakePartnershipMath'
import { useIntakeQuickActions } from '@/modules/intake/composables/useIntakeQuickActions'
import { useIntakeSubmission } from '@/modules/intake/composables/useIntakeSubmission'
import IntakeQuickProductSheet from '@/modules/intake/components/create/IntakeQuickProductSheet.vue'
import IntakeQuickSupplierSheet from '@/modules/intake/components/create/IntakeQuickSupplierSheet.vue'
import IntakeStepBasics from '@/modules/intake/components/create/IntakeStepBasics.vue'
import IntakeStepConfirm from '@/modules/intake/components/create/IntakeStepConfirm.vue'
import IntakeStepProducts from '@/modules/intake/components/create/IntakeStepProducts.vue'
import IntakeStepTerms from '@/modules/intake/components/create/IntakeStepTerms.vue'
import IntakeVariantPickerSheet from '@/modules/intake/components/create/IntakeVariantPickerSheet.vue'
import IntakeWizardProgress from '@/modules/intake/components/create/IntakeWizardProgress.vue'
import type { ContractRow, ExpenseRow, LineRow, PaymentTermsDraft } from '@/modules/intake/types'
import { defaultTermsDraft, useIntakeStore } from '@/stores/intake'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const { generateRequestId } = useIdempotency()
const { t } = useI18n()
const intakeStore = useIntakeStore()
let referencesAbortController: AbortController | null = null

interface TypeCard {
  type: ProcurementType
  labelKey: string
  descriptionKey: string
  icon: typeof Wallet
  disabled?: boolean
}

const TYPE_CARDS: TypeCard[] = [
  {
    type: ProcurementType.OWN_FUNDS,
    labelKey: 'domain.procurementType.OWN_FUNDS',
    descriptionKey: 'procurements.create.typeOwnFundsDesc',
    icon: Wallet,
  },
  {
    type: ProcurementType.PARTNERSHIP,
    labelKey: 'domain.procurementType.PARTNERSHIP',
    descriptionKey: 'procurements.create.typePartnershipDesc',
    icon: Handshake,
  },
  {
    type: ProcurementType.MUSHARAKA,
    labelKey: 'domain.procurementType.MUSHARAKA',
    descriptionKey: 'procurements.create.typeMusharakaDesc',
    icon: Users,
  },
]

const EXPENSE_TYPE_OPTIONS = [
  { value: 'CUSTOMS', labelKey: 'domain.expenseType.CUSTOMS' },
  { value: 'LOGISTICS', labelKey: 'domain.expenseType.LOGISTICS' },
  { value: 'FEE', labelKey: 'domain.expenseType.FEE' },
  { value: 'OTHER', labelKey: 'domain.expenseType.OTHER' },
]

const ALLOCATION_OPTIONS = [
  { value: 'BY_VALUE', labelKey: 'domain.allocationMethod.BY_VALUE' },
  { value: 'BY_QUANTITY', labelKey: 'domain.allocationMethod.BY_QUANTITY' },
]

const expenseTypeOptions = computed(() => EXPENSE_TYPE_OPTIONS.map((option) => ({
  value: option.value,
  label: t(option.labelKey),
})))

const allocationOptions = computed(() => ALLOCATION_OPTIONS.map((option) => ({
  value: option.value,
  label: t(option.labelKey),
})))

const selectedType = ref<ProcurementType>(ProcurementType.OWN_FUNDS)
const selectedSupplierId = ref<number | null>(null)
const notes = ref('')
const suppliers = ref<Supplier[]>([])
const categories = ref<Category[]>([])
const allVariants = ref<ProductVariant[]>([])
const partners = ref<Partner[]>([])
const isLoadingRefs = ref(false)
const isSaving = ref(false)
const formError = ref<string | null>(null)
const isLoadingDraft = ref(false)
const hasBalanceActivity = ref(false)
const linkedAgreement = ref<InvestmentAgreementDetail | null>(null)
const editingAgreementId = ref<number | null>(null)
const isRecalculationOpen = ref(false)
const {
  rate: latestUsdRate,
  error: latestUsdRateError,
  load: loadLatestUsdRateFromApi,
} = useFxRate({ baseCurrency: 'USD', quoteCurrency: 'UZS' })
const contractCurrency = ref('USD')
const plannedBudget = ref('')
const lines = ref<LineRow[]>([])
const expenses = ref<ExpenseRow[]>([])
const paymentTerms = ref<PaymentTermsDraft>(defaultTermsDraft())
const contractRows = ref<ContractRow[]>([
  { id: crypto.randomUUID(), partner_id: null, role: 'INVESTOR', capital_percent: '50', profit_percent: '50' },
  { id: crypto.randomUUID(), partner_id: null, role: 'OPERATOR', capital_percent: '50', profit_percent: '50' },
])

const {
  normalizeCurrency,
  defaultFxRateForCurrency,
  nextCurrency,
  parsePositiveNumber,
  getFxRateValue,
  toggleLineCurrency,
  toggleExpenseCurrency,
  showFxField,
  formatCurrencyTotalLabel,
  grandTotal,
  expenseTotal,
  procurementTotal,
  procurementTotalInContractCurrency,
  hasForeignCurrency,
} = useIntakeCurrency({
  lines,
  expenses,
  contractCurrency,
  latestUsdRate,
})

const {
  isPartnershipType,
  investorContractRow,
  operatorContractRow,
  capitalPercentTotal,
  profitTotal,
  investorCapitalPercent,
  investorProfitShare,
  investorProfitPercent,
  mudarabaRatio,
  expectedProfitByRole,
  simulatedInvestorCapitalPercent,
  simulatedInvestorProfitPercent,
  simulatedOperatorProfitPercent,
  simulationCapitalDelta,
  simulationProfitDelta,
  hasSimulationDelta,
  simulationRangeStyle,
  formatPercent,
  formatSignedPercent,
  setSimulationCapitalPercent,
  resetSimulation,
  buildDefaultContractRows,
  updatePairPercent,
} = useIntakePartnershipMath({
  contractRows,
  partners,
  selectedType,
})

const editingProcurementId = computed(() => {
  const raw = Number(route.params.id)
  return Number.isFinite(raw) ? raw : null
})
const isEditMode = computed(() => editingProcurementId.value !== null)
const linkedAgreementId = computed(() => {
  const raw = Number(route.query.agreement_id)
  return Number.isFinite(raw) && raw > 0 ? raw : null
})
const isLinkedAgreementMode = computed(() => linkedAgreementId.value !== null && !isEditMode.value)

function buildEmptyLine(): LineRow {
  return {
    id: crypto.randomUUID(),
    variant: null,
    quantity: '1',
    cost_per_unit: '',
    currency: 'UZS',
    fx_rate: '1',
  }
}

function buildEmptyExpense(): ExpenseRow {
  return {
    id: crypto.randomUUID(),
    expense_type: 'CUSTOMS',
    amount: '',
    currency: 'UZS',
    fx_rate: '1',
    allocation_method: 'BY_VALUE',
    notes: '',
  }
}

function formatEditablePercent(value: number): string {
  return Number(value.toFixed(4)).toString()
}

function addEmptyLine(): void {
  lines.value = [...lines.value, buildEmptyLine()]
}

function removeLine(rowId: string): void {
  lines.value = lines.value.filter((line) => line.id !== rowId)
}

function addExpense(): void {
  expenses.value = [...expenses.value, buildEmptyExpense()]
}

function removeExpense(rowId: string): void {
  expenses.value = expenses.value.filter((expense) => expense.id !== rowId)
}

function updateLine(rowId: string, field: keyof Omit<LineRow, 'id'>, value: string | ProductVariant | null): void {
  lines.value = lines.value.map((line) => line.id === rowId ? { ...line, [field]: value } : line)
}

function updateExpense(rowId: string, field: keyof Omit<ExpenseRow, 'id'>, value: string): void {
  expenses.value = expenses.value.map((expense) => expense.id === rowId ? { ...expense, [field]: value } as ExpenseRow : expense)
}

function updateContractRow(rowId: string, field: keyof Omit<ContractRow, 'id'>, value: string | number | null): void {
  contractRows.value = contractRows.value.map((row) => row.id === rowId ? { ...row, [field]: value } as ContractRow : row)
}

type ContractEditableField = 'partner_id' | 'capital_percent' | 'profit_percent'

function updateContractRole(role: ContractRow['role'], field: ContractEditableField, value: string | number | null): void {
  const row = contractRows.value.find((item) => item.role === role)
  if (!row) return
  updateContractRow(row.id, field, value)
}

async function loadLatestUsdRate(): Promise<void> {
  try {
    await loadLatestUsdRateFromApi()
  } catch {
    toast.error(latestUsdRateError.value || t('products.usdRateMissing'))
  }
}

function openInvestorInvitePage(): void {
  router.push({ name: 'owner-investors' })
}
const {
  loadAllVariants,
  variantSheetOpen,
  activeLineId,
  variantSearch,
  variantSearchCategory,
  quickProductSheetOpen,
  quickProductName,
  quickProductCategoryId,
  quickProductBasePrice,
  quickProductError,
  isCreatingQuickProduct,
  quickSupplierSheetOpen,
  quickSupplierName,
  quickSupplierPhone,
  quickSupplierEmail,
  quickSupplierError,
  isCreatingQuickSupplier,
  openVariantPicker,
  closeVariantPicker,
  openQuickProductCreator,
  closeQuickProductCreator,
  openQuickSupplierCreator,
  closeQuickSupplierCreator,
  placeholderVariantFromProcurementItem,
  createQuickProduct,
  createQuickSupplier,
  filteredVariants,
  selectVariant,
  variantDisplay,
} = useIntakeQuickActions({
  allVariants,
  lines,
  suppliers,
  selectedSupplierId,
  updateLine,
  buildEmptyLine,
  t,
  toast,
})

interface WizardStep {
  id: number
  title: string
  hint: string
}

const wizardSteps = computed<WizardStep[]>(() => [
  { id: 1, title: t('procurements.create.stepBasicsTitle'), hint: t('procurements.create.stepBasicsShort') },
  { id: 2, title: t('procurements.create.stepProductsTitle'), hint: t('procurements.create.stepProductsShort') },
  { id: 3, title: t('procurements.create.stepTermsTitle'), hint: t('procurements.create.stepTermsShort') },
  { id: 4, title: t('procurements.create.stepConfirmTitle'), hint: t('procurements.create.stepConfirmShort') },
])

const supplierOptions = computed(() => suppliers.value.map((supplier) => ({ value: supplier.id, label: supplier.name })))
const categoryOptions = computed(() => categories.value.map((category) => ({ value: category.id, label: category.name })))
const investorOptions = computed(() => partners.value.filter((partner) => partner.role === 'INVESTOR').map((partner) => ({ value: partner.id, label: partner.display_name })))
const hasLinkedInvestors = computed(() => investorOptions.value.length > 0)

const plannedBudgetAmount = computed(() => parsePositiveNumber(plannedBudget.value))
const obligationTotal = computed(() => {
  const currency = normalizeCurrency(paymentTerms.value.currency_of_obligation)
  if (currency === 'UZS') return grandTotal.value
  const fx = parsePositiveNumber(paymentTerms.value.fx_rate_at_obligation)
  return fx > 0 ? grandTotal.value / fx : 0
})
const currentStep = ref(1)
const maxReachableStep = computed(() => {
  if (!isEditMode.value) return 1
  return Math.max(2, currentStep.value)
})
const hasDraftLines = computed(() => lines.value.length > 0)
const hasDraftExpenses = computed(() => expenses.value.length > 0)
const isContractEditable = computed(() => !isEditMode.value || !hasBalanceActivity.value)

function applyDefaultContract(): void {
  contractRows.value = buildDefaultContractRows()
}
const {
  resetDraftForm,
  loadExistingDraft,
  loadLinkedAgreementIfNeeded,
} = useIntakeDraftSetup({
  selectedType,
  editingAgreementId,
  selectedSupplierId,
  notes,
  lines,
  expenses,
  paymentTerms,
  contractCurrency,
  plannedBudget,
  contractRows,
  partners,
  allVariants,
  linkedAgreement,
  linkedAgreementId,
  editingProcurementId,
  isLoadingDraft,
  hasBalanceActivity,
  normalizeCurrency,
  buildDefaultContractRows,
  placeholderVariantFromProcurementItem,
  formatEditablePercent,
  t,
})

const { saveDraft } = useIntakeSubmission({
  isSaving,
  formError,
  isEditMode,
  editingProcurementId,
  isLinkedAgreementMode,
  linkedAgreementId,
  selectedType,
  selectedSupplierId,
  editingAgreementId,
  notes,
  lines,
  expenses,
  paymentTerms,
  obligationTotal,
  contractRows,
  contractCurrency,
  plannedBudgetAmount,
  isPartnershipType,
  capitalPercentTotal,
  profitTotal,
  mudarabaRatio,
  investorProfitShare,
  expectedProfitByRole,
  normalizeCurrency,
  getFxRateValue,
  defaultFxRateForCurrency,
  showFxField,
  generateRequestId,
  router,
  toast,
  t,
})

function parseQueryStep(rawValue: unknown, fallback: number): number {
  const parsed = Number(rawValue)
  if (!Number.isFinite(parsed)) return fallback
  return Math.min(4, Math.max(1, Math.trunc(parsed)))
}

function applyStoredBasics(): void {
  selectedType.value = intakeStore.draft.selectedType
  selectedSupplierId.value = intakeStore.draft.selectedSupplierId
  notes.value = intakeStore.draft.notes
  paymentTerms.value = {
    ...defaultTermsDraft(),
    ...intakeStore.draft.terms,
  }
  applyDefaultContract()
}

function restoreStoredWorkspace(): void {
  if (intakeStore.draft.workspaceProcurementId !== editingProcurementId.value) return
  if (intakeStore.draft.lines.length > 0) {
    lines.value = intakeStore.draft.lines.map((line) => ({
      id: line.id || crypto.randomUUID(),
      variant: allVariants.value.find((variant) => variant.id === line.variant_id) ?? null,
      quantity: line.quantity,
      cost_per_unit: line.cost_per_unit,
      currency: normalizeCurrency(line.currency),
      fx_rate: line.fx_rate,
    }))
  }
  if (intakeStore.draft.expenses.length > 0) {
    expenses.value = intakeStore.draft.expenses
  }
  if (intakeStore.draft.contractCurrency) {
    contractCurrency.value = normalizeCurrency(intakeStore.draft.contractCurrency)
  }
  if (intakeStore.draft.plannedBudget) {
    plannedBudget.value = intakeStore.draft.plannedBudget
  }
  if (intakeStore.draft.contractRows.length > 0) {
    contractRows.value = intakeStore.draft.contractRows
  }
  paymentTerms.value = {
    ...defaultTermsDraft(),
    ...intakeStore.draft.terms,
  }
}

function syncStepRoute(step: number): void {
  if (!isEditMode.value || editingProcurementId.value === null) return
  const nextQuery = { ...route.query, step: String(step) }
  router.replace({ query: nextQuery })
}

function setCurrentStep(step: number): void {
  const clamped = Math.min(4, Math.max(1, step))
  currentStep.value = clamped
  intakeStore.setStep(clamped)
  syncStepRoute(clamped)
}

function goNextStep(): void {
  if (!isEditMode.value && currentStep.value === 1) return
  setCurrentStep(currentStep.value + 1)
}

function goPrevStep(): void {
  setCurrentStep(currentStep.value - 1)
}

function goToStep(step: number): void {
  if (!isEditMode.value && step > 1) return
  if (step > maxReachableStep.value) return
  setCurrentStep(step)
}

function validatePaymentTerms(): string {
  const terms = paymentTerms.value
  if (terms.type !== 'PREPAID' && selectedSupplierId.value === null) {
    return t('procurements.create.validationTermsSupplier')
  }
  if (normalizeCurrency(terms.currency_of_obligation) !== 'UZS' && parsePositiveNumber(terms.fx_rate_at_obligation) <= 0) {
    return t('procurements.create.validationTermsFxRate')
  }
  if (terms.type === 'PARTIAL') {
    const paid = parsePositiveNumber(terms.paid_amount)
    if (paid <= 0 || paid >= obligationTotal.value) {
      return t('procurements.create.validationPartialPaid')
    }
  }
  if (terms.type === 'DEFERRED' && !terms.deadline_date) {
    return t('procurements.create.validationDeadline')
  }
  if (terms.type === 'INSTALLMENT') {
    const rows = terms.schedule.filter((row) => row.due_date && parsePositiveNumber(row.amount) > 0)
    if (rows.length === 0) return t('procurements.create.validationSchedule')
  }
  return ''
}

async function handlePrimaryAction(): Promise<void> {
  if (!isEditMode.value && currentStep.value === 1) {
    const procurement = await saveDraft({
      redirectTo: (procurement) => ({
        name: 'procurement-edit',
        params: { id: procurement.id },
        query: { step: 2 },
      }),
    })
    if (procurement) {
      intakeStore.setTermsForProcurement(procurement.id, paymentTerms.value)
    }
    return
  }

  if (currentStep.value < 4) {
    if (currentStep.value === 3) {
      const termsError = validatePaymentTerms()
      formError.value = termsError || null
      if (termsError) return
    }
    goNextStep()
    return
  }

  const termsError = validatePaymentTerms()
  formError.value = termsError || null
  if (termsError) return

  const procurement = await saveDraft()
  if (procurement) {
    intakeStore.setTermsForProcurement(procurement.id, paymentTerms.value)
  }
}

const primaryActionLabel = computed(() => {
  if (!isEditMode.value) {
    return isSaving.value ? t('procurements.create.opening') : t('procurements.create.openDraftAction')
  }
  if (currentStep.value < 4) {
    return t('common.next')
  }
  return isSaving.value ? t('common.saving') : t('procurements.create.saveChanges')
})

const secondaryActionLabel = computed(() => {
  if (!isEditMode.value || currentStep.value === 1) return ''
  return t('common.back')
})

watch(
  () => [selectedType.value, selectedSupplierId.value, notes.value] as const,
  ([type, supplierId, draftNotes]) => {
    if (isEditMode.value || isLinkedAgreementMode.value) return
    intakeStore.setBasics({
      selectedType: type,
      selectedSupplierId: supplierId,
      notes: draftNotes,
    })
  },
)

watch(
  () => [
    lines.value,
    expenses.value,
    contractCurrency.value,
    plannedBudget.value,
    contractRows.value,
    paymentTerms.value,
  ] as const,
  () => {
    intakeStore.setWorkspace({
      procurementId: editingProcurementId.value,
      lines: lines.value,
      expenses: expenses.value,
      contractCurrency: contractCurrency.value,
      plannedBudget: plannedBudget.value,
      contractRows: contractRows.value,
      terms: paymentTerms.value,
    })
  },
  { deep: true },
)

watch(
  () => route.query.step,
  (value) => {
    if (!isEditMode.value) return
    currentStep.value = parseQueryStep(value, currentStep.value)
  },
)

onMounted(async () => {
  referencesAbortController?.abort()
  const controller = new AbortController()
  referencesAbortController = controller
  isLoadingRefs.value = true
  try {
    const [supplierResponse, categoryResponse, partnerResponse] = await Promise.all([
      fetchSuppliers(undefined, controller.signal),
      fetchCategories(undefined, controller.signal),
      fetchPartners({ is_active: true }, controller.signal),
      loadLatestUsdRate(),
    ])
    if (referencesAbortController !== controller) return
    suppliers.value = supplierResponse.results
    categories.value = categoryResponse
    partners.value = partnerResponse
    resetDraftForm()
    currentStep.value = isEditMode.value
      ? parseQueryStep(route.query.step, Math.max(2, intakeStore.draft.currentStep))
      : 1
    if (!isEditMode.value && !isLinkedAgreementMode.value) {
      applyStoredBasics()
    }
    if (isLinkedAgreementMode.value && linkedAgreementId.value) {
      await loadLinkedAgreementIfNeeded()
    }
    await loadExistingDraft()
    if (isEditMode.value) {
      await loadAllVariants()
      restoreStoredWorkspace()
    }
  } catch (error: unknown) {
    const requestError = error as { code?: string; name?: string }
    if (requestError.code === 'ERR_CANCELED' || requestError.name === 'CanceledError') return
    toast.error(t('products.loadFormDictionariesFailed'))
  } finally {
    if (referencesAbortController === controller) {
      referencesAbortController = null
      isLoadingRefs.value = false
    }
  }
})

onBeforeUnmount(() => {
  referencesAbortController?.abort()
})
</script>

<template>
  <div class="create-page">
    <header class="page-header">
      <button class="btn-back" :aria-label="t('common.back')" @click="router.back()">
        <ArrowLeft :size="20" :stroke-width="1.75" />
      </button>
      <h1 class="page-title">{{ isEditMode ? t('procurements.create.editTitle') : t('procurements.create.newTitle') }}</h1>
      <div class="header-spacer" />
    </header>

    <div class="form-body">
      <IntakeWizardProgress
        :steps="wizardSteps"
        :current-step="currentStep"
        :max-reachable-step="maxReachableStep"
        @select="goToStep"
      />

      <IntakeStepBasics
        v-if="currentStep === 1"
        :linked-agreement-id="linkedAgreement?.id ?? null"
        :cards="TYPE_CARDS"
        :selected-type="selectedType"
        :is-linked-agreement-mode="isLinkedAgreementMode"
        :is-partnership-type="isPartnershipType"
        :is-contract-editable="isContractEditable"
        :supplier-options="supplierOptions"
        :selected-supplier-id="selectedSupplierId"
        :is-loading-refs="isLoadingRefs"
        :notes="notes"
        :investor-options="investorOptions"
        :has-linked-investors="hasLinkedInvestors"
        :investor-contract-row="investorContractRow"
        :operator-contract-row="operatorContractRow"
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
        @select-type="(type) => { selectedType = type; applyDefaultContract() }"
        @open-quick-supplier="openQuickSupplierCreator"
        @open-investor-invite="openInvestorInvitePage"
        @update-selected-supplier-id="(value) => { selectedSupplierId = value }"
        @update-notes="(value) => { notes = value }"
        @update-contract-role="(role, field, value) => updateContractRole(role, field, value)"
        @update-contract-currency="(value) => { contractCurrency = value }"
        @update-planned-budget="(value) => { plannedBudget = value }"
        @toggle-recalculation="isRecalculationOpen = !isRecalculationOpen"
        @set-simulation-capital-percent="setSimulationCapitalPercent"
        @reset-simulation="resetSimulation"
      />

      <IntakeStepProducts
        v-else-if="currentStep === 2"
        :lines="lines"
        :variant-display="variantDisplay"
        :normalize-currency="normalizeCurrency"
        :show-fx-field="showFxField"
        :format-currency-total-label="formatCurrencyTotalLabel"
        @open-quick-product="openQuickProductCreator"
        @add-line="addEmptyLine"
        @open-variant-picker="openVariantPicker"
        @remove-line="removeLine"
        @update-line="(rowId, field, value) => updateLine(rowId, field, value)"
        @toggle-line-currency="toggleLineCurrency"
      />

      <IntakeStepTerms
        v-else-if="currentStep === 3"
        :is-partnership-type="isPartnershipType"
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
        :expenses="expenses"
        :expense-type-options="expenseTypeOptions"
        :allocation-options="allocationOptions"
        :show-fx-field="showFxField"
        :format-currency-total-label="formatCurrencyTotalLabel"
        :terms="paymentTerms"
        :supplier-selected="selectedSupplierId !== null"
        :obligation-total="obligationTotal"
        @open-investor-invite="openInvestorInvitePage"
        @update-contract-role="(role, field, value) => updateContractRole(role, field, value)"
        @update-contract-currency="(value) => { contractCurrency = value }"
        @update-planned-budget="(value) => { plannedBudget = value }"
        @toggle-recalculation="isRecalculationOpen = !isRecalculationOpen"
        @set-simulation-capital-percent="setSimulationCapitalPercent"
        @reset-simulation="resetSimulation"
        @add-expense="addExpense"
        @remove-expense="removeExpense"
        @update-expense="(rowId, field, value) => updateExpense(rowId, field, value)"
        @toggle-expense-currency="toggleExpenseCurrency"
        @update-terms="(value) => { paymentTerms = value }"
      />

      <IntakeStepConfirm
        v-else
        :selected-type="selectedType"
        :supplier-options="supplierOptions"
        :selected-supplier-id="selectedSupplierId"
        :notes="notes"
        :item-count="lines.length"
        :expense-count="expenses.length"
        :has-foreign-currency="hasForeignCurrency"
        :grand-total="grandTotal"
        :expense-total="expenseTotal"
        :procurement-total="procurementTotal"
        :obligation-total="obligationTotal"
        :terms="paymentTerms"
        :format-price="formatPrice"
      />

      <div v-if="formError" class="error-box">
        <AlertCircle :size="18" :stroke-width="1.75" />
        <span>{{ formError }}</span>
      </div>
    </div>

    <footer class="footer-actions">
      <div class="footer-actions-grid">
        <BaseButton
          v-if="secondaryActionLabel"
          type="button"
          variant="secondary"
          size="md"
          :full-width="true"
          @click="goPrevStep"
        >
          {{ secondaryActionLabel }}
        </BaseButton>
        <BaseButton
          type="button"
          variant="primary"
          size="md"
          :full-width="true"
          :loading="isSaving"
          :disabled="isLoadingDraft || (currentStep === 2 && !hasDraftLines)"
          @click="handlePrimaryAction"
        >
          {{ primaryActionLabel }}
        </BaseButton>
      </div>
    </footer>

    <IntakeVariantPickerSheet
      :open="variantSheetOpen"
      :variant-search="variantSearch"
      :category-options="categoryOptions"
      :selected-category="variantSearchCategory"
      :filtered-variants="filteredVariants"
      :variant-display="variantDisplay"
      @close="closeVariantPicker"
      @update-variant-search="(value) => { variantSearch = value }"
      @open-quick-product="openQuickProductCreator(activeLineId)"
      @update-selected-category="(value) => { variantSearchCategory = value }"
      @select-variant="selectVariant"
    />

    <IntakeQuickProductSheet
      :open="quickProductSheetOpen"
      :quick-product-name="quickProductName"
      :quick-product-category-id="quickProductCategoryId"
      :quick-product-base-price="quickProductBasePrice"
      :quick-product-error="quickProductError"
      :is-creating-quick-product="isCreatingQuickProduct"
      :category-options="categoryOptions"
      @close="closeQuickProductCreator"
      @submit="createQuickProduct"
      @update-quick-product-name="(value) => { quickProductName = value }"
      @update-quick-product-category-id="(value) => { quickProductCategoryId = value }"
      @update-quick-product-base-price="(value) => { quickProductBasePrice = value }"
    />

    <IntakeQuickSupplierSheet
      :open="quickSupplierSheetOpen"
      :quick-supplier-name="quickSupplierName"
      :quick-supplier-phone="quickSupplierPhone"
      :quick-supplier-email="quickSupplierEmail"
      :quick-supplier-error="quickSupplierError"
      :is-creating-quick-supplier="isCreatingQuickSupplier"
      @close="closeQuickSupplierCreator"
      @submit="createQuickSupplier"
      @update-quick-supplier-name="(value) => { quickSupplierName = value }"
      @update-quick-supplier-phone="(value) => { quickSupplierPhone = value }"
      @update-quick-supplier-email="(value) => { quickSupplierEmail = value }"
    />
  </div>
</template>

<style scoped>
.create-page { min-height: 100%; background: var(--color-bg-primary); }
.page-header { position: sticky; top: 0; z-index: var(--z-sticky); display: flex; align-items: center; gap: var(--space-3); height: var(--header-height); padding: 0 var(--space-4); background: var(--color-bg-primary); border-bottom: 1px solid var(--color-border-subtle); }
.btn-back,.header-spacer { width: 40px; height: 40px; display:inline-flex; align-items:center; justify-content:center; border-radius: var(--radius-md); color: var(--color-text-primary); }
.page-title { flex:1; font-size: var(--text-lg); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.form-body { display:grid; gap: var(--space-4); padding: var(--space-4); padding-bottom: calc(var(--bottom-nav-height) + var(--space-12)); }
.error-box { display:flex; gap: var(--space-2); padding: var(--space-3) var(--space-4); border-radius: var(--radius-lg); }
.error-box { background: var(--color-error-bg); color: var(--color-danger); }
.footer-actions { position: sticky; bottom: 0; padding: var(--space-4); background: linear-gradient(to top, var(--color-bg-primary), transparent); }
.footer-actions-grid { display: grid; gap: var(--space-3); grid-template-columns: minmax(0, 1fr); }
@media (min-width: 768px) {
  .footer-actions-grid { grid-template-columns: minmax(0, 160px) minmax(0, 1fr); }
}
</style>
