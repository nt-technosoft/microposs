import type { ProductVariant } from '@/types/models'

export interface LineRow {
  id: string
  variant: ProductVariant | null
  quantity: string
  cost_per_unit: string
  currency: string
  fx_rate: string
}

export interface ExpenseRow {
  id: string
  expense_type: 'CUSTOMS' | 'LOGISTICS' | 'FEE' | 'OTHER'
  amount: string
  currency: string
  fx_rate: string
  allocation_method: 'BY_VALUE' | 'BY_QUANTITY'
  notes: string
}

export interface ContractRow {
  id: string
  partner_id: number | null
  role: 'INVESTOR' | 'OPERATOR'
  capital_percent: string
  profit_percent: string
}

export type ProcurementTermsType =
  | 'PREPAID'
  | 'PARTIAL'
  | 'DEFERRED'
  | 'INSTALLMENT'
  | 'CONSIGNMENT'

export interface PaymentScheduleDraftRow {
  id: string
  due_date: string
  amount: string
}

export interface PaymentTermsDraft {
  type: ProcurementTermsType
  currency_of_obligation: string
  fx_rate_at_obligation: string
  paid_amount: string
  deadline_date: string
  consignment_agreement_id: number | null
  notes: string
  schedule: PaymentScheduleDraftRow[]
}
