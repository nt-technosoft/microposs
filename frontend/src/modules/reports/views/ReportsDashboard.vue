<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { TrendingUp, TrendingDown, ShoppingCart, ArrowDownCircle, ArrowUpCircle, ChevronDown } from 'lucide-vue-next'
import {
  fetchDailySummaries,
  fetchCashFlow,
  fetchTrialBalance,
  fetchCashAccounts,
  fetchSalesProfitability,
  fetchProductProfitability,
  type DailySummary,
  type CashFlowItem,
  type CashAccountRecord,
  type SaleProfitabilityRow,
  type ProductProfitabilityRow,
} from '@/api/finance'
import { fetchDebtSummary, type DebtSummaryItem } from '@/api/customers'
import { fetchPayablesSummary, type PayablesSummaryItem } from '@/api/suppliers'
import { fetchStockSummary, type StockSummaryItem } from '@/api/inventory'
import { useToast } from '@/composables/useToast'
import { formatPrice } from '@/utils/currency'

// ── Types ───────────────────────────────────────────────────────────────────

type Period = 'today' | 'week' | 'month' | 'all' | 'custom'
type AnalyticsView = 'sales' | 'products'
type SalesSort = 'profit' | 'margin' | 'revenue'
type ProductSort = 'profit' | 'projected' | 'remaining'

interface PeriodOption {
  value: Period
  label: string
}

// ── Composables ─────────────────────────────────────────────────────────────

const toast = useToast()
const router = useRouter()

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
const analyticsView = ref<AnalyticsView>('sales')
const salesSort = ref<SalesSort>('profit')
const productSort = ref<ProductSort>('profit')
const salesExpanded = ref(false)
const productsExpanded = ref(false)
const debtExpanded = ref(false)
const expandedSaleId = ref<number | null>(null)
const expandedProductId = ref<number | null>(null)

const loadingSummary = ref(false)
const loadingCashFlow = ref(false)
const loadingDebt = ref(false)
const loadingAnalytics = ref(false)
const errorSummary = ref<string | null>(null)
const errorCashFlow = ref<string | null>(null)
const loadingParity = ref(false)

// ── Constants ────────────────────────────────────────────────────────────────

const PERIOD_OPTIONS: PeriodOption[] = [
  { value: 'today', label: 'Сегодня' },
  { value: 'week', label: 'Неделя' },
  { value: 'month', label: 'Месяц' },
  { value: 'all', label: 'Весь период' },
  { value: 'custom', label: 'Диапазон' },
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
  const zero = { revenue: 0, profit: 0, cogs: 0, salesCount: 0, salesDays: 0, returns: 0 }

  return summaries.value.reduce((acc, s) => ({
    revenue: acc.revenue + parseFloat(s.net_sales),
    profit: acc.profit + parseFloat(s.gross_profit),
    cogs: acc.cogs + parseFloat(s.total_cogs),
    salesCount: acc.salesCount + Number(s.total_sales || 0),
    salesDays: acc.salesDays + (Number(s.total_sales || 0) > 0 ? 1 : 0),
    returns: acc.returns + parseFloat(s.total_returns),
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

const nativeCashByCurrency = computed(() => {
  const totals = new Map<string, number>()
  for (const account of cashAccounts.value) {
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
  () => PERIOD_OPTIONS.find((o) => o.value === period.value)?.label ?? '',
)
const periodLabelLower = computed(() => selectedPeriodLabel.value.toLowerCase())
const overallMargin = computed(() => (
  metrics.value.revenue > 0
    ? (metrics.value.profit / metrics.value.revenue) * 100
    : 0
))

const salesProfitabilityTotals = computed(() => {
  return salesProfitability.value.reduce((acc, sale) => ({
    revenue: acc.revenue + parseFloat(sale.revenue || '0'),
    cogs: acc.cogs + parseFloat(sale.cogs || '0'),
    grossProfit: acc.grossProfit + parseFloat(sale.gross_profit || '0'),
    investorProfit: acc.investorProfit + parseFloat(sale.investor_profit || '0'),
    businessProfit: acc.businessProfit + parseFloat(sale.business_profit || '0'),
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
    revenue: acc.revenue + parseFloat(product.revenue || '0'),
    grossProfit: acc.grossProfit + parseFloat(product.gross_profit || '0'),
    remainingLandedCost: acc.remainingLandedCost + parseFloat(product.remaining_landed_cost || '0'),
    projectedRevenue: acc.projectedRevenue + parseFloat(product.projected_revenue || '0'),
    projectedGrossProfit: acc.projectedGrossProfit + parseFloat(product.projected_gross_profit || '0'),
    projectedInvestorProfit: acc.projectedInvestorProfit + parseFloat(product.projected_investor_profit || '0'),
    projectedBusinessProfit: acc.projectedBusinessProfit + parseFloat(product.projected_business_profit || '0'),
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

const salesProfitabilitySorted = computed(() => {
  return [...salesProfitability.value].sort((left, right) => {
    if (salesSort.value === 'margin') {
      return parseFloat(right.margin_percent || '0') - parseFloat(left.margin_percent || '0')
    }
    if (salesSort.value === 'revenue') {
      return parseFloat(right.revenue || '0') - parseFloat(left.revenue || '0')
    }
    return parseFloat(right.gross_profit || '0') - parseFloat(left.gross_profit || '0')
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
      return parseFloat(right.projected_gross_profit || '0') - parseFloat(left.projected_gross_profit || '0')
    }
    if (productSort.value === 'remaining') {
      return parseFloat(right.remaining_landed_cost || '0') - parseFloat(left.remaining_landed_cost || '0')
    }
    return parseFloat(right.gross_profit || '0') - parseFloat(left.gross_profit || '0')
  })
})

const visibleProductProfitability = computed(() =>
  productsExpanded.value
    ? productProfitabilitySorted.value
    : productProfitabilitySorted.value.slice(0, ANALYTICS_PREVIEW_LIMIT),
)

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatPercent(value: string | number): string {
  const numeric = typeof value === 'number' ? value : parseFloat(value)
  if (!Number.isFinite(numeric)) return '0.00%'
  return `${numeric.toFixed(2)}%`
}

function setSalesSort(next: SalesSort): void {
  salesSort.value = next
  expandedSaleId.value = null
}

function setProductSort(next: ProductSort): void {
  productSort.value = next
  expandedProductId.value = null
}

function setAnalyticsView(next: AnalyticsView): void {
  analyticsView.value = next
  expandedSaleId.value = null
  expandedProductId.value = null
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

function paymentMethodsLabel(methods: string[]): string {
  return methods.length ? methods.join(', ') : 'Без метода оплаты'
}

// ── Data loading ─────────────────────────────────────────────────────────────

async function loadSummary(): Promise<void> {
  loadingSummary.value = true
  errorSummary.value = null
  try {
    const range = getDateRange(period.value)
    summaries.value = await fetchDailySummaries(range)
  } catch (err: unknown) {
    errorSummary.value = err instanceof Error ? err.message : 'Ошибка загрузки'
    toast.error('Не удалось загрузить данные отчёта')
  } finally {
    loadingSummary.value = false
  }
}

async function loadCashFlow(): Promise<void> {
  loadingCashFlow.value = true
  try {
    const range = getDateRange(period.value)
    cashFlow.value = await fetchCashFlow(range)
  } catch {
    toast.error('Не удалось загрузить движение наличных')
  } finally {
    loadingCashFlow.value = false
  }
}

async function loadDebt(): Promise<void> {
  loadingDebt.value = true
  try {
    debtItems.value = await fetchDebtSummary()
  } catch {
    // Non-critical — fail silently in the debt section
    debtItems.value = []
  } finally {
    loadingDebt.value = false
  }
}

async function loadParity(): Promise<void> {
  loadingParity.value = true
  try {
    const [payables, stock, trial, cash] = await Promise.all([
      fetchPayablesSummary(),
      fetchStockSummary(),
      fetchTrialBalance(),
      fetchCashAccounts(),
    ])
    payablesItems.value = payables
    stockItems.value = stock
    trialBalance.value = trial.map((line) => ({
      code: String(line.account_code || (line as unknown as { code?: string }).code || ''),
      balance: String(line.balance ?? '0'),
    }))
    cashAccounts.value = cash
  } catch {
    // Non-critical for dashboard rendering.
    payablesItems.value = []
    stockItems.value = []
    trialBalance.value = []
    cashAccounts.value = []
  } finally {
    loadingParity.value = false
  }
}

async function loadAnalytics(): Promise<void> {
  loadingAnalytics.value = true
  try {
    const range = getDateRange(period.value)
    const [salesRows, productRows] = await Promise.all([
      fetchSalesProfitability(range),
      fetchProductProfitability(range),
    ])
    salesProfitability.value = salesRows
    productProfitability.value = productRows
  } catch {
    salesProfitability.value = []
    productProfitability.value = []
  } finally {
    loadingAnalytics.value = false
  }
}

async function loadAll(): Promise<void> {
  await Promise.all([loadSummary(), loadCashFlow(), loadDebt(), loadParity(), loadAnalytics()])
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
  await Promise.all([loadSummary(), loadCashFlow(), loadAnalytics()])
}

async function applyCustomRange(): Promise<void> {
  if (period.value !== 'custom') {
    return
  }
  await Promise.all([loadSummary(), loadCashFlow(), loadAnalytics()])
}

onMounted(loadAll)

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
</script>

<template>
  <div class="reports-page">

    <!-- ── Header ─────────────────────────────────────────────── -->
    <header class="page-header">
      <h1 class="page-title">Отчёты</h1>

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
              {{ opt.label }}
            </li>
          </ul>
        </Transition>
      </div>
    </header>

    <section v-if="period === 'custom'" class="custom-range">
      <div class="custom-range-fields">
        <label class="custom-range-label">
          <span>С</span>
          <input v-model="customDateFrom" class="custom-range-input" type="date" />
        </label>
        <label class="custom-range-label">
          <span>По</span>
          <input v-model="customDateTo" class="custom-range-input" type="date" />
        </label>
      </div>
      <button class="custom-range-apply" type="button" @click="applyCustomRange">
        Применить
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
        <button class="btn-retry" @click="loadSummary">Повторить</button>
      </div>

      <template v-else>
        <section class="overview-panel">
          <div class="overview-head">
            <div class="overview-copy">
              <span class="overview-kicker">Финансовый обзор</span>
              <h2 class="overview-title">{{ selectedPeriodLabel }}</h2>
              <p class="overview-note">
                Исторический эквивалент UZS для P&amp;L и cash flow. Валютные остатки показаны отдельно, чтобы не смешивать курсовую картину.
              </p>
            </div>

            <div class="overview-actions">
              <button class="action-pill" type="button" @click="openCurrencyExchange">
                Обмен валют
              </button>
              <button class="action-pill" type="button" @click="openReconciliation">
                Сверка Excel
              </button>
            </div>
          </div>

          <div class="overview-grid">
            <article class="overview-primary">
              <span class="metric-label">Выручка</span>
              <strong class="overview-primary-value tabular-nums">{{ formatPrice(metrics.revenue) }}</strong>
              <div class="overview-primary-meta">
                <span>{{ metrics.salesCount }} продаж</span>
                <span>{{ metrics.salesDays }} дней с продажами</span>
                <span>Возвраты {{ formatPrice(metrics.returns) }}</span>
              </div>
            </article>

            <article class="metric-tile metric-tile--profit">
              <span class="metric-label">Валовая прибыль</span>
              <strong class="metric-value tabular-nums">{{ formatPrice(metrics.profit) }}</strong>
              <span class="metric-note">Себестоимость {{ formatPrice(metrics.cogs) }}</span>
            </article>

            <article class="metric-tile" :class="cashFlowTotals.net < 0 ? 'metric-tile--danger' : 'metric-tile--brand'">
              <span class="metric-label">Чистый поток</span>
              <strong class="metric-value tabular-nums">
                {{ cashFlowTotals.net >= 0 ? '+' : '' }}{{ formatPrice(cashFlowTotals.net) }}
              </strong>
              <span class="metric-note">Приход {{ formatPrice(cashFlowTotals.inflows) }} · расход {{ formatPrice(cashFlowTotals.outflows) }}</span>
            </article>

            <article class="metric-tile">
              <span class="metric-label">Касса и банк</span>
              <strong class="metric-value tabular-nums">{{ formatPrice(cashBalance) }}</strong>
              <span class="metric-note">Доступный cash в UZS-эквиваленте</span>
            </article>

            <article class="metric-tile">
              <span class="metric-label">Маржа</span>
              <strong class="metric-value tabular-nums">{{ formatPercent(overallMargin) }}</strong>
              <span class="metric-note">По выручке за {{ periodLabelLower }}</span>
            </article>

            <article class="metric-tile">
              <span class="metric-label">Склад</span>
              <strong class="metric-value tabular-nums">{{ formatPrice(inventoryTotals.value) }}</strong>
              <span class="metric-note">{{ inventoryTotals.qty }} шт. на остатке</span>
            </article>
          </div>

          <div class="overview-footer">
            <span class="overview-footer-label">Контрольные метрики</span>
            <div class="inline-chip-list">
              <span class="inline-chip">Дебиторка {{ formatPrice(totalDebt) }}</span>
              <span class="inline-chip">Кредиторка {{ formatPrice(totalPayables) }}</span>
              <span class="inline-chip">Возвраты {{ formatPrice(metrics.returns) }}</span>
              <span v-if="loadingParity" class="inline-chip">Обновляю остатки...</span>
            </div>
            <div v-if="nativeCashByCurrency.length" class="inline-chip-list">
              <span
                v-for="item in nativeCashByCurrency"
                :key="item.currency"
                class="inline-chip inline-chip--muted"
              >
                {{ formatPrice(item.amount, item.currency) }}
              </span>
            </div>
          </div>
        </section>

        <section class="workspace-board">
          <div class="workspace-head">
            <div>
              <h2 class="workspace-title">Деньги и обязательства</h2>
              <p class="workspace-note">Один экран для cash flow, валютных остатков, долгов и складского давления на оборот.</p>
            </div>
          </div>

          <div class="money-layout">
            <article class="workspace-card">
              <div class="card-head">
                <div>
                  <span class="card-kicker">Поток</span>
                  <h3 class="card-title">Движение наличных</h3>
                </div>
                <span class="status-chip" :class="cashFlowTotals.net < 0 ? 'status-chip--danger' : 'status-chip--positive'">
                  {{ cashFlowTotals.net < 0 ? 'Отток' : 'Приток' }}
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
                    <span class="money-label">Приход</span>
                    <span class="money-caption">Деньги вошли в кассу и счета</span>
                  </div>
                  <strong class="money-value money-value--in tabular-nums">{{ formatPrice(cashFlowTotals.inflows) }}</strong>
                </div>

                <div class="money-row">
                  <div class="money-icon money-icon--out">
                    <ArrowUpCircle :size="18" :stroke-width="1.75" />
                  </div>
                  <div class="money-meta">
                    <span class="money-label">Расход</span>
                    <span class="money-caption">Платежи, закупки и прочие списания</span>
                  </div>
                  <strong class="money-value money-value--out tabular-nums">{{ formatPrice(cashFlowTotals.outflows) }}</strong>
                </div>

                <div class="money-divider" />

                <div class="money-row money-row--total">
                  <div class="money-meta">
                    <span class="money-label">Чистый поток</span>
                    <span class="money-caption">Итог за {{ periodLabelLower }}</span>
                  </div>
                  <strong
                    class="money-value money-value--total tabular-nums"
                    :class="signClass(cashFlowTotals.net)"
                  >
                    <TrendingUp v-if="cashFlowTotals.net >= 0" :size="14" :stroke-width="2" />
                    <TrendingDown v-else :size="14" :stroke-width="2" />
                    {{ cashFlowTotals.net >= 0 ? '+' : '' }}{{ formatPrice(cashFlowTotals.net) }}
                  </strong>
                </div>
              </div>

              <div v-if="nativeCashByCurrency.length" class="card-foot">
                <span class="card-caption">Нативные остатки по валютам</span>
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
                  <span class="card-kicker">Риски</span>
                  <h3 class="card-title">Обязательства и давление на оборот</h3>
                </div>
              </div>

              <div class="obligation-grid">
                <div class="obligation-tile">
                  <span class="metric-label">Дебиторка</span>
                  <strong class="metric-value tabular-nums">{{ formatPrice(totalDebt) }}</strong>
                </div>
                <div class="obligation-tile">
                  <span class="metric-label">Кредиторка</span>
                  <strong class="metric-value tabular-nums">{{ formatPrice(totalPayables) }}</strong>
                </div>
                <div class="obligation-tile">
                  <span class="metric-label">Склад по себестоимости</span>
                  <strong class="metric-value tabular-nums">{{ formatPrice(inventoryTotals.value) }}</strong>
                </div>
                <div class="obligation-tile">
                  <span class="metric-label">Остаток в штуках</span>
                  <strong class="metric-value tabular-nums">{{ inventoryTotals.qty }}</strong>
                </div>
              </div>

              <div class="divider-line" />

              <div class="list-block">
                <div class="list-head">
                  <span class="card-caption">Топ должников</span>
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
                          {{ debtExpanded ? (debtor.phone || 'Без номера') : 'Покупатель' }}
                        </span>
                      </div>
                      <strong class="debtor-amount tabular-nums">{{ formatPrice(debtor.outstanding_balance) }}</strong>
                    </div>
                  </div>

                  <button
                    v-if="hasMoreDebtors"
                    type="button"
                    class="expand-btn expand-btn--soft"
                    @click="toggleDebtExpanded"
                  >
                    {{ debtExpanded ? 'Свернуть список' : `Показать ещё ${hiddenDebtorsCount}` }}
                  </button>
                </template>

                <div v-else class="empty-inline">
                  <ShoppingCart :size="18" :stroke-width="1.5" />
                  <span>Нет задолженностей покупателей</span>
                </div>
              </div>
            </article>
          </div>
        </section>

        <section class="workspace-board">
          <div class="workspace-head workspace-head--analytics">
            <div>
              <h2 class="workspace-title">Прибыльность</h2>
              <p class="workspace-note">Owner-срез по продажам и товарам без лишнего шума. Сначала итог, затем компактный список лидеров.</p>
            </div>

            <div class="analytics-switch" role="tablist" aria-label="Тип прибыльности">
              <button
                type="button"
                class="analytics-switch-btn"
                :class="{ active: analyticsView === 'sales' }"
                @click="setAnalyticsView('sales')"
              >
                Продажи
              </button>
              <button
                type="button"
                class="analytics-switch-btn"
                :class="{ active: analyticsView === 'products' }"
                @click="setAnalyticsView('products')"
              >
                Товары
              </button>
            </div>
          </div>

          <p v-if="loadingAnalytics" class="workspace-note">Собираю аналитический срез...</p>

          <template v-else-if="analyticsView === 'sales' ? salesProfitability.length : productProfitability.length">
            <div class="summary-strip">
              <template v-if="analyticsView === 'sales'">
                <div class="summary-card summary-card--primary">
                  <span class="metric-label">Валовая прибыль</span>
                  <strong class="metric-value tabular-nums">{{ formatPrice(salesProfitabilityTotals.grossProfit) }}</strong>
                  <span class="metric-note">
                    Маржа {{
                      formatPercent(
                        salesProfitabilityTotals.revenue > 0
                          ? (salesProfitabilityTotals.grossProfit / salesProfitabilityTotals.revenue) * 100
                          : 0,
                      )
                    }}
                  </span>
                </div>
                <div class="summary-card">
                  <span class="metric-label">Выручка</span>
                  <strong class="metric-value tabular-nums">{{ formatPrice(salesProfitabilityTotals.revenue) }}</strong>
                  <span class="metric-note">Себестоимость {{ formatPrice(salesProfitabilityTotals.cogs) }}</span>
                </div>
                <div class="summary-support">
                  <span class="inline-chip inline-chip--muted">Инвестор {{ formatPrice(salesProfitabilityTotals.investorProfit) }}</span>
                  <span class="inline-chip inline-chip--muted">Бизнес {{ formatPrice(salesProfitabilityTotals.businessProfit) }}</span>
                  <span class="inline-chip inline-chip--muted">{{ salesProfitabilityTotals.lineCount }} строк</span>
                  <span class="inline-chip inline-chip--muted">{{ salesProfitabilityTotals.quantitySold }} шт.</span>
                </div>
              </template>

              <template v-else>
                <div class="summary-card summary-card--primary">
                  <span class="metric-label">Факт. прибыль</span>
                  <strong class="metric-value tabular-nums">{{ formatPrice(productProfitabilityTotals.grossProfit) }}</strong>
                </div>
                <div class="summary-card">
                  <span class="metric-label">Прогноз прибыли</span>
                  <strong class="metric-value tabular-nums">{{ formatPrice(productProfitabilityTotals.projectedGrossProfit) }}</strong>
                </div>
                <div class="summary-support">
                  <span class="inline-chip inline-chip--muted">Продажи {{ formatPrice(productProfitabilityTotals.revenue) }}</span>
                  <span class="inline-chip inline-chip--muted">Остаток {{ formatPrice(productProfitabilityTotals.remainingLandedCost) }}</span>
                  <span class="inline-chip inline-chip--muted">{{ productProfitabilityTotals.remainingQuantity }} шт. в остатке</span>
                </div>
              </template>
            </div>

            <div class="toolbar-row">
              <div
                v-if="analyticsView === 'sales'"
                class="segment-control"
                role="tablist"
                aria-label="Сортировка продаж"
              >
                <button type="button" class="segment-btn" :class="{ active: salesSort === 'profit' }" @click="setSalesSort('profit')">
                  По прибыли
                </button>
                <button type="button" class="segment-btn" :class="{ active: salesSort === 'margin' }" @click="setSalesSort('margin')">
                  По марже
                </button>
                <button type="button" class="segment-btn" :class="{ active: salesSort === 'revenue' }" @click="setSalesSort('revenue')">
                  По выручке
                </button>
              </div>

              <div
                v-else
                class="segment-control"
                role="tablist"
                aria-label="Сортировка товаров"
              >
                <button type="button" class="segment-btn" :class="{ active: productSort === 'profit' }" @click="setProductSort('profit')">
                  По прибыли
                </button>
                <button type="button" class="segment-btn" :class="{ active: productSort === 'projected' }" @click="setProductSort('projected')">
                  По прогнозу
                </button>
                <button type="button" class="segment-btn" :class="{ active: productSort === 'remaining' }" @click="setProductSort('remaining')">
                  По остатку
                </button>
              </div>

              <span class="workspace-note">
                {{ analyticsView === 'sales'
                  ? `${salesProfitabilitySorted.length} продаж в срезе · детали по нажатию`
                  : `${productProfitabilitySorted.length} товаров в срезе · детали по нажатию`
                }}
              </span>
            </div>

            <div class="analytics-table">
              <div class="analytics-table-note">
                <span>{{ analyticsView === 'sales' ? 'Лидеры по выбранной сортировке' : 'Товары-лидеры по выбранной сортировке' }}</span>
                <span>Детали скрыты до открытия строки</span>
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
                        <strong class="analytics-title">Продажа #{{ sale.sale_id }}</strong>
                        <span class="analytics-badge">{{ sale.line_count }} строк</span>
                      </div>
                      <span class="analytics-meta">{{ formatDateTime(sale.date) }} · {{ sale.location_name }}</span>
                      <span class="analytics-meta">{{ sale.quantity_sold }} шт. · {{ sale.customer_name || 'Без клиента' }}</span>
                    </div>
                    <div class="analytics-side">
                      <strong class="analytics-amount tabular-nums">{{ formatPrice(sale.gross_profit) }}</strong>
                      <span class="analytics-side-meta">
                        <span class="analytics-trend">Маржа {{ formatPercent(sale.margin_percent) }}</span>
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
                    <span class="detail-chip">Выручка {{ formatPrice(sale.revenue) }}</span>
                    <span class="detail-chip">Себестоимость {{ formatPrice(sale.cogs) }}</span>
                    <span class="detail-chip">Инвестор {{ formatPrice(sale.investor_profit) }}</span>
                    <span class="detail-chip">Бизнес {{ formatPrice(sale.business_profit) }}</span>
                    <span class="detail-chip">{{ paymentMethodsLabel(sale.payment_methods) }}</span>
                  </div>
                </article>
              </template>

              <template v-else>
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
                        <span class="analytics-badge">{{ product.quantity_sold }} продано</span>
                      </div>
                      <span class="analytics-meta">Остаток {{ product.remaining_quantity }} шт.</span>
                      <span class="analytics-meta">Цена {{ formatPrice(product.current_unit_price) }}</span>
                    </div>
                    <div class="analytics-side">
                      <strong class="analytics-amount tabular-nums">{{ formatPrice(product.gross_profit) }}</strong>
                      <span class="analytics-side-meta">
                        <span class="analytics-trend">Маржа {{ formatPercent(product.margin_percent) }}</span>
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
                    <span class="detail-chip">Продажи {{ formatPrice(product.revenue) }}</span>
                    <span class="detail-chip">Факт {{ formatPrice(product.gross_profit) }}</span>
                    <span class="detail-chip">Остаток {{ formatPrice(product.remaining_landed_cost) }}</span>
                    <span class="detail-chip">Прогноз {{ formatPrice(product.projected_gross_profit) }}</span>
                    <span class="detail-chip">Инвестор {{ formatPrice(product.projected_investor_profit) }}</span>
                    <span class="detail-chip">Бизнес {{ formatPrice(product.projected_business_profit) }}</span>
                  </div>
                </article>
              </template>
            </div>

            <button
              v-if="analyticsView === 'sales'
                ? salesProfitabilitySorted.length > ANALYTICS_PREVIEW_LIMIT
                : productProfitabilitySorted.length > ANALYTICS_PREVIEW_LIMIT"
              type="button"
              class="expand-btn"
              @click="analyticsView === 'sales' ? (salesExpanded = !salesExpanded) : (productsExpanded = !productsExpanded)"
            >
              {{
                analyticsView === 'sales'
                  ? (
                    salesExpanded
                      ? 'Свернуть продажи'
                      : `Показать ещё ${salesProfitabilitySorted.length - visibleSalesProfitability.length} продаж`
                  )
                  : (
                    productsExpanded
                      ? 'Свернуть товары'
                      : `Показать ещё ${productProfitabilitySorted.length - visibleProductProfitability.length} товаров`
                  )
              }}
            </button>
          </template>

          <p v-else class="workspace-note">
            {{ analyticsView === 'sales'
              ? 'За выбранный период завершённых продаж нет.'
              : 'Пока нет данных по товарам.'
            }}
          </p>
        </section>
      </template>
    </div>
  </div>
</template>

<style scoped>
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
  gap: var(--space-4);
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

.overview-title {
  font-size: clamp(1.4rem, 3vw, 2rem);
  line-height: 1.05;
  margin-top: var(--space-1);
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

.workspace-title {
  font-size: var(--text-lg);
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
  min-height: 30px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-full);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-subtle);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
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

  .overview-grid,
  .obligation-grid,
  .summary-strip,
  .skeleton-grid {
    grid-template-columns: 1fr;
  }

  .analytics-switch,
  .segment-control {
    width: 100%;
    overflow-x: auto;
    flex-wrap: nowrap;
    padding-bottom: 2px;
  }

  .analytics-switch-btn,
  .segment-btn,
  .inline-chip,
  .detail-chip {
    white-space: nowrap;
  }

  .analytics-table-note {
    flex-direction: column;
    align-items: flex-start;
  }

  .analytics-toggle {
    grid-template-columns: 1fr;
  }

  .analytics-side {
    justify-items: start;
    text-align: left;
  }

  .analytics-details {
    grid-template-columns: 1fr;
  }

  .money-row,
  .compact-debt-row {
    grid-template-columns: 32px minmax(0, 1fr) auto;
    gap: var(--space-2);
  }

  .money-row--total {
    grid-template-columns: 1fr;
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
