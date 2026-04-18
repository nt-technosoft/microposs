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

export interface ExpenseItem {
  id: number
  title: string
  category: string
  payment_method: 'cash' | 'bank'
  source_account_code: string
  operation_currency: string
  operation_amount: string
  fx_rate_snapshot: string | null
  functional_amount_uzs: string
  occurred_at: string
  notes: string
  created_at: string
}

export interface ExpenseCreatePayload {
  title: string
  category?: string
  payment_method: 'cash' | 'bank'
  operation_currency?: string
  operation_amount: string | number
  fx_rate_snapshot?: string | number | null
  functional_amount_uzs?: string | number | null
  occurred_at: string
  source_account_code?: string
  notes?: string
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

export interface ExchangeRateItem {
  id: number
  base_currency: string
  quote_currency: string
  rate_date: string
  rate: string
  source: 'CBU' | 'MANUAL'
  is_manual: boolean
  fetched_at: string
  notes: string
  created_at: string
  updated_at: string
}

export interface ExchangeRateManualPayload {
  base_currency: string
  quote_currency: string
  rate_date: string
  rate: string | number
  notes?: string
}

export interface ExchangeRateRefreshPayload {
  base_currency?: string
  quote_currency?: string
  rate_date?: string
  overwrite_manual?: boolean
}

interface BackendDailySummary {
  date: string
  total_revenue: string
  total_cogs: string
  gross_profit: string
  total_sales_count: number
  total_returns_count: number
}

interface BackendCashFlowItem {
  date: string
  cash_in_sales: string
  cash_in_debt_payments: string
  cash_in_investor: string
  cash_out_purchases: string
  cash_out_supplier_payments: string
  cash_out_expenses?: string
  cash_out_investor_payments: string
  net_cash_flow: string
}

interface PaginatedMaybe<T> {
  results: T[]
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

function extractList<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) {
    return payload as T[]
  }
  if (
    payload
    && typeof payload === 'object'
    && Array.isArray((payload as PaginatedMaybe<T>).results)
  ) {
    return (payload as PaginatedMaybe<T>).results
  }
  return []
}

function toMoneyString(value: number): string {
  return value.toFixed(2)
}

function toNumber(raw: string | number | null | undefined): number {
  if (typeof raw === 'number') return raw
  if (typeof raw === 'string') return Number.parseFloat(raw) || 0
  return 0
}

export async function fetchAccounts(): Promise<Account[]> {
  const { data } = await api.get<PaginatedResponse<Account> | Account[]>('/api/v1/finance/accounts/')
  return extractList<Account>(data)
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
  const { data } = await api.get<PaginatedResponse<BackendDailySummary> | BackendDailySummary[]>(
    '/api/v1/finance/daily-summaries/',
    { params },
  )
  return extractList<BackendDailySummary>(data).map((item) => ({
    date: item.date,
    total_sales: String(item.total_sales_count),
    total_cogs: item.total_cogs,
    gross_profit: item.gross_profit,
    total_returns: String(item.total_returns_count),
    net_sales: item.total_revenue,
    cash_collected: item.total_revenue,
  }))
}

export async function fetchCashFlow(params?: FetchCashFlowParams): Promise<CashFlowItem[]> {
  const { data } = await api.get<PaginatedResponse<BackendCashFlowItem> | BackendCashFlowItem[]>(
    '/api/v1/finance/cash-flow/',
    { params },
  )
  return extractList<BackendCashFlowItem>(data).map((item) => {
    const inflows = (
      toNumber(item.cash_in_sales)
      + toNumber(item.cash_in_debt_payments)
      + toNumber(item.cash_in_investor)
    )
    const outflows = (
      toNumber(item.cash_out_purchases)
      + toNumber(item.cash_out_supplier_payments)
      + toNumber(item.cash_out_expenses)
      + toNumber(item.cash_out_investor_payments)
    )

    return {
      date: item.date,
      inflows: toMoneyString(inflows),
      outflows: toMoneyString(outflows),
      net: item.net_cash_flow,
    }
  })
}

export async function fetchTrialBalance(): Promise<TrialBalanceEntry[]> {
  const { data } = await api.get<TrialBalanceEntry[]>('/api/v1/finance/accounts/trial-balance/')
  return data
}

export async function fetchExpenses(params?: { date_from?: string; date_to?: string }): Promise<ExpenseItem[]> {
  const { data } = await api.get<PaginatedResponse<ExpenseItem> | ExpenseItem[]>(
    '/api/v1/finance/expenses/',
    { params },
  )
  return extractList<ExpenseItem>(data)
}

export async function createExpense(payload: ExpenseCreatePayload): Promise<ExpenseItem> {
  const { data } = await api.post<ExpenseItem>('/api/v1/finance/expenses/', payload)
  return data
}

export async function fetchLatestFxRate(params?: {
  base_currency?: string
  quote_currency?: string
  on_date?: string
}): Promise<ExchangeRateItem> {
  const { data } = await api.get<ExchangeRateItem>('/api/v1/finance/fx-rates/latest/', { params })
  return data
}

export async function createManualFxRate(payload: ExchangeRateManualPayload): Promise<ExchangeRateItem> {
  const { data } = await api.post<ExchangeRateItem>('/api/v1/finance/fx-rates/manual/', payload)
  return data
}

export async function refreshOfficialFxRate(payload: ExchangeRateRefreshPayload): Promise<{
  created: boolean
  rate: ExchangeRateItem
}> {
  const { data } = await api.post<{ created: boolean; rate: ExchangeRateItem }>(
    '/api/v1/finance/fx-rates/refresh-official/',
    payload,
  )
  return data
}
