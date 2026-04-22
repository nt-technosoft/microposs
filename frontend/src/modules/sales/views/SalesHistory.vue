<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { SlidersHorizontal, RotateCcw } from 'lucide-vue-next'
import { useSalesStore } from '@/stores/sales'
import { useSessionStore } from '@/stores/session'
import { useToast } from '@/composables/useToast'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { PaymentMethod, SaleStatus } from '@/types/enums'
import type { Sale, SaleLine } from '@/types/models'
import { formatPrice } from '@/utils/currency'

// ── Stores & composables ────────────────────────────────────────────────────

const salesStore = useSalesStore()
const sessionStore = useSessionStore()
const toast = useToast()

// ── Filter state ────────────────────────────────────────────────────────────

type FilterOption = 'all' | PaymentMethod

interface FilterChip {
  value: FilterOption
  label: string
}

const FILTER_CHIPS: FilterChip[] = [
  { value: 'all', label: 'Все' },
  { value: PaymentMethod.CASH, label: 'Наличные' },
  { value: PaymentMethod.CARD, label: 'Карта' },
  { value: PaymentMethod.CREDIT, label: 'В долг' },
]

const activeFilter = ref<FilterOption>('all')

// ── Detail sheet state ──────────────────────────────────────────────────────

const detailOpen = ref(false)
const detailLoading = ref(false)
const selectedSale = ref<Sale | null>(null)

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

watch(activeFilter, () => {
  loadSales(1)
})

// ── Filtered sales ──────────────────────────────────────────────────────────

const filteredSales = computed<Sale[]>(() => {
  if (activeFilter.value === 'all') return salesStore.sales
  return salesStore.sales.filter(
    (sale) => sale.payment_method === activeFilter.value,
  )
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

  if (isSameDay(date, today)) return 'Сегодня'
  if (isSameDay(date, yesterday)) return 'Вчера'

  return date.toLocaleDateString('ru-RU', {
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
  return new Date(dateStr).toLocaleTimeString('ru-RU', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatDateTime(dateStr: string): string {
  return new Date(dateStr).toLocaleString('ru-RU', {
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

  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) return `${count} товар`
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return `${count} товара`
  return `${count} товаров`
}

function paymentLabel(method: PaymentMethod | string | undefined): string {
  const map: Record<string, string> = {
    [PaymentMethod.CASH]: 'Наличные',
    [PaymentMethod.CARD]: 'Карта',
    [PaymentMethod.TRANSFER]: 'Перевод',
    [PaymentMethod.CREDIT]: 'В долг',
    [PaymentMethod.CASH_LEGACY]: 'Наличные',
    [PaymentMethod.CARD_LEGACY]: 'Карта',
    [PaymentMethod.CREDIT_LEGACY]: 'В долг',
  }
  if (!method) return 'Не указано'
  return map[method] ?? method
}

function isReturned(sale: Sale): boolean {
  return sale.status === SaleStatus.RETURNED
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
    return `${opStr} • курс ${fxRate.toFixed(2)} • ${fnStr}`
  }
  return fnStr ? `${opStr} • ${fnStr}` : opStr
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
      toast.error('Не удалось загрузить детали продажи')
    } finally {
      detailLoading.value = false
    }
  }
}

function closeDetail(): void {
  detailOpen.value = false
  selectedSale.value = null
}

function handleReturnPlaceholder(): void {
  toast.info('Coming soon')
}
</script>

<template>
  <div class="history-page">
    <!-- ── Sticky header ─────────────────────────────────────── -->
    <header class="page-header">
      <h1 class="page-title">История продаж</h1>
      <button class="icon-btn" aria-label="Фильтры" disabled>
        <SlidersHorizontal :size="20" :stroke-width="1.75" />
      </button>
    </header>

    <!-- ── Payment filter chips ──────────────────────────────── -->
    <div class="filter-row" role="group" aria-label="Фильтр по способу оплаты">
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
        <p class="state-title">Ошибка загрузки</p>
        <p class="state-body">{{ salesStore.error }}</p>
        <button class="btn-retry" @click="loadSales(1)">Повторить</button>
      </div>

      <!-- Empty state -->
      <div v-else-if="!salesStore.isLoading && filteredSales.length === 0" class="state-box">
        <p class="state-title">Продаж нет</p>
        <p class="state-body">
          {{ activeFilter === 'all' ? 'В этой сессии ещё нет продаж' : 'Нет продаж с выбранным способом оплаты' }}
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
            <span class="group-count">{{ group.count }} {{ group.count === 1 ? 'продажа' : group.count <= 4 ? 'продажи' : 'продаж' }}</span>
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
                <span v-if="isReturned(sale)" class="badge badge-return">Возврат</span>
              </div>
              <span class="sale-items">{{ itemsLabel(sale) }}</span>
            </div>

            <div class="sale-right">
              <span class="sale-amount tabular-nums">{{ formatPrice(sale.total_amount) }}</span>
              <span v-if="operationTrace(sale)" class="sale-trace">{{ operationTrace(sale) }}</span>
              <span
                class="badge"
                :class="`badge-${sale.payment_method}`"
              >
                {{ paymentLabel(sale.payment_method) }}
              </span>
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
          <span v-if="salesStore.isLoading">Загрузка…</span>
          <span v-else>Загрузить ещё</span>
        </button>
      </template>
    </div>

    <!-- ── Sale detail bottom sheet ──────────────────────────── -->
    <AppBottomSheet
      :open="detailOpen"
      :title="selectedSale ? `Продажа #${selectedSale.id}` : ''"
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
            :class="`badge-${selectedSale.payment_method}`"
          >
            {{ paymentLabel(selectedSale.payment_method) }}
          </span>
        </div>

        <!-- Returned banner -->
        <div v-if="isReturned(selectedSale)" class="detail-return-banner">
          Продажа возвращена
        </div>

        <!-- Line items -->
        <div class="detail-lines">
          <div
            v-for="line in selectedSale.lines"
            :key="line.id"
            class="detail-line"
          >
            <div class="line-info">
              <span class="line-name">{{ line.product_variant.attribute_values.map(a => a.value).join(', ') || `Вариант #${line.product_variant.id}` }}</span>
              <span class="line-qty">× {{ line.quantity }}</span>
            </div>
            <span class="line-price tabular-nums">{{ formatPrice(line.unit_price) }}</span>
          </div>
        </div>

        <!-- Divider -->
        <div class="detail-divider" />

        <!-- Total -->
        <div class="detail-total">
          <span class="total-label">Итого</span>
          <span class="total-amount tabular-nums">{{ formatPrice(selectedSale.total_amount) }}</span>
        </div>
        <p v-if="operationTrace(selectedSale)" class="detail-trace">
          {{ operationTrace(selectedSale) }}
        </p>

        <!-- Return button -->
        <button
          class="btn-return"
          :disabled="isReturned(selectedSale)"
          @click="handleReturnPlaceholder"
        >
          Оформить возврат
        </button>
      </template>
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

.badge-credit {
  background: var(--color-warning-bg);
  color: var(--color-warning);
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
</style>
