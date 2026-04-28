<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Wallet, Landmark, TrendingUp, ChevronRight, RefreshCcw, Settings } from 'lucide-vue-next'
import { formatPrice } from '@/utils/currency'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import {
  fetchInvestorAgreements,
  fetchInvestorDashboard,
  fetchInvestorProcurements,
  type InvestorAgreementListItem,
} from '@/api/investors'
import type { InvestorDashboardAggregate, InvestorLedgerTotals, InvestorProcurementListItem } from '@/types/models'

const router = useRouter()
const toast = useToast()
const auth = useAuthStore()

const aggregate = ref<InvestorDashboardAggregate | null>(null)
const agreements = ref<InvestorAgreementListItem[]>([])
const procurements = ref<InvestorProcurementListItem[]>([])
const isLoading = ref(true)
const errorMessage = ref('')
const hasActiveBusinessLink = computed(() => auth.tenantId !== null)

type LedgerAmountKey = keyof InvestorLedgerTotals

const currencyPriority = ['USD', 'UZS']

function nonZero(value: string | undefined): boolean {
  return Math.abs(Number.parseFloat(value ?? '0')) > 0.000001
}

function formatAggregateAmount(
  field: LedgerAmountKey,
  preferredCurrency?: string,
): string {
  const summary = aggregate.value
  if (!summary) return formatPrice('0', 'UZS')

  const currencies = Object.keys(summary.by_currency ?? {}).sort((a, b) => {
    const aIndex = currencyPriority.indexOf(a)
    const bIndex = currencyPriority.indexOf(b)
    return (aIndex === -1 ? 99 : aIndex) - (bIndex === -1 ? 99 : bIndex)
  })

  if (preferredCurrency && nonZero(summary.by_currency?.[preferredCurrency]?.[field])) {
    return formatPrice(summary.by_currency[preferredCurrency][field], preferredCurrency)
  }

  const parts = currencies
    .map((currency) => ({ currency, amount: summary.by_currency[currency][field] }))
    .filter(({ amount }) => nonZero(amount))

  if (parts.length === 0) {
    return formatPrice(summary.functional_uzs?.[field] ?? '0', 'UZS')
  }

  return parts
    .map(({ currency, amount }) => formatPrice(amount, currency))
    .join(' + ')
}

function formatFunctionalAmount(field: LedgerAmountKey): string {
  return formatPrice(aggregate.value?.functional_uzs?.[field] ?? '0', 'UZS')
}

function formatCapitalState(field: keyof InvestorDashboardAggregate['capital_state']): string {
  return formatPrice(aggregate.value?.capital_state?.[field] ?? '0', 'UZS')
}

function procurementTypeLabel(type: string): string {
  if (type === 'PARTNERSHIP') return 'Партнёрский'
  if (type === 'MUSHARAKA') return 'Мушарака'
  return type
}

function procurementStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    OPEN: 'Открыт',
    PARTIALLY_RECEIVED: 'Частично',
    RECEIVED: 'Завершён',
    CLOSED: 'Закрыт',
    CANCELLED: 'Отменён',
  }
  return labels[status] ?? status
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

async function loadDashboard(): Promise<void> {
  if (!hasActiveBusinessLink.value) {
    aggregate.value = null
    agreements.value = []
    procurements.value = []
    errorMessage.value = ''
    isLoading.value = false
    return
  }

  isLoading.value = true
  errorMessage.value = ''
  try {
    const [summary, agreementRows, procurementRows] = await Promise.all([
      fetchInvestorDashboard(),
      fetchInvestorAgreements(),
      fetchInvestorProcurements(),
    ])
    aggregate.value = summary
    agreements.value = agreementRows
    procurements.value = procurementRows
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить кабинет инвестора'
    toast.error('Ошибка загрузки кабинета инвестора')
  } finally {
    isLoading.value = false
  }
}

function openProcurement(procurementId: number): void {
  router.push({ name: 'investor-procurement', params: { id: procurementId } })
}

function openAgreement(agreementId: number): void {
  router.push({ name: 'investor-agreement', params: { id: agreementId } })
}

function agreementBalanceLabel(agreement: InvestorAgreementListItem): string {
  const parts = Object.entries(agreement.balances ?? {})
    .filter(([, amount]) => Math.abs(Number(amount || 0)) > 0.000001)
    .map(([currency, amount]) => formatPrice(amount, currency))
  return parts.length ? parts.join(' · ') : '0'
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

      <section v-else-if="!hasActiveBusinessLink" class="card onboarding-card">
        <h2 class="section-title">Кабинет пока не подключён</h2>
        <p class="empty-text">
          Этот аккаунт инвестора ещё не связан ни с одним бизнесом.
          Откройте ссылку-приглашение от owner и примите её из текущего аккаунта.
        </p>
      </section>

      <template v-else>
        <section class="stats-grid">
          <article class="stat-card">
            <Wallet :size="18" :stroke-width="1.75" />
            <span class="stat-label">Инвестировано</span>
            <strong class="stat-value tabular-nums">{{ formatAggregateAmount('capital_in', 'USD') }}</strong>
          </article>
          <article class="stat-card">
            <TrendingUp :size="18" :stroke-width="1.75" />
            <span class="stat-label">Накопленная прибыль</span>
            <strong class="stat-value tabular-nums">{{ formatAggregateAmount('profit_accrued', 'UZS') }}</strong>
          </article>
          <article class="stat-card">
            <Landmark :size="18" :stroke-width="1.75" />
            <span class="stat-label">Бизнес должен</span>
            <strong class="stat-value tabular-nums">{{ formatFunctionalAmount('profit_pending_payout') }}</strong>
          </article>
        </section>

        <section class="card">
          <h2 class="section-title">Мои инвестдоговоры</h2>
          <div v-if="agreements.length === 0" class="empty-text">
            Инвестдоговоров с вашим участием пока нет.
          </div>
          <button
            v-for="agreement in agreements"
            v-else
            :key="agreement.id"
            class="contract-row"
            type="button"
            @click="openAgreement(agreement.id)"
          >
            <div class="contract-main">
              <strong class="contract-title">Инвестдоговор #{{ agreement.id }}</strong>
              <span class="contract-meta">
                {{ agreement.supplier_name || 'Без поставщика' }} · {{ agreement.procurements_count }} приход.
              </span>
            </div>
            <div class="contract-right">
              <span class="contract-amount">{{ agreementBalanceLabel(agreement) }}</span>
              <ChevronRight :size="16" :stroke-width="2" />
            </div>
          </button>
        </section>

        <section class="card">
          <h2 class="section-title">Мои приходы</h2>
          <div v-if="procurements.length === 0" class="empty-text">
            Приходов с вашим участием пока нет.
          </div>
          <button
            v-for="procurement in procurements"
            v-else
            :key="procurement.id"
            class="contract-row"
            type="button"
            @click="openProcurement(procurement.id)"
          >
            <div class="contract-main">
              <strong class="contract-title">
                {{ procurementTypeLabel(procurement.procurement_type) }} #{{ procurement.id }}
              </strong>
              <span class="contract-meta">
                {{ procurement.supplier_name || 'Без поставщика' }} · {{ formatDate(procurement.opened_at) }}
              </span>
            </div>
            <div class="contract-right">
              <span class="contract-amount">{{ procurementStatusLabel(procurement.status) }}</span>
              <ChevronRight :size="16" :stroke-width="2" />
            </div>
          </button>
        </section>

        <section class="card">
          <h2 class="section-title">Баланс</h2>
          <article class="record-row">
            <div class="record-main">
              <strong class="record-title">Чистый капитал</strong>
              <span class="record-date">Внос минус возврат капитала</span>
            </div>
            <span class="record-amount tabular-nums">{{ formatAggregateAmount('capital_net', 'USD') }}</span>
          </article>
          <article class="record-row">
            <div class="record-main">
              <strong class="record-title">Выплачено дивидендов</strong>
              <span class="record-date">Фактические выплаты</span>
            </div>
            <span class="record-amount tabular-nums">{{ formatAggregateAmount('dividends_paid', 'USD') }}</span>
          </article>
        </section>

        <section class="card">
          <h2 class="section-title">Капитал в товаре</h2>
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

.onboarding-card {
  display: grid;
  gap: var(--space-2);
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
