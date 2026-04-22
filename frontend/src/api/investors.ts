/**
 * API client for investors domain.
 */

import api from './client'
import type {
  InvestorContract,
  InvestorDashboardAggregate,
  InvestorProcurementDetail,
  InvestorProcurementListItem,
} from '../types/models'
import { toList, toPaginated, type PaginatedResponse } from './catalog'

export interface Investor {
  id: number
  name: string
  phone: string
  created_at: string
  updated_at: string
}

interface FetchInvestorsParams {
  active?: boolean
  search?: string
  page?: number
}

interface FetchContractsParams {
  investor?: number
  status?: 'active' | 'closed'
  page?: number
}

interface FetchProfitRecordsParams {
  contract?: number
  page?: number
}

export async function fetchInvestors(params?: FetchInvestorsParams): Promise<PaginatedResponse<Investor>> {
  const { data } = await api.get<PaginatedResponse<Investor> | Investor[]>('/api/v1/investors/investors/', { params })
  return toPaginated<Investor>(data)
}

export async function fetchContracts(params?: FetchContractsParams): Promise<PaginatedResponse<InvestorContract>> {
  const { data } = await api.get<PaginatedResponse<InvestorContract> | InvestorContract[]>('/api/v1/investors/contracts/', { params })
  return toPaginated<InvestorContract>(data)
}

export async function fetchInvestorDashboard(): Promise<InvestorDashboardAggregate> {
  const { data } = await api.get<InvestorDashboardAggregate>('/api/v1/investors/dashboard/')
  return data
}

export async function fetchInvestorProcurements(): Promise<InvestorProcurementListItem[]> {
  const { data } = await api.get<PaginatedResponse<InvestorProcurementListItem> | InvestorProcurementListItem[]>('/api/v1/investors/procurements/')
  return toList<InvestorProcurementListItem>(data)
}

export async function fetchInvestorProcurementDetail(procurementId: number): Promise<InvestorProcurementDetail> {
  const { data } = await api.get<InvestorProcurementDetail>(`/api/v1/investors/procurements/${procurementId}/`)
  return data
}

export async function closeContract(contractId: number): Promise<InvestorContract> {
  const { data } = await api.post<InvestorContract>(`/api/v1/investors/contracts/${contractId}/close/`)
  return data
}
