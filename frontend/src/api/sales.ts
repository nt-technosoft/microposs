/**
 * API client for sales domain.
 */

import api from './client'
import type { PosSession, Sale } from '../types/models'
import type { PaginatedResponse } from './catalog'

export interface SaleLineInput {
  product_variant_id: number
  quantity: number
  unit_price: number
  lot_id?: number
  discount_reason_id?: number
}

export interface SaleCreatePayload {
  client_request_id?: string
  pos_session_id: number
  payment_method: string
  customer_id?: number
  lines: SaleLineInput[]
  notes?: string
}

export interface OpenSessionPayload {
  location_id: number
  opening_cash: number
}

export interface CloseSessionPayload {
  actual_cash: number
}

export interface ReturnLinePayload {
  sale_line_id: number
  quantity: number
  condition: 'good' | 'damaged'
}

export interface ReturnCreatePayload {
  lines: ReturnLinePayload[]
  notes?: string
}

export interface SaleReturn {
  id: number
  original_sale_id: number
  created_at: string
  notes: string
  lines: ReturnLinePayload[]
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
  const { data } = await api.get<PaginatedResponse<PosSession>>('/api/v1/sales/sessions/', { params })
  return data
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
  const { data } = await api.get<PaginatedResponse<Sale>>('/api/v1/sales/sales/', { params })
  return data
}

export async function fetchSale(id: number): Promise<Sale> {
  const { data } = await api.get<Sale>(`/api/v1/sales/sales/${id}/`)
  return data
}

export async function createSale(payload: SaleCreatePayload): Promise<Sale> {
  const { data } = await api.post<Sale>('/api/v1/sales/sales/', payload)
  return data
}

export async function processReturn(saleId: number, payload: ReturnCreatePayload): Promise<SaleReturn> {
  const { data } = await api.post<SaleReturn>(`/api/v1/sales/sales/${saleId}/return/`, payload)
  return data
}
