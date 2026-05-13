import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ProcurementType } from '@/types/enums'
import type { ContractRow, ExpenseRow, LineRow, PaymentTermsDraft } from '@/modules/intake/types'

const STORAGE_KEY = 'microposs_intake_wizard_v1'
const MIN_STEP = 1
const MAX_STEP = 4

interface IntakeWizardDraft {
  selectedType: ProcurementType
  selectedSupplierId: number | null
  notes: string
  currentStep: number
  workspaceProcurementId: number | null
  lines: Array<{
    id: string
    variant_id: number | null
    quantity: string
    cost_per_unit: string
    currency: string
    fx_rate: string
  }>
  expenses: ExpenseRow[]
  contractCurrency: string
  plannedBudget: string
  contractRows: ContractRow[]
  terms: PaymentTermsDraft
  termsByProcurementId: Record<string, PaymentTermsDraft>
}

function clampStep(value: number | null | undefined): number {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return MIN_STEP
  return Math.min(MAX_STEP, Math.max(MIN_STEP, Math.trunc(parsed)))
}

function defaultDraft(): IntakeWizardDraft {
  return {
    selectedType: ProcurementType.OWN_FUNDS,
    selectedSupplierId: null,
    notes: '',
    currentStep: MIN_STEP,
    workspaceProcurementId: null,
    lines: [],
    expenses: [],
    contractCurrency: 'USD',
    plannedBudget: '',
    contractRows: [],
    terms: defaultTermsDraft(),
    termsByProcurementId: {},
  }
}

export function defaultTermsDraft(): PaymentTermsDraft {
  return {
    type: 'PREPAID',
    currency_of_obligation: 'USD',
    fx_rate_at_obligation: '1',
    paid_amount: '',
    deadline_date: '',
    consignment_agreement_id: null,
    notes: '',
    schedule: [],
  }
}

function loadDraft(): IntakeWizardDraft {
  if (typeof window === 'undefined') return defaultDraft()
  const raw = localStorage.getItem(STORAGE_KEY)
  if (!raw) return defaultDraft()

  try {
    const parsed = JSON.parse(raw) as Partial<IntakeWizardDraft>
    return {
      selectedType: Object.values(ProcurementType).includes(parsed.selectedType as ProcurementType)
        ? (parsed.selectedType as ProcurementType)
        : ProcurementType.OWN_FUNDS,
      selectedSupplierId: typeof parsed.selectedSupplierId === 'number' ? parsed.selectedSupplierId : null,
      notes: typeof parsed.notes === 'string' ? parsed.notes : '',
      currentStep: clampStep(parsed.currentStep),
      workspaceProcurementId: typeof parsed.workspaceProcurementId === 'number' ? parsed.workspaceProcurementId : null,
      lines: Array.isArray(parsed.lines) ? parsed.lines : [],
      expenses: Array.isArray(parsed.expenses) ? parsed.expenses : [],
      contractCurrency: typeof parsed.contractCurrency === 'string' ? parsed.contractCurrency : 'USD',
      plannedBudget: typeof parsed.plannedBudget === 'string' ? parsed.plannedBudget : '',
      contractRows: Array.isArray(parsed.contractRows) ? parsed.contractRows : [],
      terms: {
        ...defaultTermsDraft(),
        ...(parsed.terms && typeof parsed.terms === 'object' ? parsed.terms : {}),
      },
      termsByProcurementId: parsed.termsByProcurementId && typeof parsed.termsByProcurementId === 'object'
        ? parsed.termsByProcurementId
        : {},
    }
  } catch {
    return defaultDraft()
  }
}

export const useIntakeStore = defineStore('intake', () => {
  const draft = ref<IntakeWizardDraft>(loadDraft())

  function persist(): void {
    if (typeof window === 'undefined') return
    localStorage.setItem(STORAGE_KEY, JSON.stringify(draft.value))
  }

  function setBasics(payload: Partial<Omit<IntakeWizardDraft, 'currentStep'>>): void {
    draft.value = {
      ...draft.value,
      ...payload,
    }
    persist()
  }

  function setWorkspace(payload: {
    procurementId?: number | null
    lines?: LineRow[]
    expenses?: ExpenseRow[]
    contractCurrency?: string
    plannedBudget?: string
    contractRows?: ContractRow[]
    terms?: PaymentTermsDraft
  }): void {
    draft.value = {
      ...draft.value,
      workspaceProcurementId: payload.procurementId ?? draft.value.workspaceProcurementId,
      lines: payload.lines
        ? payload.lines.map((line) => ({
            id: line.id,
            variant_id: line.variant?.id ?? null,
            quantity: line.quantity,
            cost_per_unit: line.cost_per_unit,
            currency: line.currency,
            fx_rate: line.fx_rate,
          }))
        : draft.value.lines,
      expenses: payload.expenses ?? draft.value.expenses,
      contractCurrency: payload.contractCurrency ?? draft.value.contractCurrency,
      plannedBudget: payload.plannedBudget ?? draft.value.plannedBudget,
      contractRows: payload.contractRows ?? draft.value.contractRows,
      terms: payload.terms ?? draft.value.terms,
    }
    persist()
  }

  function setStep(step: number): void {
    draft.value = {
      ...draft.value,
      currentStep: clampStep(step),
    }
    persist()
  }

  function setTermsForProcurement(procurementId: number, terms: PaymentTermsDraft): void {
    draft.value = {
      ...draft.value,
      termsByProcurementId: {
        ...draft.value.termsByProcurementId,
        [String(procurementId)]: terms,
      },
    }
    persist()
  }

  function getTermsForProcurement(procurementId: number): PaymentTermsDraft | null {
    return draft.value.termsByProcurementId[String(procurementId)] ?? null
  }

  function resetDraft(): void {
    draft.value = defaultDraft()
    persist()
  }

  return {
    draft,
    setBasics,
    setWorkspace,
    setStep,
    setTermsForProcurement,
    getTermsForProcurement,
    resetDraft,
  }
})
