/**
 * API client for inventory domain.
 */

import api from './client'
import type { Location, Lot, StockMovement, Warehouse } from '../types/models'
import { toList, toPaginated, type PaginatedResponse } from './catalog'

export interface StockSummaryItem {
  product_variant_id: number
  product_name: string
  warehouse_id: number
  warehouse_name: string
  total_quantity: number
  total_landed_cost: string
}

interface FetchLotsParams {
  product_variant?: number
  warehouse?: number
  active?: boolean
  page?: number
}

interface FetchStockMovementsParams {
  page?: number
  page_size?: number
  movement_type?: string
  reference_type?: string
  from_location?: number
  to_location?: number
  lot?: number
}

export interface TransferStockPayload {
  lot_id: number
  from_warehouse_id: number
  to_warehouse_id: number
  quantity: number
}

function normalizeWarehouseKind(rawKind: string | null | undefined): 'shop' | 'storage' {
  return String(rawKind ?? '').toUpperCase() === 'STORAGE' ? 'storage' : 'shop'
}

function normalizeWarehouse(warehouse: Warehouse): Location {
  const kind = normalizeWarehouseKind(warehouse.kind)
  return {
    ...warehouse,
    kind,
    location_type: warehouse.location_type ?? (kind === 'storage' ? 'warehouse' : 'store'),
  }
}

export async function fetchLocations(): Promise<Location[]> {
  const { data } = await api.get<PaginatedResponse<Warehouse> | Warehouse[]>('/api/v1/inventory/locations/')
  return toList<Warehouse>(data).map(normalizeWarehouse)
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

export async function transferStock(payload: TransferStockPayload): Promise<Lot> {
  const { data } = await api.post<Lot>('/api/v1/inventory/stock/transfer/', payload)
  return data
}

export async function fetchStockMovements(params?: FetchStockMovementsParams): Promise<PaginatedResponse<StockMovement>> {
  const { data } = await api.get<PaginatedResponse<StockMovement> | StockMovement[]>('/api/v1/inventory/movements/', { params })
  return toPaginated<StockMovement>(data)
}
