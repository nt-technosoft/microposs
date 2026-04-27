/**
 * API client for analytics domain.
 */

import api from './client'
import { toList, type PaginatedResponse } from './catalog'

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

export interface ReconciliationCheck {
  code: string
  title: string
  summary: string
  status: 'ok' | 'warning' | 'mismatch'
  actual_label: string
  expected_label: string
  actual_amount: string
  expected_amount: string
  delta_amount: string
  mismatch_count: number
  sample_refs: string[]
}

export interface ReconciliationHighlight {
  key: string
  label: string
  value: string
}

export interface ReconciliationSummary {
  generated_at: string
  overall_status: 'ok' | 'warning' | 'mismatch'
  totals: {
    total_checks: number
    ok_checks: number
    warning_checks: number
    mismatch_checks: number
    affected_records: number
  }
  highlights: ReconciliationHighlight[]
  checks: ReconciliationCheck[]
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
  const { data } = await api.get<PaginatedResponse<ProductPerformanceItem> | ProductPerformanceItem[]>(
    '/api/v1/analytics/product-performance/',
    { params },
  )
  return toList<ProductPerformanceItem>(data)
}

export async function fetchAgingReports(params?: FetchAgingReportsParams): Promise<AgingReportItem[]> {
  const { data } = await api.get<PaginatedResponse<AgingReportItem> | AgingReportItem[]>(
    '/api/v1/analytics/aging-reports/',
    { params },
  )
  return toList<AgingReportItem>(data)
}

export async function fetchLatestReconciliation(): Promise<ReconciliationSummary> {
  const { data } = await api.get<ReconciliationSummary>('/api/v1/core/excel/reconciliation/latest/')
  return data
}
