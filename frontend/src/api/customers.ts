/**
 * API client for customers domain.
 */

import api from './client'
import type { Customer } from '../types/models'
import { toPaginated, type PaginatedResponse } from './catalog'

export interface CustomerCreatePayload {
  name: string
  phone?: string
  email?: string
  notes?: string
}

export interface CustomerPaymentPayload {
  amount: number
  payment_method: 'cash' | 'bank'
  currency?: string
  fx_rate?: string | number | null
  notes?: string
}

export interface CustomerPayment {
  id: number
  customer_id: number
  operation_currency?: string
  operation_amount?: string | null
  fx_rate_snapshot?: string | null
  fx_rate?: string
  fx_rate_source?: string
  fx_rate_date?: string | null
  functional_amount_uzs?: string | null
  amount: string
  payment_method: 'cash' | 'bank'
  notes: string
  created_at: string
}

export interface DebtSummaryItem {
  id: number
  name: string
  phone: string
  outstanding_balance: string
}

interface FetchCustomersParams {
  active?: boolean
  has_debt?: boolean
  search?: string
  page?: number
}

export async function fetchCustomers(params?: FetchCustomersParams): Promise<PaginatedResponse<Customer>> {
  const { data } = await api.get<PaginatedResponse<Customer> | Customer[]>('/api/v1/customers/customers/', { params })
  return toPaginated<Customer>(data)
}

export async function fetchCustomer(id: number): Promise<Customer> {
  const { data } = await api.get<Customer>(`/api/v1/customers/customers/${id}/`)
  return data
}

export async function createCustomer(payload: CustomerCreatePayload): Promise<Customer> {
  const { data } = await api.post<Customer>('/api/v1/customers/customers/', payload)
  return data
}

export async function recordPayment(
  customerId: number,
  payload: CustomerPaymentPayload,
): Promise<CustomerPayment> {
  const { data } = await api.post<CustomerPayment>(
    `/api/v1/customers/customers/${customerId}/pay/`,
    payload,
  )
  return data
}

export async function fetchDebtSummary(): Promise<DebtSummaryItem[]> {
  const { data } = await api.get<DebtSummaryItem[]>('/api/v1/customers/customers/debt-summary/')
  return data
}
