<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, RefreshCcw } from 'lucide-vue-next'
import api from '@/api/client'
import { formatPrice } from '@/utils/currency'

interface SummaryItem {
  id: number
  investor_name: string
  contract: number
  contract_type: 'MUDARABA' | 'MUSHARAKA'
  total_invested: string
  in_stock_value: string
  total_sold_revenue: string
  total_profit: string
  total_losses: string
  turnover_ratio: string
  business_owes: string
  last_updated: string
}

interface ProfitRecord {
  id: number
  contract: number
  record_type: 'profit' | 'loss' | 'capital_return'
  amount: string
  description: string
  created_at: string
}

interface Paginated<T> {
  results: T[]
}

const route = useRoute()
const router = useRouter()

const summary = ref<SummaryItem | null>(null)
const records = ref<ProfitRecord[]>([])
const isLoading = ref(true)
const errorMessage = ref('')

const contractId = computed(() => Number(route.params.id))

function parseListResponse<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) return payload as T[]
  if (payload && typeof payload === 'object' && Array.isArray((payload as Paginated<T>).results)) {
    return (payload as Paginated<T>).results
  }
  return []
}

function contractTypeLabel(type: SummaryItem['contract_type']): string {
  return type === 'MUDARABA' ? 'Мудараба' : 'Мушарака'
}

function recordTypeLabel(type: ProfitRecord['record_type']): string {
  if (type === 'profit') return 'Прибыль'
  if (type === 'loss') return 'Убыток'
  return 'Возврат капитала'
}

function recordTypeClass(type: ProfitRecord['record_type']): string {
  if (type === 'profit') return 'positive'
  if (type === 'loss') return 'negative'
  return 'neutral'
}

function formatDateTime(value: string): string {
  return new Date(value).toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function loadContract(): Promise<void> {
  if (!Number.isFinite(contractId.value)) {
    errorMessage.value = 'Некорректный ID договора'
    isLoading.value = false
    return
  }

  isLoading.value = true
  errorMessage.value = ''

  try {
    const [summariesRes, recordsRes] = await Promise.all([
      api.get('/api/v1/investors/summaries/'),
      api.get('/api/v1/investors/profit-records/', {
        params: { contract: contractId.value },
      }),
    ])

    const summaries = parseListResponse<SummaryItem>(summariesRes.data)
    summary.value = summaries.find((item) => item.contract === contractId.value) ?? null
    records.value = parseListResponse<ProfitRecord>(recordsRes.data)
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить договор'
  } finally {
    isLoading.value = false
  }
}

onMounted(loadContract)
</script>

<template>
  <div class="detail-page">
    <header class="page-header">
      <button class="back-btn" type="button" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>
      <h1 class="page-title">Договор #{{ route.params.id }}</h1>
      <button class="refresh-btn" type="button" aria-label="Обновить" @click="loadContract">
        <RefreshCcw :size="16" :stroke-width="1.75" />
      </button>
    </header>

    <main class="content">
      <div v-if="isLoading" class="loading-list" aria-busy="true">
        <div class="skeleton-row" />
        <div class="skeleton-row" />
        <div class="skeleton-row" />
      </div>

      <div v-else-if="errorMessage" class="error-box" role="alert">
        {{ errorMessage }}
      </div>

      <template v-else-if="summary">
        <section class="card">
          <h2 class="section-title">{{ contractTypeLabel(summary.contract_type) }}</h2>
          <div class="meta-grid">
            <div class="meta-row">
              <span>Инвестор</span>
              <strong>{{ summary.investor_name }}</strong>
            </div>
            <div class="meta-row">
              <span>Обновлено</span>
              <strong>{{ formatDateTime(summary.last_updated) }}</strong>
            </div>
          </div>
        </section>

        <section class="card">
          <h2 class="section-title">Финансовые показатели</h2>
          <div class="metrics-grid">
            <div class="metric">
              <span>Инвестировано</span>
              <strong class="tabular-nums">{{ formatPrice(summary.total_invested) }}</strong>
            </div>
            <div class="metric">
              <span>В товаре</span>
              <strong class="tabular-nums">{{ formatPrice(summary.in_stock_value) }}</strong>
            </div>
            <div class="metric">
              <span>Продано</span>
              <strong class="tabular-nums">{{ formatPrice(summary.total_sold_revenue) }}</strong>
            </div>
            <div class="metric">
              <span>Прибыль</span>
              <strong class="tabular-nums positive">{{ formatPrice(summary.total_profit) }}</strong>
            </div>
            <div class="metric">
              <span>Убытки</span>
              <strong class="tabular-nums negative">{{ formatPrice(summary.total_losses) }}</strong>
            </div>
            <div class="metric">
              <span>Бизнес должен</span>
              <strong class="tabular-nums">{{ formatPrice(summary.business_owes) }}</strong>
            </div>
          </div>
        </section>

        <section class="card">
          <h2 class="section-title">История записей</h2>
          <div v-if="records.length === 0" class="empty-text">
            Записей по договору пока нет.
          </div>
          <article v-for="record in records" :key="record.id" class="record-row">
            <div class="record-main">
              <strong>{{ recordTypeLabel(record.record_type) }}</strong>
              <span class="record-date">{{ formatDateTime(record.created_at) }}</span>
              <span v-if="record.description" class="record-description">{{ record.description }}</span>
            </div>
            <span class="record-amount tabular-nums" :class="recordTypeClass(record.record_type)">
              {{ record.record_type === 'loss' ? '-' : '+' }}{{ formatPrice(record.amount) }}
            </span>
          </article>
        </section>
      </template>

      <div v-else class="error-box">Договор не найден или недоступен.</div>
    </main>
  </div>
</template>

<style scoped>
.detail-page {
  min-height: 100%;
  background: var(--color-bg-primary);
}

.page-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: grid;
  grid-template-columns: 40px 1fr 40px;
  align-items: center;
  gap: var(--space-3);
  min-height: var(--header-height);
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-bg-primary);
}

.page-title {
  text-align: center;
  font-size: var(--text-lg);
  color: var(--color-text-primary);
  font-weight: var(--font-semibold);
}

.back-btn,
.refresh-btn {
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
}

.content {
  padding: var(--space-4);
  display: grid;
  gap: var(--space-3);
}

.card {
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
  padding: var(--space-3);
}

.section-title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  margin-bottom: var(--space-2);
}

.meta-grid {
  display: grid;
  gap: var(--space-2);
}

.meta-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.meta-row strong {
  color: var(--color-text-primary);
}

.metrics-grid {
  display: grid;
  gap: var(--space-2);
}

.metric {
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  padding: var(--space-2) var(--space-3);
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.metric strong {
  color: var(--color-text-primary);
}

.positive {
  color: var(--color-success);
}

.negative {
  color: var(--color-error);
}

.record-row {
  border-top: 1px solid var(--color-border-subtle);
  margin-top: var(--space-2);
  padding-top: var(--space-2);
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
}

.record-main {
  display: grid;
  gap: 2px;
  color: var(--color-text-primary);
  font-size: var(--text-sm);
}

.record-date,
.record-description {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.record-amount {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.record-amount.positive {
  color: var(--color-success);
}

.record-amount.negative {
  color: var(--color-error);
}

.record-amount.neutral {
  color: var(--color-info);
}

.empty-text {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.error-box {
  border-radius: var(--radius-md);
  border: 1px solid var(--color-error);
  background: var(--color-error-bg);
  color: var(--color-error);
  padding: var(--space-3);
  font-size: var(--text-sm);
}

.loading-list {
  display: grid;
  gap: var(--space-2);
}

.skeleton-row {
  height: 70px;
  border-radius: var(--radius-md);
  background: linear-gradient(
    90deg,
    var(--color-bg-secondary) 0%,
    var(--color-bg-elevated) 50%,
    var(--color-bg-secondary) 100%
  );
  background-size: 200% 100%;
  animation: shimmer 1.1s linear infinite;
}

@keyframes shimmer {
  from { background-position: 0 0; }
  to { background-position: 200% 0; }
}
</style>
