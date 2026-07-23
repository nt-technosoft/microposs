/**
 * API client for finance domain.
 */

import api from './client'
import type { PaginatedResponse } from './catalog'
import type { DebtSummaryItem } from './customers'
import type { PayablesSummaryItem } from './suppliers'
import type { StockSummaryItem } from './inventory'

export interface Account {
  id: number
  code: string
  name: string
  account_type: string
  balance: string
  created_at: string
  updated_at: string
}

export interface CashAccountRecord {
  id: number
  name: string
  currency: string
  balance: string
  kind: string
  linked_account: number | null
  is_active: boolean
  agreement_id?: number | null
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
  total_returns_count: number
  total_writeoffs: string
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
  fx_rate_source?: string
  fx_rate_date?: string | null
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

export interface SaleProfitabilityRow {
  sale_id: number
  date: string
  location_id: number
  location_name: string
  customer_id: number | null
  customer_name: string | null
  payment_methods: string[]
  line_count: number
  quantity_sold: number
  revenue: string
  cogs: string
  gross_profit: string
  investor_profit: string
  business_profit: string
  margin_percent: string
  markup_percent: string
  display?: ReportDisplay
}

export interface ProductProfitabilityRow {
  product_variant_id: number
  product_name: string
  current_unit_price: string
  quantity_sold: number
  revenue: string
  cogs: string
  gross_profit: string
  investor_profit: string
  business_profit: string
  margin_percent: string
  markup_percent: string
  remaining_quantity: number
  remaining_landed_cost: string
  projected_revenue: string
  projected_gross_profit: string
  projected_investor_profit: string
  projected_business_profit: string
  display?: ReportDisplay
}

export interface ReportCurrencyMeta {
  currency: string
  fx_rate: string
  rate_date: string
  source: string
  policy: string
}

export interface ReportDisplay extends ReportCurrencyMeta {
  amounts: Record<string, string>
}

export interface ProcurementProfitabilityRow {
  procurement_id: number
  funding_source: string
  status: string
  opened_at: string
  received_at: string | null
  supplier_name: string | null
  item_count: number
  quantity_sold: number
  remaining_quantity: number
  revenue: string
  cogs: string
  gross_profit: string
  investor_profit: string
  business_profit: string
  margin_percent: string
  markup_percent: string
  remaining_landed_cost: string
  projected_revenue: string
  projected_gross_profit: string
  projected_investor_profit: string
  projected_business_profit: string
  display?: ReportDisplay
  received_landed_cost?: string
  pending_prepaid_cost?: string
  receive_batches_count?: number
  receive_batches?: Array<{
    id: number
    received_at: string
    items_count: number
    total_inventory_uzs: string
    display?: ReportDisplay
    capital_allocations: Array<{
      partner_id: number
      partner_name: string
      role: string
      amount_contract_currency: string
      capital_share: string
      profit_share: string
    }>
  }>
  pending_paid_items_count?: number
  draft_items_count?: number
  venture_deployed_uzs?: string
  venture_capital_recovered_uzs?: string
  venture_capital_rolled_to_pool_uzs?: string
  venture_capital_return_available_uzs?: string
  venture_provisional_profit_available_uzs?: string
  venture_loss_uzs?: string
  venture_negative_position_uzs?: string
}

export interface ProcurementProfitabilityDetailItem {
  procurement_item_id: number
  product_variant_id: number
  product_name: string
  current_unit_price: string
  purchased_quantity: number
  sold_quantity: number
  remaining_quantity: number
  unit_purchase_price: string
  landed_cost_per_unit: string
  revenue: string
  cogs: string
  gross_profit: string
  investor_profit: string
  business_profit: string
  margin_percent: string
  markup_percent: string
  remaining_landed_cost: string
  projected_revenue: string
  projected_gross_profit: string
  projected_investor_profit: string
  projected_business_profit: string
  display?: ReportDisplay
}

export interface ProcurementProfitabilityDetail {
  report_currency?: ReportCurrencyMeta
  procurement: ProcurementProfitabilityRow
  items: ProcurementProfitabilityDetailItem[]
}

export interface AgreementProfitabilityDetail {
  report_currency?: ReportCurrencyMeta
  agreement: {
    agreement_id: number
    status: string
    opened_at: string
    closed_at: string | null
    supplier_name: string | null
    planned_budget: string
    currency: string
    balances: Record<string, string>
    procurements_count: number
    quantity_sold: number
    remaining_quantity: number
    revenue: string
    cogs: string
    gross_profit: string
    investor_profit: string
    business_profit: string
    received_landed_cost: string
    pending_prepaid_cost: string
    remaining_landed_cost: string
    projected_revenue: string
    projected_gross_profit: string
    projected_investor_profit: string
    projected_business_profit: string
    display?: ReportDisplay
  }
  partners: Array<{
    partner_id: number
    partner_name: string
    role: string
    agreement_currency: string
    planned_capital_share: string
    planned_profit_share: string
    agreement_contributed: string
    agreement_withdrawn: string
    agreement_allocated: string
    agreement_returned: string
    agreement_available: string
    allocated_functional_uzs: string
    returned_functional_uzs: string
    pending_prepaid_cost_estimate_uzs: string
    capital_in: string
    capital_out: string
    profit_accrued: string
    profit_reversed: string
    losses_incurred: string
    dividends_paid: string
    profit_pending_payout: string
    venture_capital_recovered_uzs?: string
    venture_capital_rolled_to_pool_uzs?: string
    venture_capital_return_available_uzs?: string
    venture_provisional_profit_uzs?: string
    venture_provisional_profit_available_uzs?: string
    venture_loss_uzs?: string
    venture_negative_position_uzs?: string
    display?: ReportDisplay
  }>
  procurements: ProcurementProfitabilityRow[]
  current_partner_id?: number
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

export interface CurrencyExchangeItem {
  id: number
  from_account: number
  from_account_name: string
  to_account: number
  to_account_name: string
  from_amount: string
  from_currency: string
  to_amount: string
  to_currency: string
  effective_rate: string
  date: string
  notes: string
}

export interface CurrencyExchangeCreatePayload {
  from_account_id: number
  to_account_id: number
  from_amount: string | number
  rate: string | number
  notes?: string
}

export interface OwnerContributionCreatePayload {
  amount: string | number
  currency?: string
  to_account_id: number
  notes?: string
}

export interface OwnerDrawingCreatePayload {
  amount: string | number
  currency?: string
  from_account_id: number
  notes?: string
  client_request_id?: string
}

export interface CashTransferCreatePayload {
  from_account_id: number
  to_account_id: number
  amount: string | number
  notes?: string
  client_request_id?: string
}

interface BackendDailySummary {
  date: string
  total_revenue: string
  total_cogs: string
  gross_profit: string
  total_sales_count: number
  total_returns_count: number
  total_return_amount?: string
  total_writeoffs?: string
}

interface BackendCashFlowItem {
  date: string
  cash_in_sales: string
  cash_in_debt_payments: string
  cash_in_investor: string
  cash_out_purchases: string
  cash_out_supplier_payments: string
  cash_out_expenses?: string
  cash_out_refunds?: string
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

interface FetchProfitabilityParams {
  date_from?: string
  date_to?: string
  location?: number
  warehouse?: number
  report_currency?: string
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

function mapDailySummary(item: BackendDailySummary): DailySummary {
  return {
    date: item.date,
    total_sales: String(item.total_sales_count),
    total_cogs: item.total_cogs,
    gross_profit: item.gross_profit,
    total_returns: item.total_return_amount ?? '0',
    total_returns_count: item.total_returns_count,
    total_writeoffs: item.total_writeoffs ?? '0',
    net_sales: item.total_revenue,
    cash_collected: item.total_revenue,
  }
}

function mapCashFlowItem(item: BackendCashFlowItem): CashFlowItem {
  const inflows = (
    toNumber(item.cash_in_sales)
    + toNumber(item.cash_in_debt_payments)
    + toNumber(item.cash_in_investor)
  )
  const outflows = (
    toNumber(item.cash_out_purchases)
    + toNumber(item.cash_out_supplier_payments)
    + toNumber(item.cash_out_expenses)
    + toNumber(item.cash_out_refunds)
    + toNumber(item.cash_out_investor_payments)
  )

  return {
    date: item.date,
    inflows: toMoneyString(inflows),
    outflows: toMoneyString(outflows),
    net: item.net_cash_flow,
  }
}

export async function fetchAccounts(): Promise<Account[]> {
  const { data } = await api.get<PaginatedResponse<Account> | Account[]>('/api/v1/finance/accounts/')
  return extractList<Account>(data)
}

export async function fetchCashAccounts(signal?: AbortSignal): Promise<CashAccountRecord[]> {
  const { data } = await api.get<PaginatedResponse<CashAccountRecord> | CashAccountRecord[]>(
    '/api/v1/finance/cash-accounts/',
    { signal },
  )
  return extractList<CashAccountRecord>(data)
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
  return extractList<BackendDailySummary>(data).map(mapDailySummary)
}

export async function fetchCashFlow(params?: FetchCashFlowParams): Promise<CashFlowItem[]> {
  const { data } = await api.get<PaginatedResponse<BackendCashFlowItem> | BackendCashFlowItem[]>(
    '/api/v1/finance/cash-flow/',
    { params },
  )
  return extractList<BackendCashFlowItem>(data).map(mapCashFlowItem)
}

export async function fetchTrialBalance(): Promise<TrialBalanceEntry[]> {
  const { data } = await api.get<TrialBalanceEntry[]>('/api/v1/finance/accounts/trial-balance/')
  return data
}

export async function fetchSalesProfitability(
  params?: FetchProfitabilityParams,
  signal?: AbortSignal,
): Promise<SaleProfitabilityRow[]> {
  const { data } = await api.get<SaleProfitabilityRow[]>(
    '/api/v1/finance/sales-profitability/',
    { params, signal },
  )
  return data
}

export async function fetchProductProfitability(
  params?: FetchProfitabilityParams,
  signal?: AbortSignal,
): Promise<ProductProfitabilityRow[]> {
  const { data } = await api.get<ProductProfitabilityRow[]>(
    '/api/v1/finance/product-profitability/',
    { params, signal },
  )
  return data
}

export async function fetchProcurementProfitability(
  params?: FetchProfitabilityParams,
  signal?: AbortSignal,
): Promise<ProcurementProfitabilityRow[]> {
  const { data } = await api.get<ProcurementProfitabilityRow[]>(
    '/api/v1/finance/procurement-profitability/',
    { params, signal },
  )
  return data
}

export async function fetchProcurementProfitabilityDetail(
  procurementId: number,
  params?: { report_currency?: string },
  signal?: AbortSignal,
): Promise<ProcurementProfitabilityDetail> {
  const { data } = await api.get<ProcurementProfitabilityDetail>(
    `/api/v1/finance/procurement-profitability/${procurementId}/`,
    { params, signal },
  )
  return data
}

export async function fetchAgreementProfitabilityDetail(
  agreementId: number,
  params?: { report_currency?: string },
  signal?: AbortSignal,
): Promise<AgreementProfitabilityDetail> {
  const { data } = await api.get<AgreementProfitabilityDetail>(
    `/api/v1/finance/agreement-profitability/${agreementId}/`,
    { params, signal },
  )
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

export async function createCurrencyExchange(
  payload: CurrencyExchangeCreatePayload,
): Promise<CurrencyExchangeItem> {
  const { data } = await api.post<CurrencyExchangeItem>('/api/v1/finance/currency-exchanges/', payload)
  return data
}

export interface ReportSummaryResponse {
  is_computing: boolean
  report_currency?: ReportCurrencyMeta
  daily_summary: DailySummary[]
  cash_flow: CashFlowItem[]
  debt: DebtSummaryItem[]
  parity: {
    payables: PayablesSummaryItem[]
    stock: StockSummaryItem[]
    trial_balance: TrialBalanceEntry[]
    cash_accounts: CashAccountRecord[]
  }
}

interface BackendReportSummaryResponse {
  is_computing: boolean
  report_currency?: ReportCurrencyMeta
  daily_summary: BackendDailySummary[]
  cash_flow: BackendCashFlowItem[]
  debt: DebtSummaryItem[]
  parity: {
    payables: PayablesSummaryItem[]
    stock: StockSummaryItem[]
    trial_balance: TrialBalanceEntry[]
    cash_accounts: CashAccountRecord[]
  }
}

export interface ReportAnalyticsResponse {
  sales: SaleProfitabilityRow[]
  products: ProductProfitabilityRow[]
  procurements: ProcurementProfitabilityRow[]
}

export interface FetchReportSummaryParams {
  date_from?: string
  date_to?: string
  report_currency?: string
}

export interface FetchReportAnalyticsParams {
  date_from?: string
  date_to?: string
  location?: string
  report_currency?: string
}

export async function fetchReportSummary(
  params?: FetchReportSummaryParams,
  signal?: AbortSignal,
): Promise<ReportSummaryResponse> {
  const { data } = await api.get<BackendReportSummaryResponse>('/api/v1/finance/reports/summary/', { params, signal })
  return {
    ...data,
    daily_summary: data.daily_summary.map(mapDailySummary),
    cash_flow: data.cash_flow.map(mapCashFlowItem),
  }
}

export async function fetchReportAnalytics(
  params?: FetchReportAnalyticsParams,
  signal?: AbortSignal,
): Promise<ReportAnalyticsResponse> {
  const { data } = await api.get<ReportAnalyticsResponse>('/api/v1/finance/reports/analytics/', { params, signal })
  return data
}

export async function createOwnerContribution(
  payload: OwnerContributionCreatePayload,
): Promise<{
  id: number
  amount: string
  currency: string
  to_account: number
  date: string
  notes: string
}> {
  const { data } = await api.post('/api/v1/finance/owner-contributions/', payload)
  return data
}

export async function createOwnerDrawing(
  payload: OwnerDrawingCreatePayload,
): Promise<{
  id: number
  amount: string
  currency: string
  from_account: number
  date: string
  notes: string
}> {
  const { data } = await api.post('/api/v1/finance/owner-drawings/', payload)
  return data
}

export async function createCashTransfer(
  payload: CashTransferCreatePayload,
): Promise<{
  id: number
  from_account: number
  to_account: number
  amount: string
  currency: string
  date: string
  notes: string
}> {
  const { data } = await api.post('/api/v1/finance/cash-transfers/', payload)
  return data
}
