/**
 * API client for risk domain.
 */

import api from './client'
import type { RiskEvent } from '../types/models'
import type { PaginatedResponse } from './catalog'

export interface WriteoffPayload {
  lot_id: number
  quantity: number
  reason: string
  negligence?: boolean
  affects_investor?: boolean
}

export interface InventoryCheck {
  id: number
  location_id: number
  location_name: string
  status: 'pending' | 'in_progress' | 'completed'
  initiated_by: string
  initiated_at: string
  completed_at: string | null
  notes: string
  created_at: string
  updated_at: string
}

export interface InventoryCheckCreatePayload {
  location_id: number
  notes?: string
}

export interface InventoryCheckCompletePayload {
  lines: Array<{
    product_variant_id: number
    counted_quantity: number
  }>
  notes?: string
}

interface FetchRiskEventsParams {
  event_type?: string
  lot?: number
  date_from?: string
  date_to?: string
  page?: number
}

interface FetchInventoryChecksParams {
  location?: number
  status?: 'pending' | 'in_progress' | 'completed'
  page?: number
}

export async function fetchRiskEvents(params?: FetchRiskEventsParams): Promise<PaginatedResponse<RiskEvent>> {
  const { data } = await api.get<PaginatedResponse<RiskEvent>>('/api/v1/risk/events/', { params })
  return data
}

export async function createWriteoff(payload: WriteoffPayload): Promise<RiskEvent> {
  const { data } = await api.post<RiskEvent>('/api/v1/risk/writeoffs/', payload)
  return data
}

export async function fetchInventoryChecks(
  params?: FetchInventoryChecksParams,
): Promise<PaginatedResponse<InventoryCheck>> {
  const { data } = await api.get<PaginatedResponse<InventoryCheck>>(
    '/api/v1/risk/inventory-checks/',
    { params },
  )
  return data
}

export async function createInventoryCheck(payload: InventoryCheckCreatePayload): Promise<InventoryCheck> {
  const { data } = await api.post<InventoryCheck>('/api/v1/risk/inventory-checks/', payload)
  return data
}

export async function completeInventoryCheck(
  checkId: number,
  payload: InventoryCheckCompletePayload,
): Promise<InventoryCheck> {
  const { data } = await api.post<InventoryCheck>(
    `/api/v1/risk/inventory-checks/${checkId}/complete/`,
    payload,
  )
  return data
}
