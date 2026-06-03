/**
 * API client for suppliers domain.
 */

import api from './client'
import type { Supplier } from '../types/models'
import { toPaginated, type PaginatedResponse } from './catalog'

export interface SupplierCreatePayload {
  name: string
  phone?: string
  email?: string
  notes?: string
}

export interface SupplierPaymentPayload {
  amount: number
  payment_method: 'cash' | 'bank'
  operation_currency?: string
  fx_rate_snapshot?: string | number | null
  notes?: string
}

export interface SupplierPayment {
  id: number
  supplier_id: number
  operation_currency?: string
  operation_amount?: string | null
  fx_rate_snapshot?: string | null
  fx_rate_source?: string
  fx_rate_date?: string | null
  functional_amount_uzs?: string | null
  amount: string
  payment_method: 'cash' | 'bank'
  notes: string
  created_at: string
}

export interface PayablesSummaryItem {
  id: number
  name: string
  phone: string
  outstanding_balance: string
}

export interface SupplierPayable {
  id: number
  supplier: number
  supplier_name: string
  procurement: number | null
  original_amount: string
  paid_amount: string
  remaining_amount: string
  currency_of_obligation: string
  fx_rate_at_obligation: string
  status: string
  reason: string
  deadline_date: string | null
  notes: string
  schedule: Array<{
    id: number
    sequence_number: number
    due_date: string
    amount: string
    currency: string
    status: string
    paid_at: string | null
    paid_amount: string
  }>
  created_at: string
  updated_at: string
}

export interface SupplierProductHistoryItem {
  product_variant_id: number
  product_id: number
  product_name: string
  variant_sku: string
  last_received_at: string | null
  last_unit_price: string
  last_currency: string
  total_received_quantity: string
  total_received_value_uzs: string
  total_procurements_count: number
}

export interface PayablePaymentPayload {
  allocations: Array<{
    cash_account_id: number
    amount: string | number
    currency: string
  }>
  payment_date?: string | null
  schedule_entry_id?: number | null
  notes?: string
  client_request_id?: string
}

interface FetchSuppliersParams {
  active?: boolean
  has_debt?: boolean
  search?: string
  page?: number
}

export async function fetchSuppliers(
  params?: FetchSuppliersParams,
  signal?: AbortSignal,
): Promise<PaginatedResponse<Supplier>> {
  const { data } = await api.get<PaginatedResponse<Supplier> | Supplier[]>('/api/v1/suppliers/suppliers/', { params, signal })
  return toPaginated<Supplier>(data)
}

export async function fetchSupplier(id: number): Promise<Supplier> {
  const { data } = await api.get<Supplier>(`/api/v1/suppliers/suppliers/${id}/`)
  return data
}

export async function fetchSupplierProducts(id: number): Promise<SupplierProductHistoryItem[]> {
  const { data } = await api.get<SupplierProductHistoryItem[]>(
    `/api/v1/suppliers/suppliers/${id}/products/`,
  )
  return data
}

export async function createSupplier(payload: SupplierCreatePayload): Promise<Supplier> {
  const { data } = await api.post<Supplier>('/api/v1/suppliers/suppliers/', payload)
  return data
}

export async function recordSupplierPayment(
  supplierId: number,
  payload: SupplierPaymentPayload,
): Promise<SupplierPayment> {
  const { data } = await api.post<SupplierPayment>(
    `/api/v1/suppliers/suppliers/${supplierId}/pay/`,
    payload,
  )
  return data
}

export async function fetchPayablesSummary(): Promise<PayablesSummaryItem[]> {
  const { data } = await api.get<PayablesSummaryItem[]>('/api/v1/suppliers/suppliers/payables-summary/')
  return data
}

export async function fetchSupplierPayables(params?: {
  status?: string
  supplier?: number
  burning_in?: number
  overdue?: boolean
}, signal?: AbortSignal): Promise<PaginatedResponse<SupplierPayable>> {
  const { data } = await api.get<PaginatedResponse<SupplierPayable> | SupplierPayable[]>(
    '/api/v1/suppliers/payables/',
    { params, signal },
  )
  return toPaginated<SupplierPayable>(data)
}

export async function paySupplierPayable(
  id: number,
  payload: PayablePaymentPayload,
): Promise<SupplierPayment> {
  const { data } = await api.post<SupplierPayment>(`/api/v1/suppliers/payables/${id}/pay/`, payload)
  return data
}
