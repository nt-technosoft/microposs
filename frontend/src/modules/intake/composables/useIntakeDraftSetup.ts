import type { Ref } from 'vue'
import { ProcurementType } from '@/types/enums'
import { fetchInvestmentAgreement, fetchProcurement, type InvestmentAgreementDetail, type ProcurementDetail } from '@/api/partnerships'
import type { Partner } from '@/api/core'
import type { ProductVariant } from '@/types/models'
import type { ContractRow, ExpenseRow, LineRow, PaymentTermsDraft } from '@/modules/intake/types'
import { defaultTermsDraft } from '@/stores/intake'

interface UseIntakeDraftSetupOptions {
  selectedType: Ref<ProcurementType>
  editingAgreementId: Ref<number | null>
  selectedSupplierId: Ref<number | null>
  notes: Ref<string>
  lines: Ref<LineRow[]>
  expenses: Ref<ExpenseRow[]>
  paymentTerms: Ref<PaymentTermsDraft>
  contractCurrency: Ref<string>
  plannedBudget: Ref<string>
  contractRows: Ref<ContractRow[]>
  partners: Ref<Partner[]>
  allVariants: Ref<ProductVariant[]>
  linkedAgreement: Ref<InvestmentAgreementDetail | null>
  linkedAgreementId: Ref<number | null>
  editingProcurementId: Ref<number | null>
  isLoadingDraft: Ref<boolean>
  hasBalanceActivity: Ref<boolean>
  normalizeCurrency: (value: unknown) => string
  buildDefaultContractRows: () => ContractRow[]
  placeholderVariantFromProcurementItem: (item: ProcurementDetail['items'][number]) => ProductVariant
  formatEditablePercent: (value: number) => string
  t: (key: string, params?: Record<string, unknown>) => string
}

export function useIntakeDraftSetup({
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
}: UseIntakeDraftSetupOptions) {
  function resetDraftForm(): void {
    hasBalanceActivity.value = false
    selectedType.value = ProcurementType.OWN_FUNDS
    editingAgreementId.value = null
    selectedSupplierId.value = null
    notes.value = ''
    lines.value = []
    expenses.value = []
    paymentTerms.value = defaultTermsDraft()
    contractCurrency.value = 'USD'
    plannedBudget.value = ''
    contractRows.value = buildDefaultContractRows()
  }

  function applyLinkedAgreementDefaults(): void {
    hasBalanceActivity.value = false
    const agreement = linkedAgreement.value
    if (!agreement) return
    selectedType.value = ProcurementType.PARTNERSHIP
    selectedSupplierId.value = agreement.supplier
    contractCurrency.value = normalizeCurrency(agreement.currency)
    plannedBudget.value = String(agreement.planned_budget)
    contractRows.value = agreement.partners.map((partner) => ({
      id: crypto.randomUUID(),
      partner_id: partner.partner,
      role: partner.role as ContractRow['role'],
      capital_percent: Number(agreement.planned_budget) > 0
        ? formatEditablePercent((Number(partner.planned_capital_share) / Number(agreement.planned_budget)) * 100)
        : '0',
      profit_percent: formatEditablePercent(Number(partner.profit_share) * 100),
    }))
  }

  function populateFormFromProcurement(procurement: ProcurementDetail): void {
    hasBalanceActivity.value = (procurement.balance?.history?.length ?? 0) > 0
    selectedType.value = procurement.procurement_type as ProcurementType
    editingAgreementId.value = procurement.agreement
    selectedSupplierId.value = procurement.supplier
    notes.value = procurement.notes ?? ''
    lines.value = procurement.items.map((item) => {
      const variant = allVariants.value.find((entry) => entry.id === item.product_variant)
      return {
        id: crypto.randomUUID(),
        variant: variant ?? placeholderVariantFromProcurementItem(item),
        quantity: String(item.quantity),
        cost_per_unit: String(item.unit_purchase_price),
        currency: normalizeCurrency(item.currency),
        fx_rate: String(item.fx_rate),
      }
    })
    expenses.value = procurement.expenses.map((expense) => ({
      id: crypto.randomUUID(),
      expense_type: expense.expense_type as ExpenseRow['expense_type'],
      amount: String(expense.amount),
      currency: normalizeCurrency(expense.currency),
      fx_rate: String(expense.fx_rate),
      allocation_method: expense.allocation_method as ExpenseRow['allocation_method'],
      notes: expense.notes ?? '',
    }))
    paymentTerms.value = procurement.terms
      ? {
          type: procurement.terms.type as PaymentTermsDraft['type'],
          currency_of_obligation: normalizeCurrency(procurement.terms.currency_of_obligation),
          fx_rate_at_obligation: String(procurement.terms.fx_rate_at_obligation),
          paid_amount: String(procurement.terms.paid_amount),
          deadline_date: procurement.terms.deadline_date ?? '',
          consignment_agreement_id: procurement.terms.consignment_agreement,
          notes: procurement.terms.notes ?? '',
          schedule: procurement.terms.schedule.map((row) => ({
            id: crypto.randomUUID(),
            due_date: row.due_date,
            amount: String(row.amount),
          })),
        }
      : defaultTermsDraft()

    if (procurement.contract) {
      contractCurrency.value = normalizeCurrency(procurement.contract.currency)
      plannedBudget.value = String(procurement.contract.planned_budget)
      const budget = Number(procurement.contract.planned_budget) || 0
      contractRows.value = procurement.contract.partners.map((partner) => ({
        id: crypto.randomUUID(),
        partner_id: partner.partner,
        role: partner.role as ContractRow['role'],
        capital_percent: budget > 0
          ? formatEditablePercent((Number(partner.planned_capital_share) / budget) * 100)
          : '0',
        profit_percent: formatEditablePercent(Number(partner.profit_share) * 100),
      }))
    } else {
      contractCurrency.value = 'USD'
      plannedBudget.value = ''
      contractRows.value = buildDefaultContractRows()
    }
  }

  async function loadExistingDraft(): Promise<void> {
    if (editingProcurementId.value === null) return
    isLoadingDraft.value = true
    try {
      const procurement = await fetchProcurement(editingProcurementId.value)
      if (procurement.status !== 'OPEN') {
        throw new Error(t('procurements.create.onlyOpenEditable'))
      }
      populateFormFromProcurement(procurement)
    } finally {
      isLoadingDraft.value = false
    }
  }

  async function loadLinkedAgreementIfNeeded(): Promise<void> {
    if (!linkedAgreementId.value) return
    linkedAgreement.value = await fetchInvestmentAgreement(linkedAgreementId.value)
    applyLinkedAgreementDefaults()
  }

  return {
    resetDraftForm,
    applyLinkedAgreementDefaults,
    populateFormFromProcurement,
    loadExistingDraft,
    loadLinkedAgreementIfNeeded,
  }
}
