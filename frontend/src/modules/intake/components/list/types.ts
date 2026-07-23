import type { ProcurementStatus } from '@/types/enums'

export type StatusFilter = 'all' | ProcurementStatus
export type AttentionView = 'to_pay' | 'to_receive' | 'overdue'
export type ProcurementView = StatusFilter | AttentionView

export interface FilterChip {
  value: StatusFilter
  label: string
}

export type MoneyByCurrency = Record<string, number>

export interface AttentionSignals {
  toPay: { count: number; remaining: MoneyByCurrency }
  toReceive: { count: number }
  overdue: { count: number }
}
