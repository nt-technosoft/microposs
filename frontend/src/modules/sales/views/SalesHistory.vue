<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { SlidersHorizontal, RotateCcw } from 'lucide-vue-next'
import { useSalesStore } from '@/stores/sales'
import { useSessionStore } from '@/stores/session'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { PaymentMethod, SaleStatus } from '@/types/enums'
import type { Sale, SaleLine, SalePayment } from '@/types/models'
import { fetchReturnPreview, type ReturnReason, type ReturnResolution, type SaleReturnPreview } from '@/api/sales'
import { intlLocale } from '@/i18n/format'
import { formatPrice } from '@/utils/currency'

// ── Stores & composables ────────────────────────────────────────────────────

const salesStore = useSalesStore()
const sessionStore = useSessionStore()
const authStore = useAuthStore()
const toast = useToast()
const router = useRouter()
const { t, locale } = useI18n()

// ── Filter state ────────────────────────────────────────────────────────────

type FilterOption = 'all' | 'mixed' | PaymentMethod

interface FilterChip {
  value: FilterOption
  label: string
}

const FILTER_CHIPS = computed<FilterChip[]>(() => [
  { value: 'all', label: t('common.all') },
  { value: PaymentMethod.CASH, label: t('domain.paymentMethod.CASH') },
  { value: PaymentMethod.CARD, label: t('domain.paymentMethod.CARD') },
  { value: PaymentMethod.TRANSFER, label: t('domain.paymentMethod.TRANSFER') },
  { value: PaymentMethod.CREDIT, label: t('domain.paymentMethod.CREDIT') },
  { value: 'mixed', label: t('sales.mixedPayments') },
])

const activeFilter = ref<FilterOption>('all')

// ── Detail sheet state ──────────────────────────────────────────────────────

const detailOpen = ref(false)
const detailLoading = ref(false)
const selectedSale = ref<Sale | null>(null)
const returnOpen = ref(false)
const returnLoading = ref(false)
const returnSubmitting = ref(false)
const returnPreview = ref<SaleReturnPreview | null>(null)
const returnResolution = ref<ReturnResolution>('RESTOCK')
const returnReason = ref<ReturnReason>('CLIENT_REFUSE')
const returnQuantities = ref<Record<number, number>>({})
const returnRefundMethod = ref<PaymentMethod.CASH | PaymentMethod.CARD | PaymentMethod.TRANSFER | 'RECEIVABLE_OFFSET'>(PaymentMethod.CASH)
const returnError = ref('')

// ── Load sales ──────────────────────────────────────────────────────────────

async function loadSales(page = 1): Promise<void> {
  const sessionId = sessionStore.currentSession?.id
  await salesStore.fetchSales({ session: sessionId, page })
}

async function loadMore(): Promise<void> {
  const nextPage = salesStore.page + 1
  await loadSales(nextPage)
}

onMounted(async () => {
  await loadSales(1)
})

watch(() => sessionStore.currentSession?.id ?? null, () => {
  loadSales(1)
})

// ── Filtered sales ──────────────────────────────────────────────────────────

const activeSession = computed(() => sessionStore.currentSession)
const hasActiveSession = computed(() => sessionStore.isOpen && !!activeSession.value)
const canOpenExplanation = computed(() => authStore.isOwner)

function normalizePaymentMethod(method: PaymentMethod | string | null | undefined): string | null {
  if (!method) return null

  const normalized = String(method).toUpperCase()
  if (normalized === PaymentMethod.CASH_LEGACY.toUpperCase()) return PaymentMethod.CASH
  if (normalized === PaymentMethod.CARD_LEGACY.toUpperCase()) return PaymentMethod.CARD
  if (normalized === PaymentMethod.CREDIT_LEGACY.toUpperCase()) return PaymentMethod.CREDIT
  if (normalized === PaymentMethod.TRANSFER) return PaymentMethod.TRANSFER
  if (normalized === PaymentMethod.CASH) return PaymentMethod.CASH
  if (normalized === PaymentMethod.CARD) return PaymentMethod.CARD
  if (normalized === PaymentMethod.CREDIT) return PaymentMethod.CREDIT
  return normalized
}

function salePaymentMethods(sale: Sale): string[] {
  const rawMethods = Array.isArray(sale.payment_methods) && sale.payment_methods.length > 0
    ? sale.payment_methods
    : Array.isArray(sale.payments) && sale.payments.length > 0
      ? sale.payments
        .filter((payment) => payment.role === 'INCOMING')
        .map((payment) => payment.method)
      : sale.payment_method
        ? [sale.payment_method]
        : []

  const methods: string[] = []
  for (const method of rawMethods) {
    const normalized = normalizePaymentMethod(method)
    if (normalized && !methods.includes(normalized)) {
      methods.push(normalized)
    }
  }
  return methods
}

function isMixedPayment(sale: Sale): boolean {
  return salePaymentMethods(sale).length > 1
}

function saleMatchesFilter(sale: Sale, filter: FilterOption): boolean {
  if (filter === 'all') return true
  if (filter === 'mixed') return isMixedPayment(sale)
  return salePaymentMethods(sale).includes(filter)
}

const filteredSales = computed<Sale[]>(() => {
  if (activeFilter.value === 'all') return salesStore.sales
  return salesStore.sales.filter((sale) => saleMatchesFilter(sale, activeFilter.value))
})

// ── Date grouping ───────────────────────────────────────────────────────────

interface SaleGroup {
  label: string
  count: number
  sales: Sale[]
}

const groupedSales = computed<SaleGroup[]>(() => {
  const groups = new Map<string, Sale[]>()

  for (const sale of filteredSales.value) {
    const key = formatDateKey(sale.created_at)
    const existing = groups.get(key)
    if (existing) {
      groups.set(key, [...existing, sale])
    } else {
      groups.set(key, [sale])
    }
  }

  return Array.from(groups.entries()).map(([label, sales]) => ({
    label,
    count: sales.length,
    sales,
  }))
})

function formatDateKey(dateStr: string): string {
  const date = new Date(dateStr)
  const today = new Date()
  const yesterday = new Date()
  yesterday.setDate(today.getDate() - 1)

  if (isSameDay(date, today)) return t('sales.today')
  if (isSameDay(date, yesterday)) return t('sales.yesterday')

  return date.toLocaleDateString(intlLocale(locale.value), {
    day: 'numeric',
    month: 'long',
    year: date.getFullYear() !== today.getFullYear() ? 'numeric' : undefined,
  })
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

// ── Formatting helpers ──────────────────────────────────────────────────────

function formatTime(dateStr: string): string {
  return new Date(dateStr).toLocaleTimeString(intlLocale(locale.value), {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatDateTime(dateStr: string): string {
  return new Date(dateStr).toLocaleString(intlLocale(locale.value), {
    day: 'numeric',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function itemsLabel(sale: Sale): string {
  const hasLines = Array.isArray(sale.lines) && sale.lines.length > 0
  const countFromLines = hasLines ? sale.lines.reduce((sum: number, line: SaleLine) => sum + line.quantity, 0) : 0
  const countFromList = (sale as Sale & { lines_count?: number }).lines_count ?? 0
  const count = hasLines ? countFromLines : countFromList

  return t('sales.itemCount', { count })
}

function paymentLabel(method: PaymentMethod | string | undefined): string {
  const normalized = normalizePaymentMethod(method)
  const map: Record<string, string> = {
    [PaymentMethod.CASH]: t('domain.paymentMethod.CASH'),
    [PaymentMethod.CARD]: t('domain.paymentMethod.CARD'),
    [PaymentMethod.TRANSFER]: t('domain.paymentMethod.TRANSFER'),
    [PaymentMethod.CREDIT]: t('domain.paymentMethod.CREDIT'),
    [PaymentMethod.CASH_LEGACY]: t('domain.paymentMethod.CASH'),
    [PaymentMethod.CARD_LEGACY]: t('domain.paymentMethod.CARD'),
    [PaymentMethod.CREDIT_LEGACY]: t('domain.paymentMethod.CREDIT'),
  }
  if (!normalized) return t('common.notSpecified')
  return map[normalized] ?? normalized
}

function paymentMethodsLabel(methods: string[]): string {
  if (!methods.length) return t('common.notSpecified')
  return methods.map((method) => paymentLabel(method)).join(' + ')
}

function paymentBadgeLabel(sale: Sale): string {
  const methods = salePaymentMethods(sale)
  if (methods.length > 1) return t('sales.mixedPayments')
  return paymentLabel(methods[0])
}

function paymentBadgeClass(sale: Sale): string {
  if (isMixedPayment(sale)) return 'badge-mixed'
  const method = salePaymentMethods(sale)[0]
  return method ? `badge-${method.toLowerCase()}` : 'badge-unknown'
}

function paymentSummaryLabel(sale: Sale): string {
  const methods = salePaymentMethods(sale)
  return paymentMethodsLabel(methods)
}

function incomingPayments(sale: Sale): SalePayment[] {
  return Array.isArray(sale.payments)
    ? sale.payments.filter((payment) => payment.role === 'INCOMING')
    : []
}

function paymentAmountTrace(payment: SalePayment): string {
  const currency = (payment.currency || 'UZS').toUpperCase()
  const amount = formatPrice(payment.amount, currency)
  if (currency === 'UZS') {
    return amount
  }

  const fxRate = Number.parseFloat(payment.fx_rate || '')
  if (Number.isFinite(fxRate) && fxRate > 0) {
    return `${amount} • ${t('finance.rate')} ${fxRate.toFixed(2)}`
  }
  return amount
}

function isReturned(sale: Sale): boolean {
  return sale.status === SaleStatus.RETURNED
}

function isPartiallyReturned(sale: Sale): boolean {
  return sale.status === SaleStatus.PARTIALLY_RETURNED
}

function lineDisplayName(line: SaleLine): string {
  const explicitName = (line as SaleLine & { product_name?: string }).product_name
  if (explicitName && explicitName.trim()) {
    return explicitName
  }

  const variant = line.product_variant
  if (variant && typeof variant === 'object') {
    const attrs = Array.isArray(variant.attribute_values)
      ? variant.attribute_values
        .map((attribute) => attribute.value)
        .filter((value) => Boolean(value && value.trim()))
      : []

    if (attrs.length > 0) {
      return attrs.join(', ')
    }

    if ('product_name' in variant && variant.product_name) {
      return variant.product_name
    }

    if ('id' in variant && variant.id) {
      return t('products.variantFallback', { id: variant.id })
    }
  }

  if (typeof variant === 'number') {
    return t('products.variantFallback', { id: variant })
  }

  return t('products.positionFallback', { id: line.id })
}

function operationTrace(sale: Sale): string {
  const currency = (sale.operation_currency || 'UZS').toUpperCase()
  const opAmount = Number.parseFloat(sale.operation_amount || '')
  const fxRate = Number.parseFloat(sale.fx_rate_snapshot || '')
  const functional = Number.parseFloat(sale.functional_amount_uzs || '')

  if (currency === 'UZS' || !Number.isFinite(opAmount)) {
    return ''
  }

  const opStr = formatPrice(opAmount, currency)
  const fnStr = Number.isFinite(functional) ? formatPrice(functional) : ''
  if (Number.isFinite(fxRate) && fnStr) {
    return `${opStr} • ${t('finance.rate')} ${fxRate.toFixed(2)} • ${fnStr}`
  }
  return fnStr ? `${opStr} • ${fnStr}` : opStr
}

function toNumber(value: string | number | null | undefined): number {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0
  if (typeof value === 'string') {
    const parsed = Number.parseFloat(value)
    return Number.isFinite(parsed) ? parsed : 0
  }
  return 0
}

function formatPercent(value: string | number | null | undefined): string {
  const amount = toNumber(value)
  return `${amount.toLocaleString(intlLocale(locale.value), {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  })}%`
}

function salePurchaseCost(sale: Sale): number {
  if (sale.purchase_cost != null) {
    return toNumber(sale.purchase_cost)
  }
  return sale.lines.reduce(
    (sum, line) => sum + toNumber(line.unit_purchase_price) * Number(line.quantity || 0),
    0,
  )
}

function saleRevenue(sale: Sale): number {
  return toNumber(sale.total_amount)
}

function saleLandedCost(sale: Sale): number {
  if (sale.landed_cost != null) {
    return toNumber(sale.landed_cost)
  }
  return toNumber(sale.total_cogs)
}

function saleGrossProfit(sale: Sale): number {
  if (sale.gross_profit != null) {
    return toNumber(sale.gross_profit)
  }
  return saleRevenue(sale) - saleLandedCost(sale)
}

function saleInvestorProfit(sale: Sale): number {
  return toNumber(sale.investor_profit)
}

function saleBusinessProfit(sale: Sale): number {
  if (sale.business_profit != null) {
    return toNumber(sale.business_profit)
  }
  return saleGrossProfit(sale) - saleInvestorProfit(sale)
}

function saleMarginPercent(sale: Sale): string {
  if (sale.margin_percent != null) {
    return formatPercent(sale.margin_percent)
  }

  const revenue = saleRevenue(sale)
  if (revenue <= 0) {
    return '0%'
  }

  return formatPercent((saleGrossProfit(sale) / revenue) * 100)
}

function sessionMetaLabel(): string {
  if (!activeSession.value) {
    return t('sales.noOpenShiftHistory')
  }
  return `${sessionStore.location?.name || t('sales.salesPoint')} • ${formatDateTime(activeSession.value.opened_at)}`
}

// ── Sale detail ─────────────────────────────────────────────────────────────

async function openDetail(sale: Sale): Promise<void> {
  selectedSale.value = sale
  detailOpen.value = true

  // Fetch full detail (includes all lines) if the stored sale might be partial
  if (!sale.lines || sale.lines.length === 0) {
    detailLoading.value = true
    try {
      await salesStore.fetchSale(sale.id)
      selectedSale.value = salesStore.currentSale
    } catch {
      toast.error(t('sales.saleDetailsFailed'))
    } finally {
      detailLoading.value = false
    }
  }
}

function closeDetail(): void {
  detailOpen.value = false
  selectedSale.value = null
}

function selectedReturnLines() {
  return Object.entries(returnQuantities.value)
    .map(([saleLineId, quantity]) => ({
      sale_line_id: Number(saleLineId),
      quantity: Number(quantity || 0),
    }))
    .filter((line) => line.quantity > 0)
}

function selectedReturnAmountUzs(): number {
  return toNumber(returnPreview.value?.selected.refund_amount_uzs)
}

function preferredRefundPayment() {
  const sale = selectedSale.value
  const amountUzs = selectedReturnAmountUzs()
  const payment = sale ? incomingPayments(sale)[0] : null
  const currency = (payment?.currency || 'UZS').toUpperCase()
  const fxRate = Number.parseFloat(payment?.fx_rate || '1')
  const amount = currency === 'UZS'
    ? amountUzs
    : fxRate > 0
      ? amountUzs / fxRate
      : 0
  return {
    method: returnRefundMethod.value,
    amount: amount.toFixed(2),
    currency,
    fx_rate: currency === 'UZS' ? '1' : String(fxRate || 1),
  }
}

async function refreshReturnPreview(): Promise<void> {
  if (!selectedSale.value) return
  returnLoading.value = true
  returnError.value = ''
  try {
    returnPreview.value = await fetchReturnPreview(selectedSale.value.id, {
      resolution: returnResolution.value,
      reason: returnReason.value,
      lines: selectedReturnLines(),
    })
  } catch (error) {
    returnError.value = error instanceof Error ? error.message : t('sales.returnPreviewFailed')
  } finally {
    returnLoading.value = false
  }
}

async function openReturnSheet(): Promise<void> {
  if (!selectedSale.value || isReturned(selectedSale.value)) return
  if (!selectedSale.value.lines || selectedSale.value.lines.length === 0) {
    await salesStore.fetchSale(selectedSale.value.id)
    selectedSale.value = salesStore.currentSale
  }
  returnResolution.value = 'RESTOCK'
  returnReason.value = 'CLIENT_REFUSE'
  returnRefundMethod.value = PaymentMethod.CASH
  returnQuantities.value = {}
  returnOpen.value = true
  await refreshReturnPreview()
}

function closeReturnSheet(): void {
  returnOpen.value = false
  returnPreview.value = null
  returnQuantities.value = {}
  returnError.value = ''
}

async function updateReturnQuantity(saleLineId: number, rawValue: string | number, maxQuantity: number): Promise<void> {
  const parsed = Number(rawValue)
  const next = Number.isFinite(parsed)
    ? Math.max(0, Math.min(maxQuantity, Math.floor(parsed)))
    : 0
  returnQuantities.value = {
    ...returnQuantities.value,
    [saleLineId]: next,
  }
  await refreshReturnPreview()
}

async function updateReturnResolution(value: ReturnResolution): Promise<void> {
  returnResolution.value = value
  await refreshReturnPreview()
}

async function confirmReturn(): Promise<void> {
  if (!selectedSale.value || returnSubmitting.value) return
  const lines = selectedReturnLines()
  if (lines.length === 0) {
    returnError.value = t('sales.selectReturnLine')
    return
  }
  const refundPayment = preferredRefundPayment()
  if (selectedReturnAmountUzs() > 0 && Number(refundPayment.amount) <= 0) {
    returnError.value = t('sales.refundCalcFailed')
    return
  }
  returnSubmitting.value = true
  returnError.value = ''
  try {
    await salesStore.processReturn(selectedSale.value.id, {
      resolution: returnResolution.value,
      reason: returnReason.value,
      lines,
      refund_payments: selectedReturnAmountUzs() > 0 ? [refundPayment] : [],
    })
    selectedSale.value = salesStore.currentSale
    toast.success(t('sales.returnDone'))
    closeReturnSheet()
  } catch (error) {
    returnError.value = error instanceof Error ? error.message : t('sales.returnFailed')
  } finally {
    returnSubmitting.value = false
  }
}

function openExplanation(): void {
  if (!selectedSale.value) return
  const saleId = selectedSale.value.id
  closeDetail()
  router.push({ name: 'reports-sale-explanation', params: { id: saleId } })
}
</script>

<template>
  <div class="history-page">
    <!-- ── Sticky header ─────────────────────────────────────── -->
    <header class="page-header">
      <h1 class="page-title">{{ t('sales.history') }}</h1>
      <button class="icon-btn" :aria-label="t('sales.filterByPayment')" disabled>
        <SlidersHorizontal :size="20" :stroke-width="1.75" />
      </button>
    </header>

    <!-- ── Payment filter chips ──────────────────────────────── -->
    <div class="filter-row" role="group" :aria-label="t('sales.filterByPayment')">
      <button
        v-for="chip in FILTER_CHIPS"
        :key="chip.value"
        class="filter-chip"
        :class="{ active: activeFilter === chip.value }"
        @click="activeFilter = chip.value"
      >
        {{ chip.label }}
      </button>
    </div>

    <section class="session-summary" :class="{ 'session-summary--inactive': !hasActiveSession }">
      <div class="session-summary__header">
        <div class="session-summary__title-wrap">
          <p class="session-summary__eyebrow">{{ t('sales.shiftAndPayments') }}</p>
          <h2 class="session-summary__title">
            {{ hasActiveSession && activeSession ? t('sales.shiftNumber', { id: activeSession.id }) : t('sales.historyWithoutOpenShift') }}
          </h2>
        </div>
        <span class="session-summary__badge" :class="{ 'session-summary__badge--open': hasActiveSession }">
          {{ hasActiveSession ? t('sales.openBadge') : t('sales.allSales') }}
        </span>
      </div>

      <p class="session-summary__meta">{{ sessionMetaLabel() }}</p>

      <div v-if="hasActiveSession && activeSession" class="session-summary__grid">
        <div class="session-summary__metric">
          <span class="session-summary__label">{{ t('sales.startCash') }}</span>
          <strong class="session-summary__value tabular-nums">{{ formatPrice(activeSession.opening_cash) }}</strong>
        </div>
        <div class="session-summary__metric">
          <span class="session-summary__label">{{ t('sales.cashSales') }}</span>
          <strong class="session-summary__value tabular-nums">{{ formatPrice(activeSession.cash_sales_total || '0') }}</strong>
        </div>
        <div class="session-summary__metric">
          <span class="session-summary__label">{{ t('sales.expectedCash') }}</span>
          <strong class="session-summary__value tabular-nums">{{ formatPrice(activeSession.expected_cash || activeSession.opening_cash) }}</strong>
        </div>
        <div class="session-summary__metric">
          <span class="session-summary__label">{{ t('sales.salesCount') }}</span>
          <strong class="session-summary__value tabular-nums">{{ activeSession.sales_count ?? 0 }}</strong>
        </div>
      </div>

      <p class="session-summary__hint">
        {{ t('sales.filterHint') }}
      </p>
    </section>

    <!-- ── Content ───────────────────────────────────────────── -->
    <div class="content">

      <!-- Skeleton loading -->
      <template v-if="salesStore.isLoading && filteredSales.length === 0">
        <div class="skeleton-group">
          <div class="skeleton-label" />
          <div v-for="n in 3" :key="n" class="skeleton-card" />
        </div>
      </template>

      <!-- Error state -->
      <div v-else-if="salesStore.error && filteredSales.length === 0" class="state-box state-error">
        <RotateCcw :size="28" :stroke-width="1.5" class="state-icon" />
        <p class="state-title">{{ t('sales.loadingError') }}</p>
        <p class="state-body">{{ salesStore.error }}</p>
        <button class="btn-retry" @click="loadSales(1)">{{ t('common.retry') }}</button>
      </div>

      <!-- Empty state -->
      <div v-else-if="!salesStore.isLoading && filteredSales.length === 0" class="state-box">
        <p class="state-title">{{ t('sales.noSales') }}</p>
        <p class="state-body">
          {{
            activeFilter === 'all'
              ? hasActiveSession
                ? t('sales.noSalesInSession')
                : t('sales.noSalesYet')
              : t('sales.noSalesForPayment')
          }}
        </p>
      </div>

      <!-- Sale groups -->
      <template v-else>
        <section
          v-for="group in groupedSales"
          :key="group.label"
          class="sale-group"
        >
          <div class="group-label">
            <span class="group-date">{{ group.label }}</span>
            <span class="group-count">{{ t('sales.saleCount', { count: group.count }) }}</span>
          </div>

          <button
            v-for="sale in group.sales"
            :key="sale.id"
            class="sale-card"
            @click="openDetail(sale)"
          >
            <div class="sale-left">
              <div class="sale-id-row">
                <span class="sale-id">#{{ sale.id }}</span>
                <span class="sale-time">{{ formatTime(sale.created_at) }}</span>
                <span v-if="isReturned(sale)" class="badge badge-return">{{ t('sales.returnedBadge') }}</span>
                <span v-else-if="isPartiallyReturned(sale)" class="badge badge-return">{{ t('sales.partiallyReturnedBadge') }}</span>
              </div>
              <span class="sale-items">{{ itemsLabel(sale) }}</span>
            </div>

            <div class="sale-right">
              <span class="sale-amount tabular-nums">{{ formatPrice(sale.total_amount) }}</span>
              <span v-if="operationTrace(sale)" class="sale-trace">{{ operationTrace(sale) }}</span>
              <span
                class="badge"
                :class="paymentBadgeClass(sale)"
              >
                {{ paymentBadgeLabel(sale) }}
              </span>
              <span class="sale-payment-note">{{ paymentSummaryLabel(sale) }}</span>
            </div>
          </button>
        </section>

        <!-- Load more -->
        <button
          v-if="salesStore.hasMore"
          class="btn-load-more"
          :disabled="salesStore.isLoading"
          @click="loadMore"
        >
          <span v-if="salesStore.isLoading">{{ t('common.loadingMore') }}</span>
          <span v-else>{{ t('common.loadMore') }}</span>
        </button>
      </template>
    </div>

    <!-- ── Sale detail bottom sheet ──────────────────────────── -->
    <AppBottomSheet
      :open="detailOpen"
      :title="selectedSale ? t('sales.saleTitle', { id: selectedSale.id }) : ''"
      @close="closeDetail"
    >
      <template v-if="detailLoading">
        <div class="detail-skeleton">
          <div class="skeleton-line skeleton-line--md" />
          <div class="skeleton-line skeleton-line--sm" />
          <div class="skeleton-line skeleton-line--lg" />
          <div class="skeleton-line skeleton-line--md" />
        </div>
      </template>

      <template v-else-if="selectedSale">
        <!-- Meta row -->
        <div class="detail-meta">
          <span class="detail-date">{{ formatDateTime(selectedSale.created_at) }}</span>
          <span
            class="badge"
            :class="paymentBadgeClass(selectedSale)"
          >
            {{ paymentBadgeLabel(selectedSale) }}
          </span>
        </div>

        <!-- Returned banner -->
        <div v-if="isReturned(selectedSale)" class="detail-return-banner">
          {{ t('sales.saleReturned') }}
        </div>
        <div v-else-if="isPartiallyReturned(selectedSale)" class="detail-return-banner">
          {{ t('sales.salePartiallyReturned') }}
        </div>

        <!-- Line items -->
        <div class="detail-lines">
          <div
            v-for="line in selectedSale.lines"
            :key="line.id"
            class="detail-line"
          >
            <div class="line-info">
              <span class="line-name">{{ lineDisplayName(line) }}</span>
              <span class="line-qty">× {{ line.quantity }}</span>
            </div>
            <span class="line-price tabular-nums">{{ formatPrice(line.unit_price) }}</span>
          </div>
        </div>

        <!-- Divider -->
        <div class="detail-divider" />

        <!-- Total -->
        <div class="detail-total">
          <span class="total-label">{{ t('common.total') }}</span>
          <span class="total-amount tabular-nums">{{ formatPrice(selectedSale.total_amount) }}</span>
        </div>
        <p v-if="operationTrace(selectedSale)" class="detail-trace">
          {{ operationTrace(selectedSale) }}
        </p>

        <section class="payment-card">
          <div class="payment-card__header">
            <div class="payment-card__heading">
              <span class="payment-card__title">{{ t('sales.payment') }}</span>
              <span class="payment-card__subtitle">{{ paymentSummaryLabel(selectedSale) }}</span>
            </div>
            <strong class="payment-card__total tabular-nums">{{ formatPrice(selectedSale.total_amount) }}</strong>
          </div>

          <div v-if="incomingPayments(selectedSale).length > 0" class="payment-list">
            <div
              v-for="payment in incomingPayments(selectedSale)"
              :key="payment.id"
              class="payment-row"
            >
              <div class="payment-row__info">
                <span class="payment-row__method">{{ paymentLabel(payment.method) }}</span>
                <span class="payment-row__meta">{{ payment.currency.toUpperCase() }}</span>
              </div>
              <span class="payment-row__amount tabular-nums">{{ paymentAmountTrace(payment) }}</span>
            </div>
          </div>

          <p v-else class="payment-card__empty">
            {{ t('sales.paymentBreakdownMissing') }}
          </p>
        </section>

        <section class="profitability-card">
          <div class="profitability-header">
            <div class="profitability-heading">
              <span class="profitability-title">{{ t('sales.saleProfitability') }}</span>
              <span class="profitability-subtitle">{{ t('reports.grossProfit') }}</span>
            </div>
            <strong
              class="profitability-profit tabular-nums"
              :class="{ positive: saleGrossProfit(selectedSale) >= 0, negative: saleGrossProfit(selectedSale) < 0 }"
            >
              {{ formatPrice(saleGrossProfit(selectedSale)) }}
            </strong>
          </div>

          <div class="profitability-grid">
            <div class="profitability-metric">
              <span class="metric-label">{{ t('reports.revenue') }}</span>
              <strong class="metric-value tabular-nums">{{ formatPrice(saleRevenue(selectedSale)) }}</strong>
            </div>
            <div class="profitability-metric">
              <span class="metric-label">{{ t('sales.purchaseCost') }}</span>
              <strong class="metric-value tabular-nums">{{ formatPrice(salePurchaseCost(selectedSale)) }}</strong>
            </div>
            <div class="profitability-metric">
              <span class="metric-label">{{ t('sales.landedCost') }}</span>
              <strong class="metric-value tabular-nums">{{ formatPrice(saleLandedCost(selectedSale)) }}</strong>
            </div>
            <div class="profitability-metric">
              <span class="metric-label">{{ t('sales.marginPercent') }}</span>
              <strong class="metric-value tabular-nums">{{ saleMarginPercent(selectedSale) }}</strong>
            </div>
            <div class="profitability-metric">
              <span class="metric-label">{{ t('sales.investors') }}</span>
              <strong class="metric-value tabular-nums">{{ formatPrice(saleInvestorProfit(selectedSale)) }}</strong>
            </div>
            <div class="profitability-metric">
              <span class="metric-label">{{ t('sales.business') }}</span>
              <strong class="metric-value tabular-nums">{{ formatPrice(saleBusinessProfit(selectedSale)) }}</strong>
            </div>
          </div>
        </section>

        <button
          v-if="canOpenExplanation"
          class="btn-explain"
          @click="openExplanation"
        >
          {{ t('sales.explainAmount') }}
        </button>

        <!-- Return button -->
        <button
          class="btn-return"
          :disabled="isReturned(selectedSale)"
          @click="openReturnSheet"
        >
          {{ t('sales.returnSale') }}
        </button>
      </template>
    </AppBottomSheet>

    <AppBottomSheet
      :open="returnOpen"
      :title="t('sales.returnSaleTitle')"
      @close="closeReturnSheet"
    >
      <div class="return-sheet">
        <div class="return-mode">
          <button
            class="return-mode__option"
            :class="{ active: returnResolution === 'RESTOCK' }"
            @click="updateReturnResolution('RESTOCK')"
          >
            {{ t('sales.returnToStock') }}
          </button>
          <button
            class="return-mode__option"
            :class="{ active: returnResolution === 'DISPOSE' }"
            @click="updateReturnResolution('DISPOSE')"
          >
            {{ t('sales.disposeDefect') }}
          </button>
        </div>

        <label class="return-field">
          <span>{{ t('common.reason') }}</span>
          <select v-model="returnReason" class="return-select">
            <option value="CLIENT_REFUSE">{{ t('sales.clientRefuse') }}</option>
            <option value="DEFECT">{{ t('sales.defect') }}</option>
            <option value="OTHER">{{ t('sales.otherReason') }}</option>
          </select>
        </label>

        <div v-if="returnPreview" class="return-lines">
          <div
            v-for="line in returnPreview.lines"
            :key="line.sale_line_id"
            class="return-line"
          >
            <div class="return-line__main">
              <strong>{{ line.product_name }}</strong>
              <span>
                {{ t('sales.soldAvailable', { sold: line.sold_quantity, available: line.available_quantity }) }}
              </span>
            </div>
            <input
              class="return-line__input"
              type="number"
              min="0"
              :max="line.available_quantity"
              :value="returnQuantities[line.sale_line_id] || 0"
              @input="updateReturnQuantity(line.sale_line_id, ($event.target as HTMLInputElement).value, line.available_quantity)"
            >
          </div>
        </div>

        <div class="return-effect">
          <div>
            <span>{{ t('sales.refundToCustomer') }}</span>
            <strong>{{ formatPrice(returnPreview?.selected.refund_amount_uzs || 0) }}</strong>
          </div>
          <div>
            <span>{{ returnResolution === 'RESTOCK' ? t('sales.restockCogs') : t('sales.disposalLoss') }}</span>
            <strong>
              {{ formatPrice(returnResolution === 'RESTOCK'
                ? (returnPreview?.selected.restock_cogs_uzs || 0)
                : (returnPreview?.selected.disposal_loss_uzs || 0)) }}
            </strong>
          </div>
          <div>
            <span>{{ t('sales.profitReversal') }}</span>
            <strong>{{ formatPrice(returnPreview?.selected.profit_reversal_uzs || 0) }}</strong>
          </div>
        </div>

        <label class="return-field">
          <span>{{ t('sales.refundMethod') }}</span>
          <select v-model="returnRefundMethod" class="return-select">
            <option :value="PaymentMethod.CASH">{{ t('domain.paymentMethod.CASH') }}</option>
            <option :value="PaymentMethod.CARD">{{ t('domain.paymentMethod.CARD') }}</option>
            <option :value="PaymentMethod.TRANSFER">{{ t('domain.paymentMethod.TRANSFER') }}</option>
            <option value="RECEIVABLE_OFFSET">{{ t('sales.receivableOffset') }}</option>
          </select>
        </label>

        <p v-if="returnError" class="return-error">{{ returnError }}</p>

        <button
          class="btn-return-confirm"
          :disabled="returnSubmitting || returnLoading || selectedReturnLines().length === 0"
          @click="confirmReturn"
        >
          <span v-if="returnSubmitting">{{ t('sales.returnSubmitting') }}</span>
          <span v-else>{{ t('sales.confirmReturn') }}</span>
        </button>
      </div>
    </AppBottomSheet>
  </div>
</template>

<style scoped>
/* ── Layout ──────────────────────────────────────────────────────────────── */

.history-page {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  background: var(--color-bg-primary);
}

/* ── Header ─────────────────────────────────────────────────────────────── */

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
  line-height: var(--leading-tight);
}

.icon-btn {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  transition: background var(--duration-fast) var(--ease-out),
              color var(--duration-fast) var(--ease-out);
}

.icon-btn:hover:not(:disabled) {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

.icon-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ── Filter chips ───────────────────────────────────────────────────────── */

.filter-row {
  display: flex;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-5);
  overflow-x: auto;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
  background: var(--color-bg-primary);
}

.filter-row::-webkit-scrollbar {
  display: none;
}

.filter-chip {
  flex-shrink: 0;
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  border: 1px solid transparent;
  transition: background var(--duration-fast) var(--ease-out),
              color var(--duration-fast) var(--ease-out),
              border-color var(--duration-fast) var(--ease-out);
}

.filter-chip.active {
  background: var(--color-brand-50);
  color: var(--color-brand-600);
  border-color: var(--color-brand-200);
}

.filter-chip:active {
  transform: scale(0.96);
}

/* ── Session summary ────────────────────────────────────────────────────── */

.session-summary {
  margin: 0 var(--space-4);
  padding: var(--space-4);
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border-subtle);
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--color-brand-50) 72%, white 28%) 0%, var(--color-bg-elevated) 100%);
  box-shadow: var(--shadow-sm);
}

.session-summary--inactive {
  background:
    linear-gradient(180deg, var(--color-bg-secondary) 0%, var(--color-bg-elevated) 100%);
}

.session-summary__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}

.session-summary__title-wrap {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.session-summary__eyebrow {
  font-size: var(--text-2xs);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-tertiary);
}

.session-summary__title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.session-summary__badge {
  display: inline-flex;
  align-items: center;
  padding: 6px var(--space-3);
  border-radius: var(--radius-full);
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.session-summary__badge--open {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.session-summary__meta {
  margin-top: var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: var(--leading-snug);
}

.session-summary__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
  margin-top: var(--space-4);
}

.session-summary__metric {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: var(--space-3);
  border-radius: var(--radius-lg);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-subtle);
}

.session-summary__label {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.session-summary__value {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.session-summary__hint {
  margin-top: var(--space-3);
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

/* ── Content ────────────────────────────────────────────────────────────── */

.content {
  flex: 1;
  padding: var(--space-2) var(--space-4) var(--space-8);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

/* ── Date group ─────────────────────────────────────────────────────────── */

.sale-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-top: var(--space-3);
}

.group-label {
  display: flex;
  align-items: baseline;
  gap: var(--space-2);
  padding: 0 var(--space-1);
}

.group-date {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.group-count {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

/* ── Sale card ──────────────────────────────────────────────────────────── */

.sale-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--color-bg-elevated);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-subtle);
  box-shadow: var(--shadow-sm);
  text-align: left;
  width: 100%;
  cursor: pointer;
  transition: box-shadow var(--duration-fast) var(--ease-out),
              border-color var(--duration-fast) var(--ease-out),
              transform var(--duration-fast) var(--ease-out);
}

.sale-card:hover {
  border-color: var(--color-border-default);
  box-shadow: var(--shadow-md);
}

.sale-card:active {
  transform: scale(0.985);
}

.sale-left {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  min-width: 0;
}

.sale-id-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.sale-id {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  font-family: var(--font-mono);
}

.sale-time {
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
}

.sale-items {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.sale-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--space-2);
  flex-shrink: 0;
}

.sale-amount {
  font-size: var(--text-lg);
  font-weight: var(--font-bold);
  color: var(--color-text-primary);
}

.sale-trace {
  max-width: 200px;
  text-align: right;
  font-size: var(--text-2xs);
  color: var(--color-text-tertiary);
  line-height: var(--leading-snug);
}

.sale-payment-note {
  max-width: 200px;
  text-align: right;
  font-size: var(--text-2xs);
  color: var(--color-text-secondary);
  line-height: var(--leading-snug);
}

/* ── Badges ─────────────────────────────────────────────────────────────── */

.badge {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  white-space: nowrap;
}

.badge-cash {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.badge-card {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.badge-transfer {
  background: color-mix(in srgb, var(--color-brand-50) 65%, white 35%);
  color: var(--color-brand-600);
}

.badge-credit {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.badge-mixed {
  background: color-mix(in srgb, var(--color-info-bg) 45%, var(--color-warning-bg) 55%);
  color: var(--color-text-primary);
}

.badge-unknown {
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
}

.badge-return {
  background: var(--color-error-bg);
  color: var(--color-error);
}

/* ── Load more button ───────────────────────────────────────────────────── */

.btn-load-more {
  width: 100%;
  padding: var(--space-4);
  margin-top: var(--space-4);
  border-radius: var(--radius-lg);
  border: 1px dashed var(--color-border-default);
  background: transparent;
  color: var(--color-brand-500);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  transition: background var(--duration-fast) var(--ease-out),
              border-color var(--duration-fast) var(--ease-out);
}

.btn-load-more:hover:not(:disabled) {
  background: var(--color-brand-50);
  border-color: var(--color-brand-200);
}

.btn-load-more:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ── State boxes ────────────────────────────────────────────────────────── */

.state-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-16) var(--space-6);
  text-align: center;
}

.state-icon {
  color: var(--color-error);
  margin-bottom: var(--space-2);
}

.state-title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.state-body {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.btn-retry {
  margin-top: var(--space-4);
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

/* ── Skeleton ───────────────────────────────────────────────────────────── */

.skeleton-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  margin-top: var(--space-3);
}

.skeleton-label {
  height: 16px;
  width: 120px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-sunken);
  animation: shimmer 1.4s ease-in-out infinite;
}

.skeleton-card {
  height: 72px;
  border-radius: var(--radius-lg);
  background: var(--color-bg-sunken);
  animation: shimmer 1.4s ease-in-out infinite;
}

.skeleton-card:nth-child(3) { animation-delay: 0.1s; }
.skeleton-card:nth-child(4) { animation-delay: 0.2s; }

@keyframes shimmer {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ── Detail sheet content ───────────────────────────────────────────────── */

.detail-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}

.detail-date {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.detail-return-banner {
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-md);
  background: var(--color-error-bg);
  color: var(--color-error);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  margin-bottom: var(--space-4);
  text-align: center;
}

.detail-lines {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.detail-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.line-info {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

.line-name {
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.line-qty {
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
  flex-shrink: 0;
}

.line-price {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  flex-shrink: 0;
}

.detail-divider {
  height: 1px;
  background: var(--color-border-subtle);
  margin: var(--space-4) 0;
}

.detail-total {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-2);
}

.total-label {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.total-amount {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--color-text-primary);
}

.detail-trace {
  margin-bottom: var(--space-6);
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.payment-card {
  margin-bottom: var(--space-6);
  padding: var(--space-4);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
}

.payment-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.payment-card__heading {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.payment-card__title {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.payment-card__subtitle {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.payment-card__total {
  font-size: var(--text-lg);
  font-weight: var(--font-bold);
  color: var(--color-text-primary);
}

.payment-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.payment-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.payment-row__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.payment-row__method {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-primary);
}

.payment-row__meta {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.payment-row__amount {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  text-align: right;
}

.payment-card__empty {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.profitability-card {
  margin-bottom: var(--space-6);
  padding: var(--space-4);
  border-radius: var(--radius-lg);
  background: linear-gradient(180deg, var(--color-brand-50) 0%, var(--color-bg-elevated) 100%);
  border: 1px solid var(--color-brand-200);
}

.profitability-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.profitability-heading {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.profitability-title {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.profitability-subtitle {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.profitability-profit {
  font-size: var(--text-lg);
  font-weight: var(--font-bold);
}

.profitability-profit.positive {
  color: var(--color-success);
}

.profitability-profit.negative {
  color: var(--color-error);
}

.profitability-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}

.profitability-metric {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border-subtle);
}

.metric-label {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.metric-value {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.btn-explain {
  width: 100%;
  margin-bottom: var(--space-3);
  padding: var(--space-4);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-brand-200);
  background: color-mix(in srgb, var(--color-brand-50) 70%, white 30%);
  color: var(--color-brand-700);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  transition: background var(--duration-fast) var(--ease-out),
              border-color var(--duration-fast) var(--ease-out);
}

.btn-explain:hover {
  background: color-mix(in srgb, var(--color-brand-50) 82%, white 18%);
  border-color: var(--color-brand-300);
}

.btn-return {
  width: 100%;
  padding: var(--space-4);
  border-radius: var(--radius-lg);
  background: var(--color-bg-secondary);
  color: var(--color-error);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  border: 1px solid var(--color-error-bg);
  transition: background var(--duration-fast) var(--ease-out),
              border-color var(--duration-fast) var(--ease-out);
}

.btn-return:hover:not(:disabled) {
  background: var(--color-error-bg);
  border-color: var(--color-error);
}

.btn-return:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.return-sheet {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.return-mode {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-2);
  padding: 4px;
  border-radius: var(--radius-lg);
  background: var(--color-bg-secondary);
}

.return-mode__option {
  min-height: 44px;
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-secondary);
}

.return-mode__option.active {
  background: var(--color-bg-primary);
  color: var(--color-brand-700);
  box-shadow: var(--shadow-xs);
}

.return-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

.return-select,
.return-line__input {
  width: 100%;
  min-height: 44px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-size: var(--text-base);
}

.return-select {
  padding: 0 var(--space-3);
}

.return-line__input {
  max-width: 84px;
  padding: 0 var(--space-2);
  text-align: center;
  font-weight: var(--font-semibold);
}

.return-lines {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.return-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3);
  border-bottom: 1px solid var(--color-border-subtle);
}

.return-line:last-child {
  border-bottom: 0;
}

.return-line__main {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.return-line__main strong {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.return-line__main span {
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
}

.return-effect {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-secondary);
}

.return-effect > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.return-effect span {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.return-effect strong {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  text-align: right;
}

.return-error {
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-error-bg);
  color: var(--color-error);
  font-size: var(--text-sm);
}

.btn-return-confirm {
  width: 100%;
  min-height: 48px;
  border-radius: var(--radius-lg);
  background: var(--color-brand-600);
  color: white;
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
}

.btn-return-confirm:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* ── Detail skeleton ────────────────────────────────────────────────────── */

.detail-skeleton {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-2) 0;
}

.skeleton-line {
  border-radius: var(--radius-sm);
  background: var(--color-bg-sunken);
  animation: shimmer 1.4s ease-in-out infinite;
}

.skeleton-line--sm { height: 14px; width: 60%; }
.skeleton-line--md { height: 16px; width: 80%; }
.skeleton-line--lg { height: 18px; width: 100%; }

/* ── Reduced motion ─────────────────────────────────────────────────────── */

@media (prefers-reduced-motion: reduce) {
  .skeleton-card,
  .skeleton-label,
  .skeleton-line {
    animation: none;
    opacity: 0.6;
  }

  .sale-card,
  .filter-chip,
  .btn-load-more,
  .btn-return,
  .btn-retry {
    transition: none;
  }
}

@media (max-width: 420px) {
  .session-summary__grid,
  .profitability-grid {
    grid-template-columns: 1fr;
  }
}
</style>
