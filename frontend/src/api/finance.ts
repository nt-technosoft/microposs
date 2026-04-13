/**
 * API client for finance domain.
 */

import api from './client'
import type { PaginatedResponse } from './catalog'

export interface Account {
  id: number
  code: string
  name: string
  account_type: string
  balance: string
  created_at: string
  updated_at: string
}

export interface JournalEntry {
  id: number
  reference: string
  description: string
  entry_date: string
  debit_account_id: number
  debit_account_name: string
  credit_account_id: number
  credit_account_name: string
  amount: string
  created_at: string
}

export interface DailySummary {
  date: string
  total_sales: string
  total_cogs: string
  gross_profit: string
  total_returns: string
  net_sales: string
  cash_collected: string
}

export interface CashFlowItem {
  date: string
  inflows: string
  outflows: string
  net: string
}

export interface TrialBalanceEntry {
  account_id: number
  account_code: string
  account_name: string
  account_type: string
  debit_total: string
  credit_total: string
  balance: string
}

interface FetchJournalEntriesParams {
  account?: number
  date_from?: string
  date_to?: string
  page?: number
}

interface FetchDailySummariesParams {
  date_from?: string
  date_to?: string
  location?: number
}

interface FetchCashFlowParams {
  date_from?: string
  date_to?: string
  location?: number
}

export async function fetchAccounts(): Promise<Account[]> {
  const { data } = await api.get<Account[]>('/api/v1/finance/accounts/')
  return data
}

export async function fetchJournalEntries(
  params?: FetchJournalEntriesParams,
): Promise<PaginatedResponse<JournalEntry>> {
  const { data } = await api.get<PaginatedResponse<JournalEntry>>(
    '/api/v1/finance/journal-entries/',
    { params },
  )
  return data
}

export async function fetchDailySummaries(params?: FetchDailySummariesParams): Promise<DailySummary[]> {
  const { data } = await api.get<DailySummary[]>('/api/v1/finance/daily-summaries/', { params })
  return data
}

export async function fetchCashFlow(params?: FetchCashFlowParams): Promise<CashFlowItem[]> {
  const { data } = await api.get<CashFlowItem[]>('/api/v1/finance/cash-flow/', { params })
  return data
}

export async function fetchTrialBalance(): Promise<TrialBalanceEntry[]> {
  const { data } = await api.get<TrialBalanceEntry[]>('/api/v1/finance/trial-balance/')
  return data
}
