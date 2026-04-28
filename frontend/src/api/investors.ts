/**
 * API client for investors domain.
 */

import api from './client'
import type { AgreementProfitabilityDetail } from './finance'
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

export interface InvestorAgreementListItem {
  id: number
  status: string
  opened_at: string
  closed_at: string | null
  supplier_name: string | null
  planned_budget: string
  currency: string
  balances: Record<string, string>
  procurements_count: number
}

export async function fetchInvestorAgreements(): Promise<InvestorAgreementListItem[]> {
  const { data } = await api.get<InvestorAgreementListItem[]>('/api/v1/investors/agreements/')
  return toList<InvestorAgreementListItem>(data)
}

export async function fetchInvestorAgreementDetail(
  agreementId: number,
  params?: { report_currency?: string },
): Promise<AgreementProfitabilityDetail> {
  const { data } = await api.get<AgreementProfitabilityDetail>(
    `/api/v1/investors/agreements/${agreementId}/`,
    { params },
  )
  return data
}

export async function closeContract(contractId: number): Promise<InvestorContract> {
  const { data } = await api.post<InvestorContract>(`/api/v1/investors/contracts/${contractId}/close/`)
  return data
}
