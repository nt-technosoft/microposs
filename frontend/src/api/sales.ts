/**
 * API client for sales domain.
 */

import api from './client'
import { PaymentMethod } from '@/types/enums'
import type { PosSession, Sale } from '../types/models'
import { toPaginated, type PaginatedResponse } from './catalog'

export interface SaleLineInput {
  product_variant_id: number
  quantity: number
  unit_price: number
  operation_currency?: string
  operation_unit_price?: string | number | null
  fx_rate?: string | number | null
  discount_reason_id?: number
}

export interface SalePaymentInput {
  amount: string
  currency: string
  fx_rate?: string
  method: PaymentMethod
  account_id?: number | null
}

export interface SaleCreatePayload {
  client_request_id?: string
  pos_session_id: number
  location_id?: number
  customer_id?: number | null
  payment_method?: string
  lines: SaleLineInput[]
  payments?: SalePaymentInput[]
  notes?: string
}

export interface OpenSessionPayload {
  location_id: number
  opening_cash: number
  opening_cash_by_currency?: Record<string, string | number>
}

export interface CloseSessionPayload {
  actual_cash: number
  actual_cash_by_currency?: Record<string, string | number>
}

export interface ReturnLinePayload {
  sale_line_id: number
  quantity: number
}

export type ReturnResolution = 'RESTOCK' | 'DISPOSE'
export type ReturnReason = 'CLIENT_REFUSE' | 'DEFECT' | 'OTHER'

export interface ReturnRefundPaymentPayload {
  method: PaymentMethod | 'RECEIVABLE_OFFSET'
  amount: string
  currency: string
  fx_rate?: string
  account_id?: number | null
}

export interface ReturnCreatePayload {
  resolution: ReturnResolution
  reason?: ReturnReason
  lines: ReturnLinePayload[]
  refund_payments?: ReturnRefundPaymentPayload[]
  notes?: string
}

export interface SaleReturn {
  id: number
  sale: number
  resolution: ReturnResolution
  reason: ReturnReason
  date: string
  created_at: string
  notes: string
  lines: ReturnLinePayload[]
  refunds?: Array<{
    id: number
    amount: string
    currency: string
    fx_rate: string
    method: string
    account_id: number | null
  }>
}

export interface SaleReturnPreviewLine {
  sale_line_id: number
  product_name: string
  variant_name: string
  lot_id: number
  sold_quantity: number
  already_returned_quantity: number
  available_quantity: number
  selected_quantity: number
  unit_price_uzs: string
  unit_landed_cost_uzs: string
  operation_currency: string
  operation_unit_price: string
  fx_rate_snapshot: string
}

export interface SaleReturnPreview {
  sale_id: number
  sale_status: string
  resolution: ReturnResolution
  status: 'READY' | 'BLOCKED'
  remaining_refundable_by_currency: Record<string, string>
  lines: SaleReturnPreviewLine[]
  selected: {
    refund_amount_uzs: string
    profit_reversal_uzs: string
    restock_cogs_uzs: string
    disposal_loss_uzs: string
  }
}

export interface SaleExplanationPartnerSplit {
  partner_id: number | null
  partner_name: string
  role: 'INVESTOR' | 'OPERATOR' | 'UNKNOWN'
  capital_share: string | null
  profit_share: string | null
  profit_amount: string
}

export interface SaleExplanationLine {
  sale_line_id: number
  product_name: string
  quantity: number
  unit_price: string
  operation_currency?: string
  operation_unit_price?: string | null
  fx_rate_snapshot?: string | null
  revenue: string
  unit_purchase_price: string
  purchase_cost: string
  unit_landed_cost: string
  landed_cost: string
  gross_profit: string
  margin_percent: string
  lot: {
    id: number
    received_at: string | null
    quantity_initial: number
    quantity_remaining: number
    unit_purchase_price: string
    landed_cost_per_unit: string
  }
  procurement: null | {
    id: number
    procurement_type: string
    status: string
    opened_at: string
    received_at: string | null
    supplier_name: string | null
  }
  partner_split: SaleExplanationPartnerSplit[]
}

export interface SaleExplanationCashEntry {
  id: number
  date: string
  payment_id: number | null
  payment_method: string | null
  account_name: string
  currency?: string
  direction: string
  amount: string
}

export interface SaleExplanationReceivableEntry {
  id: number
  date: string
  entry_type: string
  amount: string
  currency: string
  fx_rate: string
  source_ref: string
}

export interface SaleExplanationJournalLine {
  id: number
  account_code: string
  account_name: string
  debit: string
  credit: string
  description: string
}

export interface SaleExplanationJournalEntry {
  id: number
  date: string
  description: string
  total_debit: string
  total_credit: string
  lines: SaleExplanationJournalLine[]
}

export interface SaleExplanationLedgerEntry {
  id: number
  date: string
  entry_type: string
  amount: string
  currency: string
  functional_amount_uzs: string
  source_ref: string
  partner_id: number
  partner_name: string
  partner_role: string
  procurement_id: number
}

export interface SaleExplanation {
  sale: {
    id: number
    date: string
    created_at: string
    status: string
    location_name: string
    customer_name: string | null
    pos_session_id: number | null
    payment_methods: string[]
    paid_total: string
    credit_total: string
    revenue: string
    landed_cost: string
    gross_profit: string
    investor_profit: string
    business_profit: string
    margin_percent: string
    notes: string
  }
  payments: Array<{
    id: number
    date: string
    method: string
  amount: string
  currency: string
  fx_rate: string
  functional_amount_uzs?: string
  account_id: number | null
  }>
  cash_entries: SaleExplanationCashEntry[]
  receivable_entries: SaleExplanationReceivableEntry[]
  journal_entries: SaleExplanationJournalEntry[]
  ledger_entries: SaleExplanationLedgerEntry[]
  lines: SaleExplanationLine[]
}

interface FetchSessionsParams {
  status?: 'open' | 'closed'
  location?: number
  page?: number
}

interface FetchSalesParams {
  session?: number
  payment_method?: string
  status?: string
  page?: number
}

export async function fetchSessions(params?: FetchSessionsParams): Promise<PaginatedResponse<PosSession>> {
  const { data } = await api.get<PaginatedResponse<PosSession> | PosSession[]>('/api/v1/sales/sessions/', { params })
  return toPaginated<PosSession>(data)
}

export async function openSession(payload: OpenSessionPayload): Promise<PosSession> {
  const { data } = await api.post<PosSession>('/api/v1/sales/sessions/open/', payload)
  return data
}

export async function closeSession(sessionId: number, payload: CloseSessionPayload): Promise<PosSession> {
  const { data } = await api.post<PosSession>(`/api/v1/sales/sessions/${sessionId}/close/`, payload)
  return data
}

export async function fetchSales(params?: FetchSalesParams): Promise<PaginatedResponse<Sale>> {
  const { data } = await api.get<PaginatedResponse<Sale> | Sale[]>('/api/v1/sales/sales/', { params })
  return toPaginated<Sale>(data)
}

export async function fetchSale(id: number): Promise<Sale> {
  const { data } = await api.get<Sale>(`/api/v1/sales/sales/${id}/`)
  return data
}

export async function fetchSaleExplanation(id: number): Promise<SaleExplanation> {
  const { data } = await api.get<SaleExplanation>(`/api/v1/sales/sales/${id}/explanation/`)
  return data
}

export async function createSale(payload: SaleCreatePayload): Promise<Sale> {
  const payments = payload.payments && payload.payments.length > 0
    ? payload.payments
    : payload.payment_method
      ? [{
          amount: payload.lines
            .reduce((sum, line) => sum + Number(line.unit_price) * line.quantity, 0)
            .toFixed(2),
          currency: 'UZS',
          method: payload.payment_method as PaymentMethod,
        }]
      : []

  const body = {
    client_request_id: payload.client_request_id,
    pos_session_id: payload.pos_session_id,
    customer_id: payload.customer_id,
    lines: payload.lines,
    payments,
    notes: payload.notes,
    ...(payload.location_id !== undefined ? { location_id: payload.location_id } : {}),
  }

  const { data } = await api.post<Sale>('/api/v1/sales/sales/', body)
  return data
}

export async function processReturn(saleId: number, payload: ReturnCreatePayload): Promise<SaleReturn> {
  const { data } = await api.post<SaleReturn>(`/api/v1/sales/sales/${saleId}/return/`, payload)
  return data
}

export async function fetchReturnPreview(
  saleId: number,
  payload: ReturnCreatePayload,
): Promise<SaleReturnPreview> {
  const { data } = await api.post<SaleReturnPreview>(`/api/v1/sales/sales/${saleId}/return-preview/`, payload)
  return data
}
