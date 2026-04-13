/**
 * API client for investors domain.
 */

import api from './client'
import type { InvestorContract, InvestorSummary } from '../types/models'
import type { PaginatedResponse } from './catalog'

export interface Investor {
  id: number
  name: string
  phone: string
  created_at: string
  updated_at: string
}

export interface ProfitRecord {
  id: number
  contract_id: number
  period_start: string
  period_end: string
  gross_revenue: string
  total_cogs: string
  gross_profit: string
  investor_share: string
  business_share: string
  created_at: string
}

export interface ContractSummary {
  contract_id: number
  investor_id: number
  investor_name: string
  summary: InvestorSummary
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
  const { data } = await api.get<PaginatedResponse<Investor>>('/api/v1/investors/investors/', { params })
  return data
}

export async function fetchContracts(params?: FetchContractsParams): Promise<PaginatedResponse<InvestorContract>> {
  const { data } = await api.get<PaginatedResponse<InvestorContract>>('/api/v1/investors/contracts/', { params })
  return data
}

export async function fetchSummaries(params?: { investor?: number }): Promise<ContractSummary[]> {
  const { data } = await api.get<ContractSummary[]>('/api/v1/investors/summaries/', { params })
  return data
}

export async function fetchProfitRecords(params?: FetchProfitRecordsParams): Promise<PaginatedResponse<ProfitRecord>> {
  const { data } = await api.get<PaginatedResponse<ProfitRecord>>('/api/v1/investors/profit-records/', { params })
  return data
}

export async function closeContract(contractId: number): Promise<InvestorContract> {
  const { data } = await api.post<InvestorContract>(`/api/v1/investors/contracts/${contractId}/close/`)
  return data
}

export async function refreshSummary(contractId: number): Promise<ContractSummary> {
  const { data } = await api.post<ContractSummary>(`/api/v1/investors/contracts/${contractId}/refresh-summary/`)
  return data
}
