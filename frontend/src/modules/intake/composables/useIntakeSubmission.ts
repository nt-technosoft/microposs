import type { ComputedRef, Ref } from 'vue'
import { createProcurement, updateProcurement } from '@/api/partnerships'
import type { ProcurementType } from '@/types/enums'
import type { ContractRow, ExpenseRow, LineRow, PaymentTermsDraft } from '@/modules/intake/types'

interface ToastLike {
  success: (message: string) => void
  error: (message: string) => void
}

interface UseIntakeSubmissionOptions {
  isSaving: Ref<boolean>
  formError: Ref<string | null>
  isEditMode: ComputedRef<boolean>
  editingProcurementId: ComputedRef<number | null>
  isLinkedAgreementMode: ComputedRef<boolean>
  linkedAgreementId: ComputedRef<number | null>
  selectedType: Ref<ProcurementType>
  selectedSupplierId: Ref<number | null>
  editingAgreementId: Ref<number | null>
  notes: Ref<string>
  lines: Ref<LineRow[]>
  expenses: Ref<ExpenseRow[]>
  paymentTerms: Ref<PaymentTermsDraft>
  obligationTotal: ComputedRef<number>
  contractRows: Ref<ContractRow[]>
  contractCurrency: Ref<string>
  plannedBudgetAmount: ComputedRef<number>
  isPartnershipType: ComputedRef<boolean>
  capitalPercentTotal: ComputedRef<number>
  profitTotal: ComputedRef<number>
  mudarabaRatio: ComputedRef<number>
  investorProfitShare: ComputedRef<number>
  expectedProfitByRole: ComputedRef<{ investor: number; operator: number }>
  normalizeCurrency: (value: unknown) => string
  getFxRateValue: (currency: string, raw: unknown) => number
  defaultFxRateForCurrency: (currency: string) => string
  showFxField: (currency: string) => boolean
  generateRequestId: () => string
  router: { push: (...args: any[]) => Promise<unknown> }
  toast: ToastLike
  t: (key: string, params?: Record<string, unknown>) => string
}

interface SaveDraftOptions {
  redirectTo?: {
    name: string
    params?: Record<string, string | number>
    query?: Record<string, string | number>
  } | ((procurement: { id: number }) => {
    name: string
    params?: Record<string, string | number>
    query?: Record<string, string | number>
  })
}

export function useIntakeSubmission({
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
}: UseIntakeSubmissionOptions) {
  function buildTermsPayload() {
    const terms = paymentTerms.value
    const currency = normalizeCurrency(terms.currency_of_obligation)
    const schedule = terms.type === 'INSTALLMENT'
      ? terms.schedule
          .filter((row) => row.due_date && Number.parseFloat(row.amount) > 0)
          .map((row, index) => ({
            sequence_number: index + 1,
            due_date: row.due_date,
            amount: Number.parseFloat(row.amount),
            currency,
          }))
      : []

    return {
      terms: {
        type: terms.type,
        currency_of_obligation: currency,
        fx_rate_at_obligation: String(getFxRateValue(currency, terms.fx_rate_at_obligation) || defaultFxRateForCurrency(currency)),
        total_amount_due: obligationTotal.value.toFixed(2),
        paid_amount: terms.type === 'PARTIAL' ? (Number.parseFloat(terms.paid_amount) || 0).toFixed(2) : '0',
        deadline_date: terms.type === 'DEFERRED' && terms.deadline_date ? terms.deadline_date : null,
        consignment_agreement_id: terms.type === 'CONSIGNMENT' ? terms.consignment_agreement_id : null,
        notes: terms.notes.trim(),
      },
      schedule,
    }
  }

  function validate() {
    const seenVariantIds = new Set<number>()
    for (const line of lines.value) {
      if (!line.variant) return t('procurements.create.validationChooseEveryProduct')
      if (seenVariantIds.has(line.variant.id)) return t('procurements.create.validationDuplicateProduct')
      seenVariantIds.add(line.variant.id)
      if (!line.quantity || parseFloat(line.quantity) <= 0) return t('procurements.create.validationQuantity')
      if (!line.cost_per_unit || parseFloat(line.cost_per_unit) <= 0) return t('procurements.create.validationPurchasePrice')
      if (showFxField(line.currency) && getFxRateValue(line.currency, line.fx_rate) <= 0) return t('procurements.create.validationItemFxRate')
    }

    for (const expense of expenses.value) {
      if (!expense.amount || parseFloat(expense.amount) <= 0) return t('procurements.create.validationExpenseAmount')
      if (showFxField(expense.currency) && getFxRateValue(expense.currency, expense.fx_rate) <= 0) return t('procurements.create.validationExpenseFxRate')
    }

    if (isPartnershipType.value) {
      if (contractRows.value.some((row) => !row.partner_id)) return t('procurements.create.validationChoosePartners')
      if (new Set(contractRows.value.map((row) => row.partner_id)).size !== contractRows.value.length) return t('procurements.create.validationUniquePartners')
      if (!contractRows.value.some((row) => row.role === 'OPERATOR')) return t('procurements.create.validationBusinessMissing')
      if (!contractRows.value.some((row) => row.role === 'INVESTOR')) return t('procurements.create.validationInvestorMissing')
      if (plannedBudgetAmount.value <= 0) return t('procurements.create.validationPlannedBudget')
      if (capitalPercentTotal.value <= 0) return t('procurements.create.validationCapital')
      if (Math.abs(capitalPercentTotal.value - 100) > 0.0001) return t('procurements.create.validationCapitalTotal')
      if (Math.abs(profitTotal.value - 100) > 0.01) return t('procurements.create.validationProfitTotal')
      if (!Number.isFinite(mudarabaRatio.value) || mudarabaRatio.value < 0 || mudarabaRatio.value > 1) return t('procurements.create.validationMudaraba')
      const investorProfitPercent = investorProfitShare.value * 100
      if (Math.abs(investorProfitPercent - expectedProfitByRole.value.investor * 100) > 0.05) {
        return t('procurements.create.validationInvestorProfitFormula')
      }
    }
    return ''
  }

  async function saveDraft(options: SaveDraftOptions = {}): Promise<{ id: number } | null> {
    const validation = validate()
    formError.value = validation || null
    if (validation) return null

    isSaving.value = true
    try {
      const contract = isPartnershipType.value
        ? {
            mudaraba_ratio: mudarabaRatio.value.toFixed(6),
            planned_budget: plannedBudgetAmount.value.toFixed(2),
            currency: normalizeCurrency(contractCurrency.value),
            partners: contractRows.value.map((row) => ({
              partner_id: row.partner_id as number,
              role: row.role,
              planned_capital_share: (plannedBudgetAmount.value * ((Number.parseFloat(row.capital_percent) || 0) / 100)).toFixed(2),
              profit_share: ((Number.parseFloat(row.profit_percent) || 0) / 100).toFixed(6),
            })),
          }
        : undefined

      const payload = {
        client_request_id: isEditMode.value ? undefined : generateRequestId(),
        procurement_type: selectedType.value,
        supplier_id: selectedSupplierId.value,
        agreement_id: isLinkedAgreementMode.value ? linkedAgreementId.value : editingAgreementId.value,
        notes: notes.value.trim(),
        items: lines.value.map((line) => ({
          product_variant_id: line.variant!.id,
          quantity: parseFloat(line.quantity),
          unit_purchase_price: parseFloat(line.cost_per_unit),
          currency: normalizeCurrency(line.currency),
          fx_rate: String(getFxRateValue(line.currency, line.fx_rate) || defaultFxRateForCurrency(line.currency)),
        })),
        expenses: expenses.value.map((expense) => ({
          expense_type: expense.expense_type,
          amount: Number.parseFloat(expense.amount),
          currency: normalizeCurrency(expense.currency),
          fx_rate: String(getFxRateValue(expense.currency, expense.fx_rate) || defaultFxRateForCurrency(expense.currency)),
          allocation_method: expense.allocation_method,
          notes: expense.notes.trim(),
        })),
        contract,
        ...buildTermsPayload(),
      }

      const procurement = isEditMode.value && editingProcurementId.value !== null
        ? await updateProcurement(editingProcurementId.value, payload)
        : await createProcurement(payload)

      toast.success(isEditMode.value ? t('procurements.create.updated') : t('procurements.create.opened'))
      const nextTarget = typeof options.redirectTo === 'function'
        ? options.redirectTo(procurement)
        : options.redirectTo
      await router.push(nextTarget ?? { name: 'procurement-detail', params: { id: procurement.id } })
      return procurement
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : (isEditMode.value ? t('procurements.create.updateFailed') : t('procurements.create.openFailed'))
      formError.value = msg
      toast.error(msg)
      return null
    } finally {
      isSaving.value = false
    }
  }

  return {
    validate,
    saveDraft,
  }
}
