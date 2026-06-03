<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { TrendingUp, TrendingDown, ShoppingCart, ArrowDownCircle, ArrowUpCircle, ChevronDown } from 'lucide-vue-next'
import {
  fetchReportSummary,
  fetchReportAnalytics,
  type DailySummary,
  type CashFlowItem,
  type CashAccountRecord,
  type SaleProfitabilityRow,
  type ProductProfitabilityRow,
  type ProcurementProfitabilityRow,
  type ReportCurrencyMeta,
} from '@/api/finance'
import type { DebtSummaryItem } from '@/api/customers'
import type { PayablesSummaryItem } from '@/api/suppliers'
import type { StockSummaryItem } from '@/api/inventory'
import { useToast } from '@/composables/useToast'
import { intlLocale } from '@/i18n/format'
import { formatPrice } from '@/utils/currency'
import {
  procurementStatusLabel as domainProcurementStatusLabel,
  procurementTypeLabel as domainProcurementTypeLabel,
} from '@/utils/domainLabels'

// ── Types ───────────────────────────────────────────────────────────────────

type Period = 'today' | 'week' | 'month' | 'all' | 'custom'
type AnalyticsView = 'sales' | 'products' | 'procurements'
type SalesSort = 'profit' | 'margin' | 'revenue'
type ProductSort = 'profit' | 'projected' | 'remaining'
type ProcurementSort = 'profit' | 'projected' | 'remaining'
type ReportCurrency = 'UZS' | 'USD'

interface PeriodOption {
  value: Period
  labelKey: string
}

// ── Composables ─────────────────────────────────────────────────────────────

const toast = useToast()
const router = useRouter()
const { t, locale } = useI18n()

// ── State ────────────────────────────────────────────────────────────────────

const period = ref<Period>('month')
const periodMenuOpen = ref(false)
const customDateFrom = ref('')
const customDateTo = ref('')

const summaries = ref<DailySummary[]>([])
const cashFlow = ref<CashFlowItem[]>([])
const debtItems = ref<DebtSummaryItem[]>([])
const payablesItems = ref<PayablesSummaryItem[]>([])
const stockItems = ref<StockSummaryItem[]>([])
const trialBalance = ref<Array<{ code: string; balance: string }>>([])
const cashAccounts = ref<CashAccountRecord[]>([])
const salesProfitability = ref<SaleProfitabilityRow[]>([])
const productProfitability = ref<ProductProfitabilityRow[]>([])
const procurementProfitability = ref<ProcurementProfitabilityRow[]>([])
const analyticsView = ref<AnalyticsView>('sales')
const salesSort = ref<SalesSort>('profit')
const productSort = ref<ProductSort>('profit')
const procurementSort = ref<ProcurementSort>('profit')
const salesExpanded = ref(false)
const productsExpanded = ref(false)
const procurementsExpanded = ref(false)
const debtExpanded = ref(false)
const salesSummaryExpanded = ref(false)
const productsSummaryExpanded = ref(false)
const procurementsSummaryExpanded = ref(false)
const expandedSaleId = ref<number | null>(null)
const expandedProductId = ref<number | null>(null)
const expandedProcurementId = ref<number | null>(null)
const reportCurrency = ref<ReportCurrency>('UZS')
const reportCurrencyMeta = ref<ReportCurrencyMeta | null>(null)

const loadingSummary = ref(false)
const loadingCashFlow = ref(false)
const loadingDebt = ref(false)
const loadingAnalytics = ref(false)
const errorSummary = ref<string | null>(null)
const errorCashFlow = ref<string | null>(null)
const loadingParity = ref(false)
const isComputing = ref(false)

// ── Constants ────────────────────────────────────────────────────────────────

const PERIOD_OPTIONS: PeriodOption[] = [
  { value: 'today', labelKey: 'reports.period.today' },
  { value: 'week', labelKey: 'reports.period.week' },
  { value: 'month', labelKey: 'reports.period.month' },
  { value: 'all', labelKey: 'reports.period.all' },
  { value: 'custom', labelKey: 'reports.period.custom' },
]
const ANALYTICS_PREVIEW_LIMIT = 5
const DEBT_PREVIEW_LIMIT = 3

// ── Date range helpers ───────────────────────────────────────────────────────

function toIsoDate(date: Date): string {
  return date.toISOString().split('T')[0]
}

function getDateRange(p: Period): { date_from?: string; date_to?: string } {
  const today = new Date()
  const to = toIsoDate(today)

  if (p === 'today') {
    return { date_from: to, date_to: to }
  }
  if (p === 'week') {
    const from = new Date(today)
    from.setDate(today.getDate() - 6)
    return { date_from: toIsoDate(from), date_to: to }
  }
  const from = new Date(today)
  if (p === 'month') {
    from.setDate(1)
    return { date_from: toIsoDate(from), date_to: to }
  }
  if (p === 'all') {
    return {}
  }

  const fromRaw = customDateFrom.value
  const toRaw = customDateTo.value
  if (!fromRaw && !toRaw) {
    return {}
  }
  if (fromRaw && toRaw && fromRaw > toRaw) {
    return { date_from: toRaw, date_to: fromRaw }
  }
  return {
    date_from: fromRaw || undefined,
    date_to: toRaw || undefined,
  }
}

// ── Aggregated metrics ───────────────────────────────────────────────────────

const metrics = computed(() => {
  const zero = { revenue: 0, profit: 0, cogs: 0, salesCount: 0, salesDays: 0, returns: 0, returnsCount: 0, writeoffs: 0 }

  return summaries.value.reduce((acc, s) => ({
    revenue: acc.revenue + parseFloat(s.net_sales),
    profit: acc.profit + parseFloat(s.gross_profit),
    cogs: acc.cogs + parseFloat(s.total_cogs),
    salesCount: acc.salesCount + Number(s.total_sales || 0),
    salesDays: acc.salesDays + (Number(s.total_sales || 0) > 0 ? 1 : 0),
    returns: acc.returns + parseFloat(s.total_returns),
    returnsCount: acc.returnsCount + Number(s.total_returns_count || 0),
    writeoffs: acc.writeoffs + parseFloat(s.total_writeoffs || '0'),
  }), zero)
})

const cashFlowTotals = computed(() => {
  let inflows = 0
  let outflows = 0
  let net = 0

  for (const item of cashFlow.value) {
    inflows += parseFloat(item.inflows)
    outflows += parseFloat(item.outflows)
    net += parseFloat(item.net)
  }

  return { inflows, outflows, net }
})

const totalDebt = computed(() =>
  debtItems.value.reduce((sum, d) => sum + parseFloat(d.outstanding_balance), 0),
)

const totalPayables = computed(() =>
  payablesItems.value.reduce((sum, p) => sum + parseFloat(p.outstanding_balance), 0),
)

const inventoryTotals = computed(() => {
  return stockItems.value.reduce((acc, item) => ({
    qty: acc.qty + Number(item.total_quantity || 0),
    value: acc.value + parseFloat(item.total_landed_cost || '0'),
  }), { qty: 0, value: 0 })
})

const cashBalance = computed(() => {
  return trialBalance.value
    .filter((line) => ['1000', '1010'].includes(line.code))
    .reduce((sum, line) => sum + parseFloat(line.balance || '0'), 0)
})

const operationalCashAccounts = computed(() =>
  cashAccounts.value.filter((account) => account.kind !== 'agreement_capital'),
)

const nativeCashByCurrency = computed(() => {
  const totals = new Map<string, number>()
  for (const account of operationalCashAccounts.value) {
    const currency = String(account.currency || 'UZS').toUpperCase()
    const amount = parseFloat(account.balance || '0') || 0
    totals.set(currency, (totals.get(currency) || 0) + amount)
  }
  return Array.from(totals.entries())
    .map(([currency, amount]) => ({ currency, amount }))
    .sort((left, right) => left.currency.localeCompare(right.currency))
})

const sortedDebtors = computed(() =>
  [...debtItems.value]
    .sort((a, b) => parseFloat(b.outstanding_balance) - parseFloat(a.outstanding_balance))
)
const visibleDebtors = computed(() =>
  debtExpanded.value ? sortedDebtors.value : sortedDebtors.value.slice(0, DEBT_PREVIEW_LIMIT),
)
const hasMoreDebtors = computed(() => sortedDebtors.value.length > DEBT_PREVIEW_LIMIT)
const hiddenDebtorsCount = computed(() =>
  Math.max(sortedDebtors.value.length - DEBT_PREVIEW_LIMIT, 0),
)

const selectedPeriodLabel = computed(
  () => {
    const option = PERIOD_OPTIONS.find((o) => o.value === period.value)
    return option ? t(option.labelKey) : ''
  },
)
const periodLabelLower = computed(() => selectedPeriodLabel.value.toLocaleLowerCase(intlLocale(locale.value)))
const overallMargin = computed(() => (
  metrics.value.revenue > 0
    ? (metrics.value.profit / metrics.value.revenue) * 100
    : 0
))

function reportNumberFromUzs(value: string | number | null | undefined): number {
  const raw = typeof value === 'number' ? value : Number.parseFloat(String(value ?? '0'))
  const amount = Number.isFinite(raw) ? raw : 0
  if (reportCurrency.value === 'UZS') return amount
  if (reportCurrencyMeta.value?.currency !== 'USD') return amount
  const fx = Number.parseFloat(reportCurrencyMeta.value?.fx_rate || '0')
  return Number.isFinite(fx) && fx > 0 ? amount / fx : amount
}

function rowReportNumber(
  row: { display?: { currency: string; amounts: Record<string, string> } },
  key: string,
  fallback: string | number | null | undefined,
): number {
  const displayValue = row.display?.currency === reportCurrency.value ? row.display.amounts[key] : undefined
  if (displayValue !== undefined) {
    const parsed = Number.parseFloat(displayValue)
    return Number.isFinite(parsed) ? parsed : 0
  }
  return reportNumberFromUzs(fallback)
}

function formatReportPrice(value: string | number | null | undefined): string {
  return formatPrice(reportNumberFromUzs(value), reportCurrency.value)
}

function reportFxSourceLabel(source: string | null | undefined): string {
  if (source === 'CBU') return 'ЦБ'
  if (source === 'MANUAL') return 'ручной'
  if (source === 'FUNCTIONAL') return 'UZS'
  return 'курс'
}

const reportCurrencyHint = computed(() => {
  if (reportCurrency.value === 'UZS') return 'Функциональная валюта учёта'
  const meta = reportCurrencyMeta.value
  if (meta?.currency !== 'USD' || !meta.fx_rate) return 'Курс для отображения не загружен'
  const date = meta.rate_date
    ? new Date(meta.rate_date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
    : ''
  const rate = Number(meta.fx_rate).toLocaleString(intlLocale(locale.value), { maximumFractionDigits: 2 })
  return `Отображение по курсу ${reportFxSourceLabel(meta.source)}: 1 USD = ${rate} UZS${date ? ` на ${date}` : ''}`
})

function formatRowReportPrice(
  row: { display?: { currency: string; amounts: Record<string, string> } },
  key: string,
  fallback: string | number | null | undefined,
): string {
  return formatPrice(rowReportNumber(row, key, fallback), reportCurrency.value)
}

let _currencyDebounceTimer: ReturnType<typeof setTimeout> | null = null

async function setReportCurrency(currency: ReportCurrency): Promise<void> {
  if (reportCurrency.value === currency) return
  reportCurrency.value = currency

  if (_currencyDebounceTimer !== null) clearTimeout(_currencyDebounceTimer)
  _currencyDebounceTimer = setTimeout(async () => {
    _currencyDebounceTimer = null
    try {
      await Promise.all([loadSummary(), loadAnalytics()])
      if (currency === 'USD' && reportCurrencyMeta.value?.currency !== 'USD') {
        reportCurrency.value = 'UZS'
        toast.error(errorSummary.value || t('procurements.syncUsdRateFirst'))
      }
    } catch {
      reportCurrency.value = 'UZS'
    }
  }, 300)
}

const salesProfitabilityTotals = computed(() => {
  return salesProfitability.value.reduce((acc, sale) => ({
    revenue: acc.revenue + rowReportNumber(sale, 'revenue', sale.revenue),
    cogs: acc.cogs + rowReportNumber(sale, 'cogs', sale.cogs),
    grossProfit: acc.grossProfit + rowReportNumber(sale, 'gross_profit', sale.gross_profit),
    investorProfit: acc.investorProfit + rowReportNumber(sale, 'investor_profit', sale.investor_profit),
    businessProfit: acc.businessProfit + rowReportNumber(sale, 'business_profit', sale.business_profit),
    quantitySold: acc.quantitySold + Number(sale.quantity_sold || 0),
    lineCount: acc.lineCount + Number(sale.line_count || 0),
  }), {
    revenue: 0,
    cogs: 0,
    grossProfit: 0,
    investorProfit: 0,
    businessProfit: 0,
    quantitySold: 0,
    lineCount: 0,
  })
})

const productProfitabilityTotals = computed(() => {
  return productProfitability.value.reduce((acc, product) => ({
    revenue: acc.revenue + rowReportNumber(product, 'revenue', product.revenue),
    grossProfit: acc.grossProfit + rowReportNumber(product, 'gross_profit', product.gross_profit),
    remainingLandedCost: acc.remainingLandedCost + rowReportNumber(product, 'remaining_landed_cost', product.remaining_landed_cost),
    projectedRevenue: acc.projectedRevenue + rowReportNumber(product, 'projected_revenue', product.projected_revenue),
    projectedGrossProfit: acc.projectedGrossProfit + rowReportNumber(product, 'projected_gross_profit', product.projected_gross_profit),
    projectedInvestorProfit: acc.projectedInvestorProfit + rowReportNumber(product, 'projected_investor_profit', product.projected_investor_profit),
    projectedBusinessProfit: acc.projectedBusinessProfit + rowReportNumber(product, 'projected_business_profit', product.projected_business_profit),
    remainingQuantity: acc.remainingQuantity + Number(product.remaining_quantity || 0),
  }), {
    revenue: 0,
    grossProfit: 0,
    remainingLandedCost: 0,
    projectedRevenue: 0,
    projectedGrossProfit: 0,
    projectedInvestorProfit: 0,
    projectedBusinessProfit: 0,
    remainingQuantity: 0,
  })
})

const procurementProfitabilityTotals = computed(() => {
  return procurementProfitability.value.reduce((acc, procurement) => ({
    revenue: acc.revenue + rowReportNumber(procurement, 'revenue', procurement.revenue),
    cogs: acc.cogs + rowReportNumber(procurement, 'cogs', procurement.cogs),
    grossProfit: acc.grossProfit + rowReportNumber(procurement, 'gross_profit', procurement.gross_profit),
    investorProfit: acc.investorProfit + rowReportNumber(procurement, 'investor_profit', procurement.investor_profit),
    businessProfit: acc.businessProfit + rowReportNumber(procurement, 'business_profit', procurement.business_profit),
    remainingLandedCost: acc.remainingLandedCost + rowReportNumber(procurement, 'remaining_landed_cost', procurement.remaining_landed_cost),
    projectedRevenue: acc.projectedRevenue + rowReportNumber(procurement, 'projected_revenue', procurement.projected_revenue),
    projectedGrossProfit: acc.projectedGrossProfit + rowReportNumber(procurement, 'projected_gross_profit', procurement.projected_gross_profit),
    projectedInvestorProfit: acc.projectedInvestorProfit + rowReportNumber(procurement, 'projected_investor_profit', procurement.projected_investor_profit),
    projectedBusinessProfit: acc.projectedBusinessProfit + rowReportNumber(procurement, 'projected_business_profit', procurement.projected_business_profit),
    quantitySold: acc.quantitySold + Number(procurement.quantity_sold || 0),
    remainingQuantity: acc.remainingQuantity + Number(procurement.remaining_quantity || 0),
  }), {
    revenue: 0,
    cogs: 0,
    grossProfit: 0,
    investorProfit: 0,
    businessProfit: 0,
    remainingLandedCost: 0,
    projectedRevenue: 0,
    projectedGrossProfit: 0,
    projectedInvestorProfit: 0,
    projectedBusinessProfit: 0,
    quantitySold: 0,
    remainingQuantity: 0,
  })
})

const salesProfitabilitySorted = computed(() => {
  return [...salesProfitability.value].sort((left, right) => {
    if (salesSort.value === 'margin') {
      return parseFloat(right.margin_percent || '0') - parseFloat(left.margin_percent || '0')
    }
    if (salesSort.value === 'revenue') {
      return rowReportNumber(right, 'revenue', right.revenue) - rowReportNumber(left, 'revenue', left.revenue)
    }
    return rowReportNumber(right, 'gross_profit', right.gross_profit) - rowReportNumber(left, 'gross_profit', left.gross_profit)
  })
})

const visibleSalesProfitability = computed(() =>
  salesExpanded.value
    ? salesProfitabilitySorted.value
    : salesProfitabilitySorted.value.slice(0, ANALYTICS_PREVIEW_LIMIT),
)

const productProfitabilitySorted = computed(() => {
  return [...productProfitability.value].sort((left, right) => {
    if (productSort.value === 'projected') {
      return rowReportNumber(right, 'projected_gross_profit', right.projected_gross_profit) - rowReportNumber(left, 'projected_gross_profit', left.projected_gross_profit)
    }
    if (productSort.value === 'remaining') {
      return rowReportNumber(right, 'remaining_landed_cost', right.remaining_landed_cost) - rowReportNumber(left, 'remaining_landed_cost', left.remaining_landed_cost)
    }
    return rowReportNumber(right, 'gross_profit', right.gross_profit) - rowReportNumber(left, 'gross_profit', left.gross_profit)
  })
})

const visibleProductProfitability = computed(() =>
  productsExpanded.value
    ? productProfitabilitySorted.value
    : productProfitabilitySorted.value.slice(0, ANALYTICS_PREVIEW_LIMIT),
)

const procurementProfitabilitySorted = computed(() => {
  return [...procurementProfitability.value].sort((left, right) => {
    if (procurementSort.value === 'projected') {
      return rowReportNumber(right, 'projected_gross_profit', right.projected_gross_profit) - rowReportNumber(left, 'projected_gross_profit', left.projected_gross_profit)
    }
    if (procurementSort.value === 'remaining') {
      return rowReportNumber(right, 'remaining_landed_cost', right.remaining_landed_cost) - rowReportNumber(left, 'remaining_landed_cost', left.remaining_landed_cost)
    }
    return rowReportNumber(right, 'gross_profit', right.gross_profit) - rowReportNumber(left, 'gross_profit', left.gross_profit)
  })
})

const visibleProcurementProfitability = computed(() =>
  procurementsExpanded.value
    ? procurementProfitabilitySorted.value
    : procurementProfitabilitySorted.value.slice(0, ANALYTICS_PREVIEW_LIMIT),
)

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString(intlLocale(locale.value), {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatPercent(value: string | number): string {
  const numeric = typeof value === 'number' ? value : parseFloat(value)
  if (!Number.isFinite(numeric)) return '0.00%'
  return `${numeric.toLocaleString(intlLocale(locale.value), { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
}

function setSalesSort(next: SalesSort): void {
  salesSort.value = next
  expandedSaleId.value = null
}

function setProductSort(next: ProductSort): void {
  productSort.value = next
  expandedProductId.value = null
}

function setProcurementSort(next: ProcurementSort): void {
  procurementSort.value = next
  expandedProcurementId.value = null
}

function setAnalyticsView(next: AnalyticsView): void {
  analyticsView.value = next
  expandedSaleId.value = null
  expandedProductId.value = null
  expandedProcurementId.value = null
}

function toggleDebtExpanded(): void {
  debtExpanded.value = !debtExpanded.value
}

function toggleSaleExpanded(id: number): void {
  expandedSaleId.value = expandedSaleId.value === id ? null : id
}

function toggleProductExpanded(id: number): void {
  expandedProductId.value = expandedProductId.value === id ? null : id
}

function toggleProcurementExpanded(id: number): void {
  expandedProcurementId.value = expandedProcurementId.value === id ? null : id
}

function paymentMethodsLabel(methods: string[]): string {
  if (!methods.length) return t('reports.noPaymentMethod')
  return methods.map((method) => t(`domain.paymentMethod.${method}`)).join(', ')
}

function procurementTypeLabel(type: string): string {
  return domainProcurementTypeLabel(type)
}

function procurementStatusLabel(status: string): string {
  return domainProcurementStatusLabel(status)
}

function procurementDateLabel(procurement: ProcurementProfitabilityRow): string {
  return formatDateTime(procurement.received_at || procurement.opened_at)
}

// ── Data loading ─────────────────────────────────────────────────────────────

let _summaryAbort: AbortController | null = null
let _analyticsAbort: AbortController | null = null
let _computingPollTimer: ReturnType<typeof setInterval> | null = null

function _applySummaryResult(result: Awaited<ReturnType<typeof fetchReportSummary>>): void {
  reportCurrencyMeta.value = result.report_currency ?? null
  const metaCurrency = result.report_currency?.currency
  if ((metaCurrency === 'UZS' || metaCurrency === 'USD') && reportCurrency.value !== metaCurrency) {
    reportCurrency.value = metaCurrency
  }
  summaries.value = result.daily_summary
  cashFlow.value = result.cash_flow
  debtItems.value = result.debt
  payablesItems.value = result.parity.payables
  stockItems.value = result.parity.stock
  trialBalance.value = result.parity.trial_balance.map((line) => ({
    code: String(line.account_code || (line as unknown as { code?: string }).code || ''),
    balance: String(line.balance ?? '0'),
  }))
  cashAccounts.value = result.parity.cash_accounts
}

async function loadSummary(): Promise<void> {
  _summaryAbort?.abort()
  _summaryAbort = new AbortController()
  if (_computingPollTimer !== null) {
    clearInterval(_computingPollTimer)
    _computingPollTimer = null
  }

  loadingSummary.value = true
  loadingCashFlow.value = true
  loadingDebt.value = true
  loadingParity.value = true
  errorSummary.value = null
  try {
    const range = getDateRange(period.value)
    const result = await fetchReportSummary(
      { ...range, report_currency: reportCurrency.value },
      _summaryAbort.signal,
    )

    _applySummaryResult(result)
    isComputing.value = result.is_computing

    if (result.is_computing) {
      let attempts = 0
      _computingPollTimer = setInterval(async () => {
        attempts++
        if (attempts > 12) {
          clearInterval(_computingPollTimer!)
          _computingPollTimer = null
          return
        }
        try {
          const poll = await fetchReportSummary({ ...range, report_currency: reportCurrency.value })
          if (!poll.is_computing) {
            clearInterval(_computingPollTimer!)
            _computingPollTimer = null
            _applySummaryResult(poll)
            isComputing.value = false
          }
        } catch {
          // ignore poll errors
        }
      }, 5000)
    }
  } catch (err: unknown) {
    if ((err as { name?: string })?.name === 'CanceledError') return
    errorSummary.value = err instanceof Error ? err.message : t('reports.loadFailed')
    toast.error(t('reports.loadFailed'))
  } finally {
    loadingSummary.value = false
    loadingCashFlow.value = false
    loadingDebt.value = false
    loadingParity.value = false
  }
}

async function loadAnalytics(): Promise<void> {
  _analyticsAbort?.abort()
  _analyticsAbort = new AbortController()
  const { signal } = _analyticsAbort

  loadingAnalytics.value = true
  try {
    const range = getDateRange(period.value)
    const params = { ...range, report_currency: reportCurrency.value }
    const result = await fetchReportAnalytics(params, signal)
    salesProfitability.value = result.sales
    productProfitability.value = result.products
    procurementProfitability.value = result.procurements
  } catch (err: unknown) {
    if ((err as { name?: string })?.name === 'CanceledError') return
    salesProfitability.value = []
    productProfitability.value = []
    procurementProfitability.value = []
  } finally {
    loadingAnalytics.value = false
  }
}

async function loadAll(): Promise<void> {
  await Promise.all([loadSummary(), loadAnalytics()])
}

async function onPeriodSelect(p: Period): Promise<void> {
  period.value = p
  periodMenuOpen.value = false
  if (p === 'custom') {
    if (!customDateFrom.value || !customDateTo.value) {
      const today = new Date()
      const firstDay = new Date(today.getFullYear(), today.getMonth(), 1)
      customDateFrom.value = toIsoDate(firstDay)
      customDateTo.value = toIsoDate(today)
    }
  }
  await Promise.all([loadSummary(), loadAnalytics()])
}

async function applyCustomRange(): Promise<void> {
  if (period.value !== 'custom') {
    return
  }
  await Promise.all([loadSummary(), loadAnalytics()])
}

onMounted(loadAll)
onBeforeUnmount(() => {
  _summaryAbort?.abort()
  _analyticsAbort?.abort()
  if (_computingPollTimer !== null) clearInterval(_computingPollTimer)
  if (_currencyDebounceTimer !== null) clearTimeout(_currencyDebounceTimer)
})

// ── Formatting ───────────────────────────────────────────────────────────────

function signClass(value: number): string {
  if (value > 0) return 'positive'
  if (value < 0) return 'negative'
  return ''
}

function openReconciliation(): void {
  router.push({ name: 'reports-reconciliation' })
}

function openCurrencyExchange(): void {
  router.push({ name: 'finance-exchange' })
}

function openSaleExplanation(saleId: number): void {
  router.push({ name: 'reports-sale-explanation', params: { id: saleId } })
}

function openProcurementAudit(procurementId: number): void {
  router.push({ name: 'reports-procurement-profitability', params: { id: procurementId } })
}
</script>

<template>
  <div class="reports-page">

    <!-- ── Header ─────────────────────────────────────────────── -->
    <header class="page-header">
      <h1 class="page-title">{{ t('reports.title') }}</h1>

      <div class="period-selector">
        <button
          class="period-btn"
          :class="{ open: periodMenuOpen }"
          aria-haspopup="listbox"
          :aria-expanded="periodMenuOpen"
          @click="periodMenuOpen = !periodMenuOpen"
        >
          {{ selectedPeriodLabel }}
          <ChevronDown :size="14" :stroke-width="2" class="period-chevron" />
        </button>

        <Transition name="dropdown">
          <ul v-if="periodMenuOpen" class="period-menu" role="listbox">
            <li
              v-for="opt in PERIOD_OPTIONS"
              :key="opt.value"
              class="period-option"
              :class="{ active: period === opt.value }"
              role="option"
              :aria-selected="period === opt.value"
              @click="onPeriodSelect(opt.value)"
            >
              {{ t(opt.labelKey) }}
            </li>
          </ul>
        </Transition>
      </div>
    </header>

    <section v-if="period === 'custom'" class="custom-range">
      <div class="custom-range-fields">
        <label class="custom-range-label">
          <span>{{ t('reports.from') }}</span>
          <input v-model="customDateFrom" class="custom-range-input" type="date" />
        </label>
        <label class="custom-range-label">
          <span>{{ t('reports.to') }}</span>
          <input v-model="customDateTo" class="custom-range-input" type="date" />
        </label>
      </div>
      <button class="custom-range-apply" type="button" @click="applyCustomRange">
        {{ t('common.apply') }}
      </button>
    </section>

    <div class="content">
      <template v-if="loadingSummary && summaries.length === 0">
        <div class="skeleton-hero" />
        <div class="skeleton-grid">
          <div class="skeleton-card-sm" />
          <div class="skeleton-card-sm" />
          <div class="skeleton-card-sm" />
          <div class="skeleton-card-sm" />
        </div>
        <div class="skeleton-panel" />
        <div class="skeleton-panel" />
      </template>

      <div v-else-if="errorSummary && summaries.length === 0" class="error-box">
        <p class="error-text">{{ errorSummary }}</p>
        <button class="btn-retry" @click="loadSummary">{{ t('common.retry') }}</button>
      </div>

      <template v-else>
        <div v-if="isComputing" class="computing-notice">
          {{ t('reports.backgroundRefresh') }}
        </div>

        <section class="overview-panel">
          <div class="overview-head">
            <div class="overview-copy">
              <h2 class="overview-title">{{ selectedPeriodLabel }}</h2>
            </div>

            <div class="overview-actions">
              <div class="report-currency-control">
                <div class="currency-switch" role="group" :aria-label="t('reports.reportCurrency')">
                  <button
                    type="button"
                    class="currency-switch__btn"
                    :class="{ active: reportCurrency === 'UZS' }"
                    @click="setReportCurrency('UZS')"
                  >
                    UZS
                  </button>
                  <button
                    type="button"
                    class="currency-switch__btn"
                    :class="{ active: reportCurrency === 'USD' }"
                    @click="setReportCurrency('USD')"
                  >
                    USD
                  </button>
                </div>
                <span class="report-currency-hint">{{ reportCurrencyHint }}</span>
              </div>
              <button class="action-pill" type="button" @click="openCurrencyExchange">
                {{ t('finance.exchange') }}
              </button>
              <button class="action-pill" type="button" @click="openReconciliation">
                {{ t('reports.reconciliation') }}
              </button>
            </div>
          </div>

          <div class="overview-grid">
            <article class="overview-primary">
              <span class="metric-label">{{ t('reports.revenue') }}</span>
              <strong class="overview-primary-value tabular-nums">{{ formatReportPrice(metrics.revenue) }}</strong>
              <div class="overview-primary-meta">
                <span>{{ t('reports.salesCountLine', { count: metrics.salesCount }) }}</span>
                <span>{{ t('reports.salesDaysLine', { count: metrics.salesDays }) }}</span>
                <span>{{ t('reports.returnsLine', { count: metrics.returnsCount, amount: formatReportPrice(metrics.returns) }) }}</span>
              </div>
            </article>

            <article class="metric-tile metric-tile--profit">
              <span class="metric-label">{{ t('reports.grossProfit') }}</span>
              <strong class="metric-value tabular-nums">{{ formatReportPrice(metrics.profit) }}</strong>
              <span class="metric-note">{{ t('reports.cogsLine', { amount: formatReportPrice(metrics.cogs) }) }}</span>
            </article>

            <article class="metric-tile">
              <span class="metric-label">{{ t('reports.margin') }}</span>
              <strong class="metric-value tabular-nums">{{ formatPercent(overallMargin) }}</strong>
              <span class="metric-note">{{ t('reports.marginForPeriod', { period: periodLabelLower }) }}</span>
            </article>

            <article class="metric-tile">
              <span class="metric-label">{{ t('reports.cashAccounts') }}</span>
              <div v-if="nativeCashByCurrency.length" class="cash-native-list">
                <strong
                  v-for="item in nativeCashByCurrency"
                  :key="`cash-${item.currency}`"
                  class="metric-value metric-value--stacked tabular-nums"
                >
                  {{ formatPrice(item.amount, item.currency) }}
                </strong>
              </div>
              <strong v-else class="metric-value tabular-nums">{{ formatPrice(0) }}</strong>
              <span class="metric-note">{{ t('reports.nativeBalancesNoMix') }}</span>
            </article>

            <article class="metric-tile">
              <span class="metric-label">{{ t('reports.stock') }}</span>
              <strong class="metric-value tabular-nums">{{ formatReportPrice(inventoryTotals.value) }}</strong>
              <span class="metric-note">{{ t('reports.stockQtyLine', { count: inventoryTotals.qty }) }}</span>
            </article>
          </div>

          <div class="overview-footer">
            <span class="overview-footer-label">{{ t('reports.controlMetrics') }}</span>
            <div class="inline-chip-list">
              <span class="inline-chip">{{ t('reports.receivablesLine', { amount: formatReportPrice(totalDebt) }) }}</span>
              <span class="inline-chip">{{ t('reports.payablesLine', { amount: formatReportPrice(totalPayables) }) }}</span>
              <span class="inline-chip">{{ t('reports.returnsAmountLine', { amount: formatReportPrice(metrics.returns) }) }}</span>
              <span class="inline-chip">{{ t('reports.writeoffsLine', { amount: formatReportPrice(metrics.writeoffs) }) }}</span>
              <span v-if="loadingParity" class="inline-chip">{{ t('reports.updatingBalances') }}</span>
            </div>
          </div>
        </section>

        <section class="workspace-board">
          <div class="money-layout">
            <article class="workspace-card">
              <div class="card-head">
                <div>
                  <h3 class="card-title">{{ t('finance.cashFlow') }}</h3>
                </div>
                <span class="status-chip" :class="cashFlowTotals.net < 0 ? 'status-chip--danger' : 'status-chip--positive'">
                  {{ cashFlowTotals.net < 0 ? t('finance.outflow') : t('finance.inflow') }}
                </span>
              </div>

              <div v-if="loadingCashFlow" class="cf-skeleton">
                <div class="skeleton-line skeleton-line--md" />
                <div class="skeleton-line skeleton-line--sm" />
                <div class="skeleton-line skeleton-line--md" />
                <div class="skeleton-line skeleton-line--sm" />
              </div>

              <div v-else class="money-flow-list">
                <div class="money-row">
                  <div class="money-icon money-icon--in">
                    <ArrowDownCircle :size="18" :stroke-width="1.75" />
                  </div>
                  <div class="money-meta">
                    <span class="money-label">{{ t('finance.inflow') }}</span>
                  </div>
                  <strong class="money-value money-value--in tabular-nums">{{ formatReportPrice(cashFlowTotals.inflows) }}</strong>
                </div>

                <div class="money-row">
                  <div class="money-icon money-icon--out">
                    <ArrowUpCircle :size="18" :stroke-width="1.75" />
                  </div>
                  <div class="money-meta">
                    <span class="money-label">{{ t('finance.outflow') }}</span>
                    <span v-if="metrics.returns > 0" class="money-caption">
                      {{ t('reports.includingReturns', { amount: formatReportPrice(metrics.returns) }) }}
                    </span>
                  </div>
                  <strong class="money-value money-value--out tabular-nums">{{ formatReportPrice(cashFlowTotals.outflows) }}</strong>
                </div>

                <div class="money-divider" />

                <div class="money-row money-row--total">
                  <div class="money-meta">
                    <span class="money-label">{{ t('finance.netFlow') }}</span>
                    <span class="money-caption">{{ t('reports.periodTotal', { period: periodLabelLower }) }}</span>
                  </div>
                  <strong
                    class="money-value money-value--total tabular-nums"
                    :class="signClass(cashFlowTotals.net)"
                  >
                    <TrendingUp v-if="cashFlowTotals.net >= 0" :size="14" :stroke-width="2" />
                    <TrendingDown v-else :size="14" :stroke-width="2" />
                    {{ cashFlowTotals.net >= 0 ? '+' : '' }}{{ formatReportPrice(cashFlowTotals.net) }}
                  </strong>
                </div>
              </div>

              <div v-if="nativeCashByCurrency.length" class="card-foot">
                <span class="card-caption">{{ t('reports.nativeBalancesByCurrency') }}</span>
                <div class="inline-chip-list">
                  <span
                    v-for="item in nativeCashByCurrency"
                    :key="item.currency"
                    class="inline-chip inline-chip--muted"
                  >
                    {{ formatPrice(item.amount, item.currency) }}
                  </span>
                </div>
              </div>
            </article>

            <article class="workspace-card">
              <div class="card-head">
                <div>
                  <h3 class="card-title">{{ t('reports.debtsAndStock') }}</h3>
                </div>
              </div>

              <div class="obligation-grid">
                <div class="obligation-tile">
                  <span class="metric-label">{{ t('reports.receivables') }}</span>
                  <strong class="metric-value tabular-nums">{{ formatReportPrice(totalDebt) }}</strong>
                </div>
                <div class="obligation-tile">
                  <span class="metric-label">{{ t('reports.payables') }}</span>
                  <strong class="metric-value tabular-nums">{{ formatReportPrice(totalPayables) }}</strong>
                </div>
                <div class="obligation-tile">
                  <span class="metric-label">{{ t('reports.stockAtCost') }}</span>
                  <strong class="metric-value tabular-nums">{{ formatReportPrice(inventoryTotals.value) }}</strong>
                </div>
                <div class="obligation-tile">
                  <span class="metric-label">{{ t('reports.remainingPieces') }}</span>
                  <strong class="metric-value tabular-nums">{{ inventoryTotals.qty }}</strong>
                </div>
                <div v-if="metrics.writeoffs > 0" class="obligation-tile">
                  <span class="metric-label">{{ t('investors.writeoffs') }}</span>
                  <strong class="metric-value tabular-nums">{{ formatReportPrice(metrics.writeoffs) }}</strong>
                </div>
              </div>

              <div class="divider-line" />

              <div class="list-block">
                <div class="list-head">
                  <span class="card-caption">{{ t('reports.topDebtors') }}</span>
                  <span class="card-caption">{{ sortedDebtors.length }}</span>
                </div>

                <div v-if="loadingDebt" class="debt-skeleton">
                  <div v-for="n in 3" :key="n" class="skeleton-row" />
                </div>

                <template v-else-if="visibleDebtors.length">
                  <div class="compact-debt-list">
                    <div
                      v-for="debtor in visibleDebtors"
                      :key="debtor.id"
                      class="compact-debt-row"
                    >
                      <div class="debtor-avatar" aria-hidden="true">
                        {{ debtor.name.charAt(0).toUpperCase() }}
                      </div>
                      <div class="debtor-info">
                        <span class="debtor-name">{{ debtor.name }}</span>
                        <span class="debtor-phone">
                          {{ debtExpanded ? (debtor.phone || t('reports.noPhone')) : t('customers.customer') }}
                        </span>
                      </div>
                      <strong class="debtor-amount tabular-nums">{{ formatReportPrice(debtor.outstanding_balance) }}</strong>
                    </div>
                  </div>

                  <button
                    v-if="hasMoreDebtors"
                    type="button"
                    class="expand-btn expand-btn--soft"
                    @click="toggleDebtExpanded"
                  >
                    {{ debtExpanded ? t('reports.collapseList') : t('reports.showMoreCount', { count: hiddenDebtorsCount }) }}
                  </button>
                </template>

                <div v-else class="empty-inline">
                  <ShoppingCart :size="18" :stroke-width="1.5" />
                  <span>{{ t('reports.noCustomerDebts') }}</span>
                </div>
              </div>
            </article>
          </div>
        </section>

        <section class="workspace-board">
          <div class="workspace-head workspace-head--analytics">
            <div>
              <h2 class="workspace-title">{{ t('reports.profitability') }}</h2>
              <p class="workspace-note">{{ t('reports.profitabilityHint') }}</p>
            </div>

            <div class="analytics-switch" role="tablist" :aria-label="t('reports.profitabilityType')">
              <button
                type="button"
                class="analytics-switch-btn"
                :class="{ active: analyticsView === 'sales' }"
                @click="setAnalyticsView('sales')"
              >
                {{ t('sales.history') }}
              </button>
              <button
                type="button"
                class="analytics-switch-btn"
                :class="{ active: analyticsView === 'products' }"
                @click="setAnalyticsView('products')"
              >
                {{ t('products.title') }}
              </button>
              <button
                type="button"
                class="analytics-switch-btn"
                :class="{ active: analyticsView === 'procurements' }"
                @click="setAnalyticsView('procurements')"
              >
                {{ t('procurements.title') }}
              </button>
            </div>
          </div>

          <p v-if="loadingAnalytics" class="workspace-note">{{ t('reports.loadingAnalytics') }}</p>

          <template
            v-else-if="
              analyticsView === 'sales'
                ? salesProfitability.length
                : analyticsView === 'products'
                  ? productProfitability.length
                  : procurementProfitability.length
            "
          >
            <div class="summary-strip">
              <template v-if="analyticsView === 'sales'">
                <div class="summary-card summary-card--primary">
                  <span class="metric-label">{{ t('reports.grossProfit') }}</span>
                  <strong class="metric-value tabular-nums">{{ formatPrice(salesProfitabilityTotals.grossProfit, reportCurrency) }}</strong>
                  <span class="metric-note">
                    {{ t('reports.marginValue', {
                      value:
                      formatPercent(
                        salesProfitabilityTotals.revenue > 0
                          ? (salesProfitabilityTotals.grossProfit / salesProfitabilityTotals.revenue) * 100
                          : 0,
                      )
                    }) }}
                  </span>
                </div>
                <div class="summary-card">
                  <span class="metric-label">{{ t('reports.revenue') }}</span>
                  <strong class="metric-value tabular-nums">{{ formatPrice(salesProfitabilityTotals.revenue, reportCurrency) }}</strong>
                  <span class="metric-note">{{ t('reports.cogsLine', { amount: formatPrice(salesProfitabilityTotals.cogs, reportCurrency) }) }}</span>
                </div>
                <div class="summary-footer">
                  <button
                    type="button"
                    class="expand-btn expand-btn--soft"
                    @click="salesSummaryExpanded = !salesSummaryExpanded"
                  >
                    {{ salesSummaryExpanded ? t('reports.hideMetrics') : t('reports.moreMetrics') }}
                  </button>
                  <div v-if="salesSummaryExpanded" class="summary-support">
                    <span class="inline-chip inline-chip--muted">{{ t('reports.investorLine', { amount: formatPrice(salesProfitabilityTotals.investorProfit, reportCurrency) }) }}</span>
                    <span class="inline-chip inline-chip--muted">{{ t('reports.businessLine', { amount: formatPrice(salesProfitabilityTotals.businessProfit, reportCurrency) }) }}</span>
                    <span class="inline-chip inline-chip--muted">{{ t('reports.linesCount', { count: salesProfitabilityTotals.lineCount }) }}</span>
                    <span class="inline-chip inline-chip--muted">{{ t('reports.pcsShort', { count: salesProfitabilityTotals.quantitySold }) }}</span>
                  </div>
                </div>
              </template>

              <template v-else-if="analyticsView === 'products'">
                <div class="summary-card summary-card--primary">
                  <span class="metric-label">{{ t('reports.factualProfit') }}</span>
                  <strong class="metric-value tabular-nums">{{ formatPrice(productProfitabilityTotals.grossProfit, reportCurrency) }}</strong>
                </div>
                <div class="summary-card">
                  <span class="metric-label">{{ t('reports.profitForecast') }}</span>
                  <strong class="metric-value tabular-nums">{{ formatPrice(productProfitabilityTotals.projectedGrossProfit, reportCurrency) }}</strong>
                </div>
                <div class="summary-footer">
                  <button
                    type="button"
                    class="expand-btn expand-btn--soft"
                    @click="productsSummaryExpanded = !productsSummaryExpanded"
                  >
                    {{ productsSummaryExpanded ? t('reports.hideMetrics') : t('reports.moreMetrics') }}
                  </button>
                  <div v-if="productsSummaryExpanded" class="summary-support">
                    <span class="inline-chip inline-chip--muted">{{ t('reports.salesAmountLine', { amount: formatPrice(productProfitabilityTotals.revenue, reportCurrency) }) }}</span>
                    <span class="inline-chip inline-chip--muted">{{ t('reports.remainingAmountLine', { amount: formatPrice(productProfitabilityTotals.remainingLandedCost, reportCurrency) }) }}</span>
                    <span class="inline-chip inline-chip--muted">{{ t('reports.remainingQtyLine', { count: productProfitabilityTotals.remainingQuantity }) }}</span>
                  </div>
                </div>
              </template>

              <template v-else>
                <div class="summary-card summary-card--primary">
                  <span class="metric-label">{{ t('reports.factualProfit') }}</span>
                  <strong class="metric-value tabular-nums">{{ formatPrice(procurementProfitabilityTotals.grossProfit, reportCurrency) }}</strong>
                  <span class="metric-note">{{ t('reports.investorBusinessLine', {
                    investor: formatPrice(procurementProfitabilityTotals.investorProfit, reportCurrency),
                    business: formatPrice(procurementProfitabilityTotals.businessProfit, reportCurrency),
                  }) }}</span>
                </div>
                <div class="summary-card">
                  <span class="metric-label">{{ t('reports.profitForecast') }}</span>
                  <strong class="metric-value tabular-nums">{{ formatPrice(procurementProfitabilityTotals.projectedGrossProfit, reportCurrency) }}</strong>
                  <span class="metric-note">{{ t('reports.remainingAmountLine', { amount: formatPrice(procurementProfitabilityTotals.remainingLandedCost, reportCurrency) }) }}</span>
                </div>
                <div class="summary-footer">
                  <button
                    type="button"
                    class="expand-btn expand-btn--soft"
                    @click="procurementsSummaryExpanded = !procurementsSummaryExpanded"
                  >
                    {{ procurementsSummaryExpanded ? t('reports.hideMetrics') : t('reports.moreMetrics') }}
                  </button>
                  <div v-if="procurementsSummaryExpanded" class="summary-support">
                    <span class="inline-chip inline-chip--muted">{{ t('reports.revenueLine', { amount: formatPrice(procurementProfitabilityTotals.revenue, reportCurrency) }) }}</span>
                    <span class="inline-chip inline-chip--muted">{{ t('reports.soldPcsLine', { count: procurementProfitabilityTotals.quantitySold }) }}</span>
                    <span class="inline-chip inline-chip--muted">{{ t('reports.inStockPcsLine', { count: procurementProfitabilityTotals.remainingQuantity }) }}</span>
                    <span class="inline-chip inline-chip--muted">{{ t('reports.investorForecastLine', { amount: formatPrice(procurementProfitabilityTotals.projectedInvestorProfit, reportCurrency) }) }}</span>
                  </div>
                </div>
              </template>
            </div>

            <div class="toolbar-row">
              <div
                v-if="analyticsView === 'sales'"
                class="segment-control"
                role="tablist"
                :aria-label="t('reports.salesSorting')"
              >
                <button type="button" class="segment-btn" :class="{ active: salesSort === 'profit' }" @click="setSalesSort('profit')">
                  {{ t('reports.sortByProfit') }}
                </button>
                <button type="button" class="segment-btn" :class="{ active: salesSort === 'margin' }" @click="setSalesSort('margin')">
                  {{ t('reports.sortByMargin') }}
                </button>
                <button type="button" class="segment-btn" :class="{ active: salesSort === 'revenue' }" @click="setSalesSort('revenue')">
                  {{ t('reports.sortByRevenue') }}
                </button>
              </div>

              <div
                v-else-if="analyticsView === 'products'"
                class="segment-control"
                role="tablist"
                :aria-label="t('reports.productsSorting')"
              >
                <button type="button" class="segment-btn" :class="{ active: productSort === 'profit' }" @click="setProductSort('profit')">
                  {{ t('reports.sortByProfit') }}
                </button>
                <button type="button" class="segment-btn" :class="{ active: productSort === 'projected' }" @click="setProductSort('projected')">
                  {{ t('reports.sortByForecast') }}
                </button>
                <button type="button" class="segment-btn" :class="{ active: productSort === 'remaining' }" @click="setProductSort('remaining')">
                  {{ t('reports.sortByRemaining') }}
                </button>
              </div>

              <div
                v-else
                class="segment-control"
                role="tablist"
                :aria-label="t('reports.procurementsSorting')"
              >
                <button type="button" class="segment-btn" :class="{ active: procurementSort === 'profit' }" @click="setProcurementSort('profit')">
                  {{ t('reports.sortByProfit') }}
                </button>
                <button type="button" class="segment-btn" :class="{ active: procurementSort === 'projected' }" @click="setProcurementSort('projected')">
                  {{ t('reports.sortByForecast') }}
                </button>
                <button type="button" class="segment-btn" :class="{ active: procurementSort === 'remaining' }" @click="setProcurementSort('remaining')">
                  {{ t('reports.sortByRemaining') }}
                </button>
              </div>

              <span class="workspace-note">
                {{ analyticsView === 'sales'
                  ? t('reports.salesInSlice', { count: salesProfitabilitySorted.length })
                  : analyticsView === 'products'
                    ? t('reports.productsInSlice', { count: productProfitabilitySorted.length })
                    : t('reports.procurementsInSlice', { count: procurementProfitabilitySorted.length })
                }}
              </span>
            </div>

            <div class="analytics-table">
              <div class="analytics-table-note">
                <span>{{
                  analyticsView === 'sales'
                    ? t('reports.sortLeaders')
                    : analyticsView === 'products'
                      ? t('reports.productLeaders')
                      : t('reports.procurementLeaders')
                }}</span>
                <span>{{ t('reports.rowOpensDetails') }}</span>
              </div>

              <template v-if="analyticsView === 'sales'">
                <article
                  v-for="sale in visibleSalesProfitability"
                  :key="sale.sale_id"
                  class="analytics-row"
                  :class="{ open: expandedSaleId === sale.sale_id }"
                >
                  <button type="button" class="analytics-toggle" @click="toggleSaleExpanded(sale.sale_id)">
                    <div class="analytics-main">
                      <div class="analytics-title-row">
                        <strong class="analytics-title">{{ t('reports.saleAudit.saleNumber', { id: sale.sale_id }) }}</strong>
                        <span class="analytics-badge">{{ t('reports.linesCount', { count: sale.line_count }) }}</span>
                      </div>
                      <span class="analytics-meta">{{ formatDateTime(sale.date) }} · {{ sale.location_name }}</span>
                      <span class="analytics-meta">{{ t('reports.pcsShort', { count: sale.quantity_sold }) }} · {{ sale.customer_name || t('reports.saleAudit.noCustomer') }}</span>
                    </div>
                    <div class="analytics-side">
                      <strong class="analytics-amount tabular-nums">{{ formatRowReportPrice(sale, 'gross_profit', sale.gross_profit) }}</strong>
                      <span class="analytics-side-meta">
                        <span class="analytics-trend">{{ t('reports.marginValue', { value: formatPercent(sale.margin_percent) }) }}</span>
                        <ChevronDown
                          :size="16"
                          :stroke-width="1.8"
                          class="analytics-chevron"
                          :class="{ open: expandedSaleId === sale.sale_id }"
                        />
                      </span>
                    </div>
                  </button>

                  <div v-if="expandedSaleId === sale.sale_id" class="analytics-details">
                    <span class="detail-chip">{{ t('reports.revenueLine', { amount: formatRowReportPrice(sale, 'revenue', sale.revenue) }) }}</span>
                    <span class="detail-chip">{{ t('reports.cogsLine', { amount: formatRowReportPrice(sale, 'cogs', sale.cogs) }) }}</span>
                    <span class="detail-chip">{{ t('reports.investorLine', { amount: formatRowReportPrice(sale, 'investor_profit', sale.investor_profit) }) }}</span>
                    <span class="detail-chip">{{ t('reports.businessLine', { amount: formatRowReportPrice(sale, 'business_profit', sale.business_profit) }) }}</span>
                    <span class="detail-chip">{{ paymentMethodsLabel(sale.payment_methods) }}</span>
                    <button type="button" class="detail-chip detail-chip--action" @click.stop="openSaleExplanation(sale.sale_id)">
                      {{ t('reports.saleAudit.title') }}
                    </button>
                  </div>
                </article>
              </template>

              <template v-else-if="analyticsView === 'products'">
                <article
                  v-for="product in visibleProductProfitability"
                  :key="product.product_variant_id"
                  class="analytics-row"
                  :class="{ open: expandedProductId === product.product_variant_id }"
                >
                  <button type="button" class="analytics-toggle" @click="toggleProductExpanded(product.product_variant_id)">
                    <div class="analytics-main">
                      <div class="analytics-title-row">
                        <strong class="analytics-title">{{ product.product_name }}</strong>
                        <span class="analytics-badge">{{ t('reports.soldPcsLine', { count: product.quantity_sold }) }}</span>
                      </div>
                      <span class="analytics-meta">{{ t('reports.remainingQtyLine', { count: product.remaining_quantity }) }}</span>
                      <span class="analytics-meta">{{ t('reports.priceLine', { amount: formatRowReportPrice(product, 'current_unit_price', product.current_unit_price) }) }}</span>
                    </div>
                    <div class="analytics-side">
                      <strong class="analytics-amount tabular-nums">{{ formatRowReportPrice(product, 'gross_profit', product.gross_profit) }}</strong>
                      <span class="analytics-side-meta">
                        <span class="analytics-trend">{{ t('reports.marginValue', { value: formatPercent(product.margin_percent) }) }}</span>
                        <ChevronDown
                          :size="16"
                          :stroke-width="1.8"
                          class="analytics-chevron"
                          :class="{ open: expandedProductId === product.product_variant_id }"
                        />
                      </span>
                    </div>
                  </button>

                  <div v-if="expandedProductId === product.product_variant_id" class="analytics-details">
                    <span class="detail-chip">{{ t('reports.salesAmountLine', { amount: formatRowReportPrice(product, 'revenue', product.revenue) }) }}</span>
                    <span class="detail-chip">{{ t('reports.actualLine', { amount: formatRowReportPrice(product, 'gross_profit', product.gross_profit) }) }}</span>
                    <span class="detail-chip">{{ t('reports.remainingAmountLine', { amount: formatRowReportPrice(product, 'remaining_landed_cost', product.remaining_landed_cost) }) }}</span>
                    <span class="detail-chip">{{ t('reports.forecastLine', { amount: formatRowReportPrice(product, 'projected_gross_profit', product.projected_gross_profit) }) }}</span>
                    <span class="detail-chip">{{ t('reports.investorLine', { amount: formatRowReportPrice(product, 'projected_investor_profit', product.projected_investor_profit) }) }}</span>
                    <span class="detail-chip">{{ t('reports.businessLine', { amount: formatRowReportPrice(product, 'projected_business_profit', product.projected_business_profit) }) }}</span>
                  </div>
                </article>
              </template>

              <template v-else>
                <article
                  v-for="procurement in visibleProcurementProfitability"
                  :key="procurement.procurement_id"
                  class="analytics-row"
                  :class="{ open: expandedProcurementId === procurement.procurement_id }"
                >
                  <button type="button" class="analytics-toggle" @click="toggleProcurementExpanded(procurement.procurement_id)">
                    <div class="analytics-main">
                      <div class="analytics-title-row">
                        <strong class="analytics-title">{{ t('procurements.procurementNumber', { id: procurement.procurement_id }) }}</strong>
                        <span class="analytics-badge">{{ procurement.item_count }} SKU</span>
                      </div>
                      <span class="analytics-meta">{{ procurementDateLabel(procurement) }} · {{ procurement.supplier_name || t('procurements.supplierMissing') }}</span>
                      <span class="analytics-meta">{{ procurementStatusLabel(procurement.status) }} · {{ t('reports.soldShortCount', { count: procurement.quantity_sold }) }} · {{ t('reports.remainingShortCount', { count: procurement.remaining_quantity }) }}</span>
                    </div>
                    <div class="analytics-side">
                      <strong class="analytics-amount tabular-nums">{{ formatRowReportPrice(procurement, 'gross_profit', procurement.gross_profit) }}</strong>
                      <span class="analytics-side-meta">
                        <span class="analytics-trend">{{ t('reports.forecastLine', { amount: formatRowReportPrice(procurement, 'projected_gross_profit', procurement.projected_gross_profit) }) }}</span>
                        <ChevronDown
                          :size="16"
                          :stroke-width="1.8"
                          class="analytics-chevron"
                          :class="{ open: expandedProcurementId === procurement.procurement_id }"
                        />
                      </span>
                    </div>
                  </button>

                  <div v-if="expandedProcurementId === procurement.procurement_id" class="analytics-details">
                    <span class="detail-chip">{{ procurementTypeLabel(procurement.funding_source) }}</span>
                    <span class="detail-chip">{{ procurementStatusLabel(procurement.status) }}</span>
                    <span class="detail-chip">{{ t('reports.revenueLine', { amount: formatRowReportPrice(procurement, 'revenue', procurement.revenue) }) }}</span>
                    <span class="detail-chip">{{ t('reports.cogsLine', { amount: formatRowReportPrice(procurement, 'cogs', procurement.cogs) }) }}</span>
                    <span class="detail-chip">{{ t('reports.actualLine', { amount: formatRowReportPrice(procurement, 'gross_profit', procurement.gross_profit) }) }}</span>
                    <span class="detail-chip">{{ t('reports.investorLine', { amount: formatRowReportPrice(procurement, 'investor_profit', procurement.investor_profit) }) }}</span>
                    <span class="detail-chip">{{ t('reports.businessLine', { amount: formatRowReportPrice(procurement, 'business_profit', procurement.business_profit) }) }}</span>
                    <span class="detail-chip">{{ t('reports.remainingAmountLine', { amount: formatRowReportPrice(procurement, 'remaining_landed_cost', procurement.remaining_landed_cost) }) }}</span>
                    <span class="detail-chip">{{ t('reports.forecastLine', { amount: formatRowReportPrice(procurement, 'projected_gross_profit', procurement.projected_gross_profit) }) }}</span>
                    <span class="detail-chip">{{ t('reports.investorForecastLine', { amount: formatRowReportPrice(procurement, 'projected_investor_profit', procurement.projected_investor_profit) }) }}</span>
                    <span class="detail-chip">{{ t('reports.businessForecastLine', { amount: formatRowReportPrice(procurement, 'projected_business_profit', procurement.projected_business_profit) }) }}</span>
                    <button type="button" class="detail-chip detail-chip--action" @click.stop="openProcurementAudit(procurement.procurement_id)">
                      {{ t('reports.procurementAudit') }}
                    </button>
                  </div>
                </article>
              </template>
            </div>

            <button
              v-if="
                analyticsView === 'sales'
                  ? salesProfitabilitySorted.length > ANALYTICS_PREVIEW_LIMIT
                  : analyticsView === 'products'
                    ? productProfitabilitySorted.length > ANALYTICS_PREVIEW_LIMIT
                    : procurementProfitabilitySorted.length > ANALYTICS_PREVIEW_LIMIT
              "
              type="button"
              class="expand-btn"
              @click="
                analyticsView === 'sales'
                  ? (salesExpanded = !salesExpanded)
                  : analyticsView === 'products'
                    ? (productsExpanded = !productsExpanded)
                    : (procurementsExpanded = !procurementsExpanded)
              "
            >
              {{
                analyticsView === 'sales'
                  ? (
                    salesExpanded
                      ? t('reports.collapseSales')
                      : t('reports.showMoreSales', { count: salesProfitabilitySorted.length - visibleSalesProfitability.length })
                  )
                  : (
                    analyticsView === 'products'
                      ? (
                        productsExpanded
                          ? t('reports.collapseProducts')
                          : t('reports.showMoreProducts', { count: productProfitabilitySorted.length - visibleProductProfitability.length })
                      )
                      : (
                        procurementsExpanded
                          ? t('reports.collapseProcurements')
                          : t('reports.showMoreProcurements', { count: procurementProfitabilitySorted.length - visibleProcurementProfitability.length })
                      )
                  )
              }}
            </button>
          </template>

          <p v-else class="workspace-note">
            {{ analyticsView === 'sales'
              ? t('reports.noSalesForPeriod')
              : analyticsView === 'products'
                ? t('reports.noProductData')
                : t('reports.noProcurementData')
            }}
          </p>
        </section>
      </template>
    </div>
  </div>
</template>

<style scoped>
.computing-notice {
  margin: var(--space-3) var(--space-5);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--color-brand-50) 60%, transparent);
  border: 1px solid var(--color-brand-200, #c7d2fe);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  text-align: center;
}

.reports-page {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  background:
    radial-gradient(circle at top right, color-mix(in srgb, var(--color-brand-50) 70%, transparent) 0, transparent 32%),
    var(--color-bg-primary);
  padding-bottom: calc(var(--bottom-nav-height) + var(--space-8));
}

.page-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5);
  background: color-mix(in srgb, var(--color-bg-primary) 92%, white);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--color-border-subtle);
}

.page-title {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.period-selector { position: relative; }

.period-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  min-height: 38px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  transition: border-color var(--duration-fast) var(--ease-out), color var(--duration-fast) var(--ease-out);
}

.period-btn.open,
.period-btn:hover {
  border-color: var(--color-brand-300);
  color: var(--color-brand-700);
}

.period-chevron {
  transition: transform var(--duration-fast) var(--ease-out);
}

.period-btn.open .period-chevron {
  transform: rotate(180deg);
}

.period-menu {
  position: absolute;
  right: 0;
  top: calc(100% + var(--space-2));
  min-width: 138px;
  padding: var(--space-1) 0;
  list-style: none;
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.period-option {
  padding: var(--space-3) var(--space-4);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
}

.period-option:hover,
.period-option.active {
  background: var(--color-brand-50);
  color: var(--color-brand-700);
}

.custom-range {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-5);
  border-bottom: 1px solid var(--color-border-subtle);
}

.custom-range-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-2);
  flex: 1;
}

.custom-range-label {
  display: grid;
  gap: var(--space-1);
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
}

.custom-range-input {
  width: 100%;
  min-height: 40px;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
}

.custom-range-apply,
.action-pill,
.expand-btn,
.btn-retry {
  min-height: 40px;
  padding: 0 var(--space-4);
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  white-space: nowrap;
}

.custom-range-apply,
.btn-retry {
  background: var(--color-brand-500);
  border-color: transparent;
  color: var(--color-text-inverse);
}

.content {
  flex: 1;
  display: grid;
  gap: var(--space-4);
  padding: var(--space-5);
}

.overview-panel,
.workspace-card,
.analytics-table,
.error-box {
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-xl);
  background: var(--color-bg-elevated);
}

.overview-panel {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-5);
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--color-brand-50) 60%, white) 0%, var(--color-bg-elevated) 38%);
}

.overview-head,
.workspace-head,
.card-head,
.toolbar-row,
.list-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}

.overview-copy,
.workspace-note,
.card-head > div {
  min-width: 0;
}

.overview-kicker,
.card-kicker,
.overview-footer-label,
.card-caption {
  display: block;
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.overview-title,
.workspace-title,
.card-title {
  color: var(--color-text-primary);
  font-weight: var(--font-semibold);
}

.workspace-title,
.card-title {
  font-size: var(--text-lg);
  line-height: var(--leading-tight);
}

.overview-title {
  font-size: clamp(1.4rem, 3vw, 2rem);
  line-height: 1.05;
}

.overview-note,
.workspace-note,
.money-caption,
.analytics-meta,
.analytics-trend,
.metric-note,
.debtor-phone,
.error-text {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.45;
}

.overview-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.report-currency-control {
  min-width: 160px;
  display: grid;
  gap: 4px;
}

.report-currency-hint {
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
  line-height: 1.25;
}

.currency-switch {
  display: inline-grid;
  grid-template-columns: repeat(2, minmax(46px, 1fr));
  min-height: 40px;
  padding: 3px;
  border-radius: var(--radius-full);
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-subtle);
}

.currency-switch__btn {
  min-height: 32px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-full);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.currency-switch__btn.active {
  background: var(--color-bg-elevated);
  color: var(--color-brand-700);
  box-shadow: var(--shadow-xs);
}

.overview-grid,
.obligation-grid,
.summary-strip,
.skeleton-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-2);
}

.overview-primary,
.metric-tile,
.obligation-tile,
.summary-card {
  display: grid;
  gap: 4px;
  padding: var(--space-3);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-bg-primary) 74%, white);
}

.overview-primary {
  grid-column: 1 / -1;
  padding: var(--space-4);
}

.metric-label {
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.overview-primary-value {
  color: var(--color-text-primary);
  font-size: clamp(2rem, 4vw, 3rem);
  font-weight: var(--font-bold);
  line-height: 1;
}

.overview-primary-meta,
.inline-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
}

.metric-value {
  color: var(--color-text-primary);
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  overflow-wrap: anywhere;
}

.cash-native-list {
  display: grid;
  gap: 2px;
}

.metric-value--stacked {
  line-height: var(--leading-tight);
}

.metric-tile--profit .metric-value { color: var(--color-success); }
.metric-tile--brand .metric-value { color: var(--color-brand-700); }
.metric-tile--danger .metric-value { color: var(--color-error); }

.overview-footer {
  display: grid;
  gap: var(--space-2);
}

.inline-chip {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-full);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-default);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

.inline-chip--muted {
  color: var(--color-text-secondary);
}

.workspace-board {
  display: grid;
  gap: var(--space-3);
}

.money-layout {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}

.workspace-card {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
}

.status-chip {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  white-space: nowrap;
}

.status-chip--positive {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.status-chip--danger {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.money-flow-list {
  display: grid;
  gap: var(--space-2);
}

.money-row {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-3);
}

.money-row--total {
  grid-template-columns: minmax(0, 1fr) auto;
}

.money-icon {
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
}

.money-icon--in {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.money-icon--out {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.money-meta {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.money-label {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.money-value {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  white-space: nowrap;
}

.money-value--in { color: var(--color-success); }
.money-value--out { color: var(--color-error); }
.money-value--total {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--color-text-primary);
}

.money-value--total.positive { color: var(--color-success); }
.money-value--total.negative { color: var(--color-error); }

.money-divider,
.divider-line {
  height: 1px;
  background: var(--color-border-subtle);
}

.card-foot,
.list-block {
  display: grid;
  gap: var(--space-2);
}

.obligation-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.compact-debt-list {
  display: grid;
  gap: var(--space-2);
}

.compact-debt-row {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2);
  border-radius: var(--radius-lg);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-subtle);
}

.debtor-avatar {
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  background: var(--color-brand-100);
  color: var(--color-brand-700);
  font-size: var(--text-sm);
  font-weight: var(--font-bold);
}

.debtor-info {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.debtor-name {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.debtor-amount {
  color: var(--color-error);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  white-space: nowrap;
}

.empty-inline {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.analytics-switch {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px;
  border-radius: var(--radius-full);
  background: var(--color-bg-sunken);
}

.analytics-switch-btn,
.segment-btn {
  min-height: 34px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-full);
  border: 1px solid transparent;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

.analytics-switch-btn.active,
.segment-btn.active {
  background: var(--color-bg-elevated);
  border-color: var(--color-border-default);
  color: var(--color-text-primary);
}

.segment-control {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.summary-card {
  background: var(--color-bg-elevated);
}

.summary-card--primary {
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--color-brand-50) 62%, white) 0%, var(--color-bg-elevated) 100%);
}

.summary-support {
  grid-column: 1 / -1;
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.summary-footer {
  grid-column: 1 / -1;
  display: grid;
  gap: var(--space-2);
  justify-items: start;
}

.expand-btn--soft {
  justify-self: start;
  padding-left: 0;
  padding-right: 0;
  border: 0;
  background: transparent;
  color: var(--color-brand-700);
}

.analytics-table {
  overflow: hidden;
  display: grid;
}

.analytics-table-note {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg-sunken);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
}

.analytics-row {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  border-top: 1px solid var(--color-border-subtle);
}

.analytics-row.open {
  background: color-mix(in srgb, var(--color-brand-50) 28%, white);
}

.analytics-toggle {
  width: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--space-3);
  align-items: start;
  padding: var(--space-3) var(--space-2);
  border: 0;
  border-radius: var(--radius-lg);
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.analytics-main,
.analytics-side,
.analytics-details {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.analytics-title-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.analytics-title {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.analytics-badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 10px;
  border-radius: var(--radius-full);
  background: var(--color-brand-50);
  color: var(--color-brand-700);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
}

.analytics-side {
  justify-items: end;
  text-align: right;
}

.analytics-side-meta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.analytics-amount {
  color: var(--color-text-primary);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  white-space: nowrap;
}

.analytics-chevron {
  color: var(--color-text-tertiary);
  transition: transform var(--duration-fast) var(--ease-out);
}

.analytics-chevron.open {
  transform: rotate(180deg);
}

.analytics-details {
  padding: 0 var(--space-2) var(--space-3);
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-2);
}

.detail-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 30px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-full);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-subtle);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.detail-chip--action {
  color: var(--color-brand-700);
  border-color: var(--color-brand-200);
  background: var(--color-brand-50);
  font-weight: var(--font-medium);
}

.error-box {
  display: grid;
  place-items: center;
  gap: var(--space-3);
  padding: var(--space-12) var(--space-5);
  text-align: center;
}

.btn-retry {
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  border-color: transparent;
}

.skeleton-hero,
.skeleton-card-sm,
.skeleton-panel,
.skeleton-line,
.skeleton-row {
  border-radius: var(--radius-lg);
  background: var(--color-bg-sunken);
  animation: shimmer 1.4s ease-in-out infinite;
}

.skeleton-hero {
  height: 168px;
}

.skeleton-card-sm {
  height: 88px;
}

.skeleton-panel {
  height: 220px;
}

.cf-skeleton,
.debt-skeleton {
  display: grid;
  gap: var(--space-2);
}

.skeleton-line--sm { height: 14px; width: 55%; }
.skeleton-line--md { height: 16px; width: 82%; }
.skeleton-row { height: 52px; }

@keyframes shimmer {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.52; }
}

.dropdown-enter-active,
.dropdown-leave-active {
  transition: opacity var(--duration-fast) var(--ease-out), transform var(--duration-fast) var(--ease-out);
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

@media (max-width: 900px) {
  .money-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .page-header,
  .custom-range,
  .content {
    padding-left: var(--space-4);
    padding-right: var(--space-4);
  }

  .custom-range {
    flex-direction: column;
    align-items: stretch;
  }

  .custom-range-apply {
    width: 100%;
  }

  .overview-head,
  .workspace-head,
  .toolbar-row,
  .card-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .overview-actions {
    display: flex;
    flex-wrap: nowrap;
    align-items: center;
    width: 100%;
    gap: 6px;
  }

  .report-currency-control {
    min-width: 0;
    flex: 1 1 112px;
  }

  .report-currency-hint {
    max-width: 156px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .currency-switch {
    min-height: 36px;
    grid-template-columns: repeat(2, minmax(36px, 1fr));
  }

  .currency-switch__btn {
    min-height: 28px;
    padding: 0 8px;
  }

  .action-pill {
    min-height: 36px;
    padding: 0 12px;
    font-size: var(--text-xs);
    flex: 0 0 auto;
  }

  .overview-grid,
  .obligation-grid {
    grid-template-columns: 1fr;
  }

  .summary-strip,
  .skeleton-grid {
    grid-template-columns: 1fr;
  }

  .overview-panel,
  .workspace-card {
    padding: var(--space-4);
  }

  .overview-primary {
    padding: var(--space-3);
  }

  .overview-primary-value {
    font-size: 1.9rem;
  }

  .metric-value {
    font-size: var(--text-base);
    line-height: 1.2;
  }

  .metric-note {
    font-size: var(--text-xs);
  }

  .card-head {
    flex-direction: row;
    align-items: center;
  }

  .card-title,
  .workspace-title {
    font-size: var(--text-lg);
  }

  .status-chip {
    min-height: 26px;
    padding: 0 10px;
  }

  .analytics-switch,
  .segment-control {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    width: 100%;
    overflow: hidden;
    gap: 4px;
    padding: 4px;
    border-radius: var(--radius-full);
    background: var(--color-bg-sunken);
  }

  .analytics-switch-btn,
  .segment-btn {
    width: 100%;
    min-width: 0;
    padding: 0 var(--space-2);
    justify-content: center;
    text-align: center;
    font-size: var(--text-xs);
  }

  .inline-chip,
  .detail-chip {
    white-space: nowrap;
  }

  .toolbar-row {
    gap: var(--space-2);
  }

  .toolbar-row .workspace-note {
    font-size: var(--text-xs);
  }

  .summary-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .summary-card {
    min-width: 0;
    padding: var(--space-3);
  }

  .summary-card .metric-value {
    font-size: var(--text-base);
    line-height: 1.2;
    overflow-wrap: anywhere;
  }

  .summary-card .metric-note {
    font-size: var(--text-xs);
  }

  .summary-footer {
    grid-column: 1 / -1;
  }

  .analytics-table-note {
    flex-direction: row;
    align-items: center;
    padding: var(--space-2) var(--space-3);
    background: var(--color-bg-primary);
    border-bottom: 1px solid var(--color-border-subtle);
  }

  .analytics-table-note span:first-child {
    color: var(--color-text-primary);
    font-weight: var(--font-semibold);
  }

  .analytics-table-note span:last-child {
    display: none;
  }

  .analytics-row {
    gap: 0;
    padding: 0;
  }

  .analytics-toggle {
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-3);
    border-radius: 0;
  }

  .analytics-title-row {
    flex-wrap: nowrap;
    gap: var(--space-1);
  }

  .analytics-title {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .analytics-badge {
    flex-shrink: 0;
    min-height: 20px;
    padding: 0 8px;
    font-size: 11px;
  }

  .analytics-main .analytics-meta:nth-of-type(n + 2) {
    display: none;
  }

  .analytics-meta {
    font-size: var(--text-xs);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .analytics-side {
    justify-items: end;
    text-align: right;
  }

  .analytics-amount {
    font-size: var(--text-sm);
  }

  .analytics-side-meta {
    justify-content: flex-end;
    gap: 4px;
  }

  .analytics-trend {
    font-size: var(--text-xs);
  }

  .analytics-details {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    padding: 0 var(--space-3) var(--space-3);
  }

  .detail-chip {
    min-width: 0;
    min-height: 28px;
    justify-content: flex-start;
    padding: 0 var(--space-2);
    overflow: hidden;
    text-overflow: ellipsis;
    font-size: var(--text-xs);
  }

  .money-row,
  .compact-debt-row {
    grid-template-columns: 32px minmax(0, 1fr) auto;
    gap: var(--space-2);
  }

  .money-row--total {
    grid-template-columns: minmax(0, 1fr) auto;
  }
}

@media (prefers-reduced-motion: reduce) {
  .period-chevron,
  .period-btn,
  .dropdown-enter-active,
  .dropdown-leave-active,
  .skeleton-hero,
  .skeleton-card-sm,
  .skeleton-panel,
  .skeleton-line,
  .skeleton-row {
    transition: none;
    animation: none;
  }
}
</style>
