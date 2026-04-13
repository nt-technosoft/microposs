/**
 * API client for inventory domain.
 */

import api from './client'
import type { Location, Lot } from '../types/models'
import type { PaginatedResponse } from './catalog'

export interface StockSummaryItem {
  product_variant_id: number
  product_name: string
  location_id: number
  location_name: string
  total_quantity: number
  total_value: string
}

interface FetchLotsParams {
  product_variant?: number
  location?: number
  active?: boolean
  page?: number
}

export async function fetchLocations(): Promise<Location[]> {
  const { data } = await api.get<Location[]>('/api/v1/inventory/locations/')
  return data
}

export async function fetchLots(params?: FetchLotsParams): Promise<PaginatedResponse<Lot>> {
  const { data } = await api.get<PaginatedResponse<Lot>>('/api/v1/inventory/lots/', { params })
  return data
}

export async function fetchStockSummary(locationId?: number): Promise<StockSummaryItem[]> {
  const params = locationId !== undefined ? { location: locationId } : undefined
  const { data } = await api.get<StockSummaryItem[]>('/api/v1/inventory/stock/summary/', { params })
  return data
}
