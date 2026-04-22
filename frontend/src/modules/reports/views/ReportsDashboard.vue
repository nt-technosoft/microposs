<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { TrendingUp, TrendingDown, ShoppingCart, RotateCcw, ArrowDownCircle, ArrowUpCircle, ChevronDown } from 'lucide-vue-next'
import { fetchDailySummaries, fetchCashFlow, fetchTrialBalance, fetchCashAccounts, type DailySummary, type CashFlowItem, type CashAccountRecord } from '@/api/finance'
import { fetchDebtSummary, type DebtSummaryItem } from '@/api/customers'
import { fetchPayablesSummary, type PayablesSummaryItem } from '@/api/suppliers'
import { fetchStockSummary, type StockSummaryItem } from '@/api/inventory'
import { useToast } from '@/composables/useToast'
import { formatPrice } from '@/utils/currency'

// ── Types ───────────────────────────────────────────────────────────────────

type Period = 'today' | 'week' | 'month' | 'all' | 'custom'

interface PeriodOption {
  value: Period
  label: string
}

// ── Composables ─────────────────────────────────────────────────────────────

const toast = useToast()
const router = useRouter()

// ── State ────────────────────────────────────────────────────────────────────

const period = ref<Period>('today')
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

const loadingSummary = ref(false)
const loadingCashFlow = ref(false)
const loadingDebt = ref(false)
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
    value: acc.value,
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

const topDebtors = computed(() =>
  [...debtItems.value]
    .sort((a, b) => parseFloat(b.outstanding_balance) - parseFloat(a.outstanding_balance))
    .slice(0, 5),
)

const selectedPeriodLabel = computed(
  () => PERIOD_OPTIONS.find((o) => o.value === period.value)?.label ?? '',
)
const periodLabelLower = computed(() => selectedPeriodLabel.value.toLowerCase())

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

async function loadAll(): Promise<void> {
  await Promise.all([loadSummary(), loadCashFlow(), loadDebt(), loadParity()])
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
  await Promise.all([loadSummary(), loadCashFlow()])
}

async function applyCustomRange(): Promise<void> {
  if (period.value !== 'custom') {
    return
  }
  await Promise.all([loadSummary(), loadCashFlow()])
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
      <p class="context-note">
        P&amp;L, Cash Flow и карточки в отчётах ниже показаны в историческом эквиваленте UZS. Раздельные остатки денег по валютам вынесены отдельно.
      </p>

      <!-- ── Loading skeletons ──────────────────────────────── -->
      <template v-if="loadingSummary && summaries.length === 0">
        <div class="skeleton-hero" />
        <div class="grid-2">
          <div class="skeleton-card-sm" />
          <div class="skeleton-card-sm" />
          <div class="skeleton-card-sm" />
          <div class="skeleton-card-sm" />
        </div>
      </template>

      <!-- ── Error state ────────────────────────────────────── -->
      <div v-else-if="errorSummary && summaries.length === 0" class="error-box">
        <p class="error-text">{{ errorSummary }}</p>
        <button class="btn-retry" @click="loadSummary">Повторить</button>
      </div>

      <!-- ── Metrics ───────────────────────────────────────── -->
      <template v-else>

        <!-- Hero revenue card -->
        <div class="stat-card stat-card--hero">
          <div class="stat-accent" />
          <span class="stat-label">Выручка за период</span>
          <span class="stat-value stat-value--revenue tabular-nums">
            {{ formatPrice(metrics.revenue) }}
          </span>
          <div class="stat-sub">
            <TrendingUp :size="14" :stroke-width="2" />
            <span>за {{ periodLabelLower }}</span>
          </div>
        </div>

        <!-- 2-column grid -->
        <div class="grid-2">
          <!-- Profit -->
          <div class="stat-card stat-card--sm">
            <div class="stat-accent stat-accent--success" />
            <span class="stat-label">Прибыль</span>
            <span class="stat-value stat-value--profit tabular-nums">
              {{ formatPrice(metrics.profit) }}
            </span>
          </div>

          <!-- COGS -->
          <div class="stat-card stat-card--sm">
            <div class="stat-accent stat-accent--muted" />
            <span class="stat-label">Расходы</span>
            <span class="stat-value stat-value--cogs tabular-nums">
              {{ formatPrice(metrics.cogs) }}
            </span>
          </div>

          <!-- Sales count -->
          <div class="stat-card stat-card--sm">
            <div class="stat-accent stat-accent--info" />
            <span class="stat-label">Дней с продажами</span>
            <span class="stat-value tabular-nums">
              {{ metrics.salesDays }} дн.
            </span>
          </div>

          <!-- Returns -->
          <div class="stat-card stat-card--sm">
            <div class="stat-accent stat-accent--warning" />
            <span class="stat-label">Возвраты</span>
            <span class="stat-value stat-value--returns tabular-nums">
              {{ formatPrice(metrics.returns) }}
            </span>
          </div>
        </div>

        <!-- ── Операционные сводки ───────────────────────────── -->
        <section class="section">
          <div class="section-head">
            <h2 class="section-title">Операционные срезы</h2>
            <div class="section-actions">
              <button class="link-btn" type="button" @click="openCurrencyExchange">
                Обмен валют
              </button>
              <button class="link-btn" type="button" @click="openReconciliation">
                Сверка Excel
              </button>
            </div>
          </div>

          <div class="grid-2">
            <div class="stat-card stat-card--sm">
              <span class="stat-label">Касса и банк (UZS экв.)</span>
              <span class="stat-value tabular-nums">{{ formatPrice(cashBalance) }}</span>
            </div>
            <div class="stat-card stat-card--sm">
              <span class="stat-label">Склад (шт.)</span>
              <span class="stat-value tabular-nums">{{ inventoryTotals.qty }}</span>
            </div>
            <div class="stat-card stat-card--sm">
              <span class="stat-label">Дебиторка (AR)</span>
              <span class="stat-value tabular-nums">{{ formatPrice(totalDebt) }}</span>
            </div>
            <div class="stat-card stat-card--sm">
              <span class="stat-label">Кредиторка (AP)</span>
              <span class="stat-value tabular-nums">{{ formatPrice(totalPayables) }}</span>
            </div>
          </div>

          <div v-if="nativeCashByCurrency.length" class="native-balances">
            <span class="section-note">Денежные счета по валютам</span>
            <div class="native-balance-list">
              <span
                v-for="item in nativeCashByCurrency"
                :key="item.currency"
                class="native-balance-chip"
              >
                {{ formatPrice(item.amount, item.currency) }}
              </span>
            </div>
          </div>

          <p v-if="loadingParity" class="section-note">Обновляю операционные метрики...</p>
          <p v-else class="section-note">
            Стоимость остатков на складе:
            <strong class="tabular-nums">{{ formatPrice(inventoryTotals.value) }}</strong>
          </p>
        </section>

        <!-- ── Cash flow section ───────────────────────────── -->
        <section class="section">
          <h2 class="section-title">Движение наличных</h2>

          <div v-if="loadingCashFlow" class="cf-skeleton">
            <div class="skeleton-line skeleton-line--md" />
            <div class="skeleton-line skeleton-line--sm" />
            <div class="skeleton-line skeleton-line--md" />
            <div class="skeleton-line skeleton-line--sm" />
          </div>

          <div v-else class="cf-card">
            <div class="cf-row">
              <div class="cf-icon-wrap cf-icon-wrap--in">
                <ArrowDownCircle :size="18" :stroke-width="1.75" />
              </div>
              <span class="cf-label">Приход</span>
              <span class="cf-amount cf-amount--in tabular-nums">
                {{ formatPrice(cashFlowTotals.inflows) }}
              </span>
            </div>

            <div class="cf-row">
              <div class="cf-icon-wrap cf-icon-wrap--out">
                <ArrowUpCircle :size="18" :stroke-width="1.75" />
              </div>
              <span class="cf-label">Расходы</span>
              <span class="cf-amount cf-amount--out tabular-nums">
                {{ formatPrice(cashFlowTotals.outflows) }}
              </span>
            </div>

            <div class="cf-divider" />

            <div class="cf-row cf-row--total">
              <span class="cf-label cf-label--total">Чистый поток</span>
              <span
                class="cf-amount cf-amount--net tabular-nums"
                :class="signClass(cashFlowTotals.net)"
              >
                <TrendingUp v-if="cashFlowTotals.net >= 0" :size="14" :stroke-width="2" />
                <TrendingDown v-else :size="14" :stroke-width="2" />
                {{ cashFlowTotals.net >= 0 ? '+' : '' }}{{ formatPrice(cashFlowTotals.net) }}
              </span>
            </div>
          </div>
        </section>

        <!-- ── AR (Debts) section ──────────────────────────── -->
        <section class="section">
          <h2 class="section-title">Долги покупателей</h2>

          <div v-if="loadingDebt" class="debt-skeleton">
            <div v-for="n in 3" :key="n" class="skeleton-row" />
          </div>

          <template v-else-if="debtItems.length > 0">
            <div class="debt-total-banner">
              <span class="debt-total-label">Всего долгов</span>
              <span class="debt-total-amount tabular-nums">{{ formatPrice(totalDebt) }}</span>
            </div>

            <div class="debt-list">
              <div
                v-for="debtor in topDebtors"
                :key="debtor.id"
                class="debt-row"
              >
                <div class="debtor-avatar" aria-hidden="true">
                  {{ debtor.name.charAt(0).toUpperCase() }}
                </div>
                <div class="debtor-info">
                  <span class="debtor-name">{{ debtor.name }}</span>
                  <span class="debtor-phone">{{ debtor.phone }}</span>
                </div>
                <span class="debtor-amount tabular-nums">
                  {{ formatPrice(debtor.outstanding_balance) }}
                </span>
              </div>
            </div>
          </template>

          <div v-else class="debt-empty">
            <ShoppingCart :size="28" :stroke-width="1.5" class="debt-empty-icon" />
            <p class="debt-empty-text">Нет задолженностей</p>
          </div>
        </section>

      </template>
    </div>
  </div>
</template>

<style scoped>
/* ── Layout ───────────────────────────────────────────────────────────────── */

.reports-page {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  background: var(--color-bg-primary);
  padding-bottom: calc(var(--bottom-nav-height) + var(--space-6));
}

/* ── Header ──────────────────────────────────────────────────────────────── */

.page-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4) var(--space-5);
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border-subtle);
}

.page-title {
  font-size: var(--text-xl);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

/* ── Period selector ─────────────────────────────────────────────────────── */

.period-selector {
  position: relative;
}

.period-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-elevated);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-primary);
  transition: background var(--duration-fast) var(--ease-out),
              border-color var(--duration-fast) var(--ease-out);
}

.period-btn:hover,
.period-btn.open {
  background: var(--color-brand-50);
  border-color: var(--color-brand-300);
  color: var(--color-brand-600);
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
  min-width: 120px;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  z-index: var(--z-dropdown);
  overflow: hidden;
  list-style: none;
  padding: var(--space-1) 0;
}

.period-option {
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-out),
              color var(--duration-fast) var(--ease-out);
}

.period-option:hover {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

.period-option.active {
  background: var(--color-brand-50);
  color: var(--color-brand-600);
}

/* ── Custom range ─────────────────────────────────────────────────────────── */

.custom-range {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-5);
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-bg-primary);
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
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.custom-range-input {
  width: 100%;
  min-height: 38px;
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  padding: 0 var(--space-2);
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
}

.custom-range-apply {
  min-height: 38px;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-brand-300);
  border-radius: var(--radius-md);
  background: var(--color-brand-50);
  color: var(--color-brand-700);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

/* ── Content ─────────────────────────────────────────────────────────────── */

.content {
  flex: 1;
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.context-note {
  font-size: var(--text-xs);
  line-height: 1.45;
  color: var(--color-text-secondary);
}

/* ── Stat cards ──────────────────────────────────────────────────────────── */

.stat-card {
  position: relative;
  background: var(--color-bg-elevated);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-subtle);
  box-shadow: var(--shadow-md);
  overflow: hidden;
  padding: var(--space-4) var(--space-4) var(--space-4) calc(var(--space-4) + 3px);
}

.stat-accent {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: var(--color-brand-400);
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
}

.stat-accent--success  { background: var(--color-success); }
.stat-accent--muted    { background: var(--color-text-tertiary); }
.stat-accent--info     { background: var(--color-info); }
.stat-accent--warning  { background: var(--color-warning); }

.stat-card--hero {
  padding: var(--space-5) var(--space-5) var(--space-5) calc(var(--space-5) + 3px);
}

.stat-label {
  display: block;
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: var(--space-1);
}

.stat-value {
  display: block;
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--color-text-primary);
  line-height: var(--leading-tight);
}

.stat-card--sm .stat-value {
  font-size: var(--text-xl);
}

.stat-value--revenue { color: var(--color-brand-600); }
.stat-value--profit  { color: var(--color-success); }
.stat-value--cogs    { color: var(--color-text-secondary); }
.stat-value--returns { color: var(--color-warning); }

.stat-sub {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  margin-top: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

/* ── Grid ────────────────────────────────────────────────────────────────── */

.grid-2 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-3);
}

/* ── Sections ────────────────────────────────────────────────────────────── */

.section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.section-title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.section-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--space-3);
}

.link-btn {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--color-brand-600);
}

.section-note {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.native-balances {
  display: grid;
  gap: var(--space-2);
}

.native-balance-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.native-balance-chip {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-full);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-default);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

/* ── Cash flow card ──────────────────────────────────────────────────────── */

.cf-card {
  background: var(--color-bg-elevated);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-subtle);
  box-shadow: var(--shadow-sm);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.cf-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.cf-row--total {
  padding-top: var(--space-1);
}

.cf-icon-wrap {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.cf-icon-wrap--in {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.cf-icon-wrap--out {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.cf-label {
  flex: 1;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.cf-label--total {
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.cf-amount {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.cf-amount--in  { color: var(--color-success); }
.cf-amount--out { color: var(--color-error); }
.cf-amount--net {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-base);
  font-weight: var(--font-bold);
}

.cf-amount--net.positive { color: var(--color-success); }
.cf-amount--net.negative { color: var(--color-error); }

.cf-divider {
  height: 1px;
  background: var(--color-border-subtle);
}

/* ── Debt section ────────────────────────────────────────────────────────── */

.debt-total-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  background: var(--color-warning-bg);
  border: 1px solid var(--color-accent-200);
  border-radius: var(--radius-md);
}

.debt-total-label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-warning);
}

.debt-total-amount {
  font-size: var(--text-base);
  font-weight: var(--font-bold);
  color: var(--color-warning);
}

.debt-list {
  background: var(--color-bg-elevated);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-subtle);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.debt-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-border-subtle);
}

.debt-row:last-child {
  border-bottom: none;
}

.debtor-avatar {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-full);
  background: var(--color-brand-100);
  color: var(--color-brand-700);
  font-size: var(--text-sm);
  font-weight: var(--font-bold);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.debtor-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.debtor-name {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.debtor-phone {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.debtor-amount {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-error);
  flex-shrink: 0;
}

/* ── Empty / error states ────────────────────────────────────────────────── */

.debt-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-8) var(--space-4);
  text-align: center;
}

.debt-empty-icon {
  color: var(--color-text-tertiary);
}

.debt-empty-text {
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
}

.error-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-12) var(--space-5);
  text-align: center;
}

.error-text {
  font-size: var(--text-sm);
  color: var(--color-error);
}

.btn-retry {
  padding: var(--space-2) var(--space-5);
  border-radius: var(--radius-full);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  transition: background var(--duration-fast) var(--ease-out);
}

.btn-retry:hover {
  background: var(--color-brand-600);
}

/* ── Skeletons ───────────────────────────────────────────────────────────── */

.skeleton-hero {
  height: 96px;
  border-radius: var(--radius-lg);
  background: var(--color-bg-sunken);
  animation: shimmer 1.4s ease-in-out infinite;
}

.skeleton-card-sm {
  height: 80px;
  border-radius: var(--radius-lg);
  background: var(--color-bg-sunken);
  animation: shimmer 1.4s ease-in-out infinite;
}

.skeleton-card-sm:nth-child(2) { animation-delay: 0.1s; }
.skeleton-card-sm:nth-child(3) { animation-delay: 0.2s; }
.skeleton-card-sm:nth-child(4) { animation-delay: 0.3s; }

.cf-skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.skeleton-line {
  border-radius: var(--radius-sm);
  background: var(--color-bg-sunken);
  animation: shimmer 1.4s ease-in-out infinite;
}

.skeleton-line--sm { height: 14px; width: 55%; }
.skeleton-line--md { height: 16px; width: 80%; }

.debt-skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.skeleton-row {
  height: 52px;
  border-radius: var(--radius-md);
  background: var(--color-bg-sunken);
  animation: shimmer 1.4s ease-in-out infinite;
}

@keyframes shimmer {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.5; }
}

/* ── Dropdown transition ─────────────────────────────────────────────────── */

.dropdown-enter-active,
.dropdown-leave-active {
  transition: opacity var(--duration-fast) var(--ease-out),
              transform var(--duration-fast) var(--ease-out);
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

@media (max-width: 640px) {
  .custom-range {
    padding: var(--space-3) var(--space-4);
    align-items: stretch;
    flex-direction: column;
  }

  .custom-range-apply {
    width: 100%;
  }
}

/* ── Reduced motion ──────────────────────────────────────────────────────── */

@media (prefers-reduced-motion: reduce) {
  .skeleton-hero,
  .skeleton-card-sm,
  .skeleton-line,
  .skeleton-row {
    animation: none;
    opacity: 0.6;
  }

  .period-chevron,
  .period-btn,
  .btn-retry {
    transition: none;
  }

  .dropdown-enter-active,
  .dropdown-leave-active {
    transition: none;
  }
}
</style>
