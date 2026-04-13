/**
 * API client for analytics domain.
 */

import api from './client'

export interface ProductPerformanceItem {
  product_variant_id: number
  product_name: string
  variant_sku: string
  units_sold: number
  revenue: string
  cogs: string
  gross_profit: string
  profit_margin: string
}

export interface AgingReportItem {
  customer_id: number
  customer_name: string
  current: string
  days_1_30: string
  days_31_60: string
  days_61_90: string
  over_90: string
  total_outstanding: string
}

interface FetchProductPerformanceParams {
  date_from?: string
  date_to?: string
  location?: number
  category?: number
  page?: number
}

interface FetchAgingReportsParams {
  as_of_date?: string
  customer?: number
}

export async function fetchProductPerformance(
  params?: FetchProductPerformanceParams,
): Promise<ProductPerformanceItem[]> {
  const { data } = await api.get<ProductPerformanceItem[]>(
    '/api/v1/analytics/product-performance/',
    { params },
  )
  return data
}

export async function fetchAgingReports(params?: FetchAgingReportsParams): Promise<AgingReportItem[]> {
  const { data } = await api.get<AgingReportItem[]>('/api/v1/analytics/aging-reports/', { params })
  return data
}
