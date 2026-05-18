import type { ProductVariant } from '@/types/models'

export type CurrencyCode = 'UZS' | 'USD'
export type ExpenseType = 'CUSTOMS' | 'LOGISTICS' | 'FEE' | 'OTHER'
export type AllocationMethod = 'BY_VALUE' | 'BY_QUANTITY'

export interface SelectOption<T = string | number | null> {
  value: T
  label: string
}

export interface ItemTarget {
  id: number
  label: string
}

export interface DraftLineRow {
  id: string
  serverId: number | null
  variant: ProductVariant | null
  quantity: string
  cost_per_unit: string
  currency: CurrencyCode
  fx_rate: string
  locked_reason: string | null
}

export interface DraftExpenseRow {
  id: string
  serverId: number | null
  expense_type: ExpenseType
  amount: string
  currency: CurrencyCode
  fx_rate: string
  allocation_method: AllocationMethod
  notes: string
  target_item_ids: number[]
  locked_reason: string | null
}
