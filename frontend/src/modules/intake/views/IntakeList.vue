<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Plus, RotateCcw, PackageOpen } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { formatPrice } from '@/utils/currency'
import { ReceiptType, ReceiptStatus } from '@/types/enums'
import api from '@/api/client'
import type { PaginatedResponse } from '@/api/catalog'

// ── Router & composables ────────────────────────────────────────────────────

const router = useRouter()
const toast = useToast()

// ── State ───────────────────────────────────────────────────────────────────

type StatusFilter = 'all' | ReceiptStatus

interface FilterChip {
  value: StatusFilter
  label: string
}

interface ReceiptListItem {
  id: number
  receipt_type: ReceiptType
  status: ReceiptStatus
  date: string
  created_at: string
  lines_count: number
  total_amount: string
  operation_currency?: string
  operation_amount?: string | null
  fx_rate_snapshot?: string | null
  functional_amount_uzs?: string | null
}

const FILTER_CHIPS: FilterChip[] = [
  { value: 'all', label: 'Все' },
  { value: ReceiptStatus.DRAFT, label: 'Черновик' },
  { value: ReceiptStatus.CONFIRMED, label: 'Подтверждён' },
]

const receipts = ref<ReceiptListItem[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)
const activeFilter = ref<StatusFilter>('all')

// ── API ──────────────────────────────────────────────────────────────────────

async function loadReceipts(): Promise<void> {
  isLoading.value = true
  error.value = null

  try {
    const params: Record<string, string> = {}
    if (activeFilter.value !== 'all') {
      params.status = activeFilter.value
    }

    const { data } = await api.get<PaginatedResponse<ReceiptListItem>>(
      '/api/v1/inventory/receipts/',
      { params },
    )
    receipts.value = data.results
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Не удалось загрузить приходы'
    error.value = message
    toast.error(message)
  } finally {
    isLoading.value = false
  }
}

onMounted(loadReceipts)

// ── Computed ─────────────────────────────────────────────────────────────────

const filteredReceipts = computed<ReceiptListItem[]>(() => {
  if (activeFilter.value === 'all') return receipts.value
  return receipts.value.filter((r) => r.status === activeFilter.value)
})

// ── Type & status helpers ────────────────────────────────────────────────────

interface TypeMeta {
  label: string
  colorClass: string
}

const TYPE_META: Record<ReceiptType, TypeMeta> = {
  [ReceiptType.BUSINESS_OWNED]: { label: 'Свои деньги', colorClass: 'badge-type--teal' },
  [ReceiptType.MUDARABA]: { label: 'Мудараба', colorClass: 'badge-type--purple' },
  [ReceiptType.MUSHARAKA]: { label: 'Мушарака', colorClass: 'badge-type--indigo' },
  [ReceiptType.SUPPLIER_PURCHASE]: { label: 'Поставщик', colorClass: 'badge-type--blue' },
  [ReceiptType.CONSIGNMENT]: { label: 'Консигнация', colorClass: 'badge-type--orange' },
}

const STATUS_META: Record<ReceiptStatus, { label: string; colorClass: string }> = {
  [ReceiptStatus.DRAFT]: { label: 'Черновик', colorClass: 'badge-status--gray' },
  [ReceiptStatus.CONFIRMED]: { label: 'Подтверждён', colorClass: 'badge-status--green' },
}

function getTypeMeta(type: ReceiptType): TypeMeta {
  return TYPE_META[type] ?? { label: type, colorClass: 'badge-type--blue' }
}

function getStatusMeta(status: ReceiptStatus) {
  return STATUS_META[status] ?? { label: status, colorClass: 'badge-status--gray' }
}

// ── Formatting ───────────────────────────────────────────────────────────────

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
  })
}

function totalCost(totalAmount: string): string {
  const total = parseFloat(totalAmount || '0')
  return formatPrice(Number.isNaN(total) ? 0 : total)
}

function linesLabel(countRaw: number): string {
  const count = Number.isFinite(countRaw) ? countRaw : 0
  const mod10 = count % 10
  const mod100 = count % 100
  if (mod10 === 1 && mod100 !== 11) return `${count} позиция`
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return `${count} позиции`
  return `${count} позиций`
}

function operationTrace(receipt: ReceiptListItem): string {
  const currency = (receipt.operation_currency || 'UZS').toUpperCase()
  const opAmount = Number.parseFloat(receipt.operation_amount || '')
  const fxRate = Number.parseFloat(receipt.fx_rate_snapshot || '')
  const functional = Number.parseFloat(receipt.functional_amount_uzs || '')

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

// ── Navigation ───────────────────────────────────────────────────────────────

function goToDetail(id: number): void {
  router.push({ name: 'intake-detail', params: { id } })
}

function goToCreate(): void {
  router.push({ name: 'intake-create' })
}

function onFilterChange(value: StatusFilter): void {
  activeFilter.value = value
  loadReceipts()
}
</script>

<template>
  <div class="list-page">
    <!-- ── Header ──────────────────────────────────────────────── -->
    <header class="page-header">
      <h1 class="page-title">Приходы</h1>
      <button class="btn-new" aria-label="Новый приход" @click="goToCreate">
        <Plus :size="18" :stroke-width="2" />
        <span>Новый</span>
      </button>
    </header>

    <!-- ── Status filter chips ───────────────────────────────── -->
    <div class="filter-row" role="group" aria-label="Фильтр по статусу">
      <button
        v-for="chip in FILTER_CHIPS"
        :key="chip.value"
        class="filter-chip"
        :class="{ active: activeFilter === chip.value }"
        @click="onFilterChange(chip.value)"
      >
        {{ chip.label }}
      </button>
    </div>

    <!-- ── Content ───────────────────────────────────────────── -->
    <div class="content">

      <!-- Skeleton loading -->
      <template v-if="isLoading && filteredReceipts.length === 0">
        <div v-for="n in 4" :key="n" class="skeleton-card" />
      </template>

      <!-- Error state -->
      <div v-else-if="error && filteredReceipts.length === 0" class="state-box state-error">
        <RotateCcw :size="28" :stroke-width="1.5" class="state-icon" />
        <p class="state-title">Ошибка загрузки</p>
        <p class="state-body">{{ error }}</p>
        <button class="btn-retry" @click="loadReceipts">Повторить</button>
      </div>

      <!-- Empty state -->
      <div v-else-if="!isLoading && filteredReceipts.length === 0" class="state-box">
        <PackageOpen :size="40" :stroke-width="1.25" class="state-icon-empty" />
        <p class="state-title">Нет приходов</p>
        <p class="state-body">
          {{ activeFilter === 'all'
            ? 'Создайте первый приход товаров'
            : 'Нет приходов с выбранным статусом' }}
        </p>
        <button v-if="activeFilter === 'all'" class="btn-retry" @click="goToCreate">
          Создать приход
        </button>
      </div>

      <!-- Receipt list -->
      <template v-else>
        <button
          v-for="receipt in filteredReceipts"
          :key="receipt.id"
          class="receipt-card"
          @click="goToDetail(receipt.id)"
        >
          <!-- Top row: ID + date + type badge -->
          <div class="card-top">
            <div class="card-id-row">
              <span class="card-id">#{{ receipt.id }}</span>
              <span class="card-date">{{ formatDate(receipt.date || receipt.created_at) }}</span>
            </div>
            <span class="badge-type" :class="getTypeMeta(receipt.receipt_type).colorClass">
              {{ getTypeMeta(receipt.receipt_type).label }}
            </span>
          </div>

          <!-- Bottom row: lines count + total + status -->
          <div class="card-bottom">
              <span class="card-lines">{{ linesLabel(receipt.lines_count) }}</span>
              <div class="card-right">
                <span class="card-total tabular-nums">{{ totalCost(receipt.total_amount) }}</span>
                <span v-if="operationTrace(receipt)" class="card-trace">{{ operationTrace(receipt) }}</span>
                <span
                  class="badge-status"
                  :class="getStatusMeta(receipt.status).colorClass"
              >
                {{ getStatusMeta(receipt.status).label }}
              </span>
            </div>
          </div>
        </button>
      </template>
    </div>
  </div>
</template>

<style scoped>
/* ── Layout ──────────────────────────────────────────────────────────────── */

.list-page {
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

.btn-new {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  height: 36px;
  padding: 0 var(--space-4);
  border-radius: var(--radius-full);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  white-space: nowrap;
  transition: background var(--duration-fast) var(--ease-out),
              transform var(--duration-fast) var(--ease-out);
}

.btn-new:hover {
  background: var(--color-brand-600);
}

.btn-new:active {
  transform: scale(0.97);
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
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4) var(--space-8);
}

/* ── Receipt card ────────────────────────────────────────────────────────── */

.receipt-card {
  display: flex;
  flex-direction: column;
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

.receipt-card:hover {
  border-color: var(--color-border-default);
  box-shadow: var(--shadow-md);
}

.receipt-card:active {
  transform: scale(0.985);
}

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.card-id-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.card-id {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  font-family: var(--font-mono);
}

.card-date {
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
}

.card-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.card-lines {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.card-right {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: var(--space-1);
}

.card-total {
  font-size: var(--text-base);
  font-weight: var(--font-bold);
  color: var(--color-text-primary);
}

.card-trace {
  max-width: 220px;
  text-align: right;
  font-size: var(--text-2xs);
  color: var(--color-text-tertiary);
  line-height: var(--leading-snug);
}

/* ── Type badges ────────────────────────────────────────────────────────── */

.badge-type {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  white-space: nowrap;
  flex-shrink: 0;
}

.badge-type--teal {
  background: var(--color-brand-50);
  color: var(--color-brand-600);
}

.badge-type--purple {
  background: #F3E8FF;
  color: #7C3AED;
}

.badge-type--indigo {
  background: #EEF2FF;
  color: #4338CA;
}

.badge-type--blue {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.badge-type--orange {
  background: #FFF7ED;
  color: #C2410C;
}

/* ── Status badges ──────────────────────────────────────────────────────── */

.badge-status {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  white-space: nowrap;
  flex-shrink: 0;
}

.badge-status--gray {
  background: var(--color-bg-sunken);
  color: var(--color-text-secondary);
}

.badge-status--green {
  background: var(--color-success-bg);
  color: var(--color-success);
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

.state-icon-empty {
  color: var(--color-text-tertiary);
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

.skeleton-card {
  height: 88px;
  border-radius: var(--radius-lg);
  background: var(--color-bg-sunken);
  animation: shimmer 1.4s ease-in-out infinite;
}

.skeleton-card:nth-child(2) { animation-delay: 0.1s; }
.skeleton-card:nth-child(3) { animation-delay: 0.2s; }
.skeleton-card:nth-child(4) { animation-delay: 0.3s; }

@keyframes shimmer {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ── Reduced motion ─────────────────────────────────────────────────────── */

@media (prefers-reduced-motion: reduce) {
  .skeleton-card { animation: none; opacity: 0.6; }
  .receipt-card, .filter-chip, .btn-new, .btn-retry { transition: none; }
}
</style>
