<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Wallet, Landmark, TrendingUp, ChevronRight, RefreshCcw, Settings } from 'lucide-vue-next'
import api from '@/api/client'
import { formatPrice } from '@/utils/currency'
import { useToast } from '@/composables/useToast'

interface SummaryItem {
  id: number
  investor: number
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

const router = useRouter()
const toast = useToast()

const summaries = ref<SummaryItem[]>([])
const records = ref<ProfitRecord[]>([])
const isLoading = ref(true)
const errorMessage = ref('')

function parseListResponse<T>(payload: unknown): T[] {
  if (Array.isArray(payload)) return payload as T[]
  if (payload && typeof payload === 'object' && Array.isArray((payload as Paginated<T>).results)) {
    return (payload as Paginated<T>).results
  }
  return []
}

const totalInvested = computed(() =>
  summaries.value.reduce((sum, item) => sum + parseFloat(item.total_invested || '0'), 0),
)

const totalProfit = computed(() =>
  summaries.value.reduce((sum, item) => sum + parseFloat(item.total_profit || '0'), 0),
)

const totalBusinessOwes = computed(() =>
  summaries.value.reduce((sum, item) => sum + parseFloat(item.business_owes || '0'), 0),
)

const recentRecords = computed(() =>
  [...records.value]
    .sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at))
    .slice(0, 6),
)

function contractTypeLabel(type: SummaryItem['contract_type']): string {
  return type === 'MUDARABA' ? 'Мудараба' : 'Мушарака'
}

function recordTypeLabel(type: ProfitRecord['record_type']): string {
  if (type === 'profit') return 'Прибыль'
  if (type === 'loss') return 'Убыток'
  return 'Возврат капитала'
}

function recordTypeClass(type: ProfitRecord['record_type']): string {
  if (type === 'profit') return 'record-positive'
  if (type === 'loss') return 'record-negative'
  return 'record-neutral'
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

async function loadDashboard(): Promise<void> {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const [summaryRes, recordsRes] = await Promise.all([
      api.get('/api/v1/investors/summaries/'),
      api.get('/api/v1/investors/profit-records/'),
    ])

    summaries.value = parseListResponse<SummaryItem>(summaryRes.data)
    records.value = parseListResponse<ProfitRecord>(recordsRes.data)
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить кабинет инвестора'
    toast.error('Ошибка загрузки кабинета инвестора')
  } finally {
    isLoading.value = false
  }
}

function openContract(contractId: number): void {
  router.push({ name: 'investor-contract', params: { id: contractId } })
}

onMounted(loadDashboard)
</script>

<template>
  <div class="dashboard-page">
    <header class="page-header">
      <h1 class="page-title">Кабинет инвестора</h1>
      <div class="header-actions">
        <button
          class="refresh-btn"
          type="button"
          aria-label="Настройки"
          @click="router.push({ name: 'settings' })"
        >
          <Settings :size="16" :stroke-width="1.75" />
        </button>
        <button class="refresh-btn" type="button" aria-label="Обновить" @click="loadDashboard">
          <RefreshCcw :size="16" :stroke-width="1.75" />
        </button>
      </div>
    </header>

    <main class="content">
      <div v-if="isLoading" class="loading-grid" aria-busy="true">
        <div class="skeleton-card" />
        <div class="skeleton-card" />
        <div class="skeleton-card" />
      </div>

      <div v-else-if="errorMessage" class="error-box" role="alert">
        {{ errorMessage }}
      </div>

      <template v-else>
        <section class="stats-grid">
          <article class="stat-card">
            <Wallet :size="18" :stroke-width="1.75" />
            <span class="stat-label">Инвестировано</span>
            <strong class="stat-value tabular-nums">{{ formatPrice(totalInvested) }}</strong>
          </article>
          <article class="stat-card">
            <TrendingUp :size="18" :stroke-width="1.75" />
            <span class="stat-label">Накопленная прибыль</span>
            <strong class="stat-value tabular-nums">{{ formatPrice(totalProfit) }}</strong>
          </article>
          <article class="stat-card">
            <Landmark :size="18" :stroke-width="1.75" />
            <span class="stat-label">Бизнес должен</span>
            <strong class="stat-value tabular-nums">{{ formatPrice(totalBusinessOwes) }}</strong>
          </article>
        </section>

        <section class="card">
          <h2 class="section-title">Активные договоры</h2>
          <div v-if="summaries.length === 0" class="empty-text">
            Активных договоров пока нет.
          </div>
          <button
            v-for="summary in summaries"
            v-else
            :key="summary.id"
            class="contract-row"
            type="button"
            @click="openContract(summary.contract)"
          >
            <div class="contract-main">
              <strong class="contract-title">
                {{ contractTypeLabel(summary.contract_type) }} · {{ summary.investor_name }}
              </strong>
              <span class="contract-meta">
                В обороте: {{ formatPrice(summary.in_stock_value) }}
              </span>
            </div>
            <div class="contract-right">
              <span class="contract-amount tabular-nums">{{ formatPrice(summary.business_owes) }}</span>
              <ChevronRight :size="16" :stroke-width="2" />
            </div>
          </button>
        </section>

        <section class="card">
          <h2 class="section-title">Последние движения</h2>
          <div v-if="recentRecords.length === 0" class="empty-text">
            Записи по прибыли и убыткам пока отсутствуют.
          </div>
          <article v-for="record in recentRecords" :key="record.id" class="record-row">
            <div class="record-main">
              <strong class="record-title">{{ recordTypeLabel(record.record_type) }}</strong>
              <span class="record-date">{{ formatDate(record.created_at) }}</span>
              <span v-if="record.description" class="record-description">{{ record.description }}</span>
            </div>
            <span class="record-amount tabular-nums" :class="recordTypeClass(record.record_type)">
              {{ record.record_type === 'loss' ? '-' : '+' }}{{ formatPrice(record.amount) }}
            </span>
          </article>
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped>
.dashboard-page {
  min-height: 100%;
  background: var(--color-bg-primary);
}

.page-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: var(--header-height);
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-bg-primary);
}

.header-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}

.page-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.refresh-btn {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-default);
  color: var(--color-text-secondary);
}

.content {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  padding-bottom: var(--space-8);
}

.stats-grid {
  display: grid;
  gap: var(--space-2);
}

.stat-card {
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  padding: var(--space-3);
  display: grid;
  gap: var(--space-1);
  color: var(--color-text-primary);
}

.stat-label {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.stat-value {
  font-size: var(--text-base);
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

.contract-row {
  width: 100%;
  min-height: 56px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-subtle);
  background: var(--color-bg-primary);
  padding: 0 var(--space-3);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  margin-top: var(--space-2);
}

.contract-main {
  display: grid;
  gap: 2px;
  text-align: left;
}

.contract-title {
  font-size: var(--text-sm);
  color: var(--color-text-primary);
}

.contract-meta {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.contract-right {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-text-secondary);
}

.contract-amount {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.record-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-2);
  border-top: 1px solid var(--color-border-subtle);
  padding-top: var(--space-2);
  margin-top: var(--space-2);
}

.record-main {
  display: grid;
  gap: 2px;
}

.record-title {
  font-size: var(--text-sm);
  color: var(--color-text-primary);
}

.record-date,
.record-description {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.record-amount {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.record-positive {
  color: var(--color-success);
}

.record-negative {
  color: var(--color-error);
}

.record-neutral {
  color: var(--color-info);
}

.empty-text {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.error-box {
  border-radius: var(--radius-md);
  border: 1px solid var(--color-error);
  background: var(--color-error-bg);
  color: var(--color-error);
  padding: var(--space-3);
  font-size: var(--text-sm);
}

.loading-grid {
  display: grid;
  gap: var(--space-2);
}

.skeleton-card {
  height: 76px;
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
