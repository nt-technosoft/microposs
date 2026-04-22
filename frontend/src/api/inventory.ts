/**
 * API client for inventory domain.
 */

import api from './client'
import type { Location, Lot, Warehouse } from '../types/models'
import { toList, toPaginated, type PaginatedResponse } from './catalog'

export interface StockSummaryItem {
  product_variant_id: number
  product_name: string
  warehouse_id: number
  warehouse_name: string
  total_quantity: number
}

interface FetchLotsParams {
  product_variant?: number
  warehouse?: number
  active?: boolean
  page?: number
}

export async function fetchLocations(): Promise<Location[]> {
  const { data } = await api.get<PaginatedResponse<Warehouse> | Warehouse[]>('/api/v1/inventory/locations/')
  return toList<Warehouse>(data).map((warehouse) => ({
    ...warehouse,
    location_type: warehouse.location_type ?? (warehouse.kind === 'storage' ? 'warehouse' : 'store'),
  }))
}

export async function fetchLots(params?: FetchLotsParams): Promise<PaginatedResponse<Lot>> {
  const { data } = await api.get<PaginatedResponse<Lot> | Lot[]>('/api/v1/inventory/lots/', { params })
  return toPaginated<Lot>(data)
}

export async function fetchStockSummary(warehouseId?: number): Promise<StockSummaryItem[]> {
  const params = warehouseId !== undefined ? { warehouse: warehouseId } : undefined
  const { data } = await api.get<StockSummaryItem[]>('/api/v1/inventory/stock/summary/', { params })
  return data
}
