/**
 * API client for suppliers domain.
 */

import api from './client'
import type { Supplier } from '../types/models'
import type { PaginatedResponse } from './catalog'

export interface SupplierCreatePayload {
  name: string
  phone?: string
  email?: string
  notes?: string
}

export interface SupplierPaymentPayload {
  amount: number
  payment_method: 'cash' | 'bank'
  notes?: string
}

export interface SupplierPayment {
  id: number
  supplier_id: number
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

interface FetchSuppliersParams {
  active?: boolean
  has_debt?: boolean
  search?: string
  page?: number
}

export async function fetchSuppliers(params?: FetchSuppliersParams): Promise<PaginatedResponse<Supplier>> {
  const { data } = await api.get<PaginatedResponse<Supplier>>('/api/v1/suppliers/suppliers/', { params })
  return data
}

export async function fetchSupplier(id: number): Promise<Supplier> {
  const { data } = await api.get<Supplier>(`/api/v1/suppliers/suppliers/${id}/`)
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
