<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, RefreshCcw } from 'lucide-vue-next'
import { formatPrice } from '@/utils/currency'
import { fetchInvestorProcurementDetail } from '@/api/investors'
import type { InvestorLedgerEntry, InvestorLedgerTotals, InvestorProcurementDetail } from '@/types/models'

const route = useRoute()
const router = useRouter()

const procurement = ref<InvestorProcurementDetail | null>(null)
const isLoading = ref(true)
const errorMessage = ref('')

const procurementId = computed(() => Number(route.params.id))
type LedgerAmountKey = keyof InvestorLedgerTotals
const currencyPriority = ['USD', 'UZS']

function nonZero(value: string | undefined): boolean {
  return Math.abs(Number.parseFloat(value ?? '0')) > 0.000001
}

function formatAggregateAmount(
  field: LedgerAmountKey,
  preferredCurrency?: string,
): string {
  const aggregate = procurement.value?.investor_aggregate
  if (!aggregate) return formatPrice('0', 'UZS')

  const currencies = Object.keys(aggregate.by_currency ?? {}).sort((a, b) => {
    const aIndex = currencyPriority.indexOf(a)
    const bIndex = currencyPriority.indexOf(b)
    return (aIndex === -1 ? 99 : aIndex) - (bIndex === -1 ? 99 : bIndex)
  })

  if (preferredCurrency && nonZero(aggregate.by_currency?.[preferredCurrency]?.[field])) {
    return formatPrice(aggregate.by_currency[preferredCurrency][field], preferredCurrency)
  }

  const parts = currencies
    .map((currency) => ({ currency, amount: aggregate.by_currency[currency][field] }))
    .filter(({ amount }) => nonZero(amount))

  if (parts.length === 0) {
    return formatPrice(aggregate.functional_uzs?.[field] ?? '0', 'UZS')
  }

  return parts
    .map(({ currency, amount }) => formatPrice(amount, currency))
    .join(' + ')
}

function procurementTypeLabel(type: string): string {
  if (type === 'PARTNERSHIP') return 'Партнёрский'
  if (type === 'MUSHARAKA') return 'Мушарака'
  return type
}

function entryLabel(entry: InvestorLedgerEntry): string {
  if (entry.entry_type === 'CAPITAL_IN') return 'Внос капитала'
  if (entry.entry_type === 'CAPITAL_OUT') return 'Возврат капитала'
  if (entry.entry_type === 'PROFIT_ACCRUED') return 'Начислена прибыль'
  if (entry.entry_type === 'DIVIDEND_PAID') return 'Дивиденд выплачен'
  if (entry.entry_type === 'LOSS_INCURRED') return 'Убыток'
  return entry.entry_type
}

function entryClass(entry: InvestorLedgerEntry): string {
  if (entry.entry_type === 'CAPITAL_IN' || entry.entry_type === 'PROFIT_ACCRUED') return 'positive'
  if (entry.entry_type === 'LOSS_INCURRED') return 'negative'
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

function formatCapitalState(field: keyof InvestorProcurementDetail['capital_state']): string {
  return formatPrice(procurement.value?.capital_state?.[field] ?? '0', 'UZS')
}

async function loadContract(): Promise<void> {
  if (!Number.isFinite(procurementId.value)) {
    errorMessage.value = 'Некорректный ID прихода'
    isLoading.value = false
    return
  }

  isLoading.value = true
  errorMessage.value = ''

  try {
    procurement.value = await fetchInvestorProcurementDetail(procurementId.value)
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить приход'
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
      <h1 class="page-title">Приход #{{ route.params.id }}</h1>
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

      <template v-else-if="procurement">
        <section class="card">
          <h2 class="section-title">{{ procurementTypeLabel(procurement.procurement_type) }}</h2>
          <div class="meta-grid">
            <div class="meta-row">
              <span>Поставщик</span>
              <strong>{{ procurement.supplier_name || '—' }}</strong>
            </div>
            <div class="meta-row">
              <span>Открыт</span>
              <strong>{{ formatDateTime(procurement.opened_at) }}</strong>
            </div>
          </div>
        </section>

        <section class="card">
          <h2 class="section-title">Финансовые показатели</h2>
          <div class="metrics-grid">
            <div class="metric">
              <span>Инвестировано</span>
              <strong class="tabular-nums">{{ formatAggregateAmount('capital_in', 'USD') }}</strong>
            </div>
            <div class="metric">
              <span>Чистый капитал</span>
              <strong class="tabular-nums">{{ formatAggregateAmount('capital_net', 'USD') }}</strong>
            </div>
            <div class="metric">
              <span>Прибыль</span>
              <strong class="tabular-nums positive">{{ formatAggregateAmount('profit_accrued', 'UZS') }}</strong>
            </div>
            <div class="metric">
              <span>Убытки</span>
              <strong class="tabular-nums negative">{{ formatAggregateAmount('losses_incurred', 'UZS') }}</strong>
            </div>
            <div class="metric">
              <span>Дивиденды</span>
              <strong class="tabular-nums">{{ formatAggregateAmount('dividends_paid', 'USD') }}</strong>
            </div>
          </div>
        </section>

        <section class="card">
          <h2 class="section-title">Капитал по этому приходу</h2>
          <div class="metrics-grid">
            <div class="metric">
              <span>Продано по себестоимости</span>
              <strong class="tabular-nums">{{ formatCapitalState('sold_cost_uzs') }}</strong>
            </div>
            <div class="metric">
              <span>Осталось в товаре</span>
              <strong class="tabular-nums">{{ formatCapitalState('in_stock_cost_uzs') }}</strong>
            </div>
            <div class="metric">
              <span>Всего отслеживается</span>
              <strong class="tabular-nums">{{ formatCapitalState('tracked_cost_uzs') }}</strong>
            </div>
            <div class="metric">
              <span>Выручка по проданному</span>
              <strong class="tabular-nums">{{ formatCapitalState('sold_revenue_uzs') }}</strong>
            </div>
            <div class="metric">
              <span>Прогноз выручки по остатку</span>
              <strong class="tabular-nums">{{ formatCapitalState('projected_revenue_uzs') }}</strong>
            </div>
            <div class="metric">
              <span>Прогноз прибыли инвестора</span>
              <strong class="tabular-nums positive">{{ formatCapitalState('projected_partner_profit_uzs') }}</strong>
            </div>
          </div>
        </section>

        <section class="card">
          <h2 class="section-title">История записей</h2>
          <div v-if="procurement.investor_ledger.entries.length === 0" class="empty-text">
            Записей по договору пока нет.
          </div>
          <article v-for="entry in procurement.investor_ledger.entries" :key="entry.id" class="record-row">
            <div class="record-main">
              <strong>{{ entryLabel(entry) }}</strong>
              <span class="record-date">{{ formatDateTime(entry.date) }}</span>
              <span v-if="entry.source_ref" class="record-description">{{ entry.source_ref }}</span>
            </div>
            <span class="record-amount tabular-nums" :class="entryClass(entry)">
              {{ formatPrice(entry.amount, entry.currency) }}
            </span>
          </article>
        </section>
      </template>

      <div v-else class="error-box">Приход не найден или недоступен.</div>
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
