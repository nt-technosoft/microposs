<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ChevronRight,
  Landmark,
  PackageSearch,
  RefreshCcw,
  Scale,
  ScrollText,
  Settings,
  TrendingUp,
} from 'lucide-vue-next'

import {
  fetchInvestorAgreements,
  fetchInvestorDashboard,
  fetchInvestorProcurements,
  type InvestorAgreementListItem,
} from '@/api/investors'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import type { InvestorDashboardAggregate, InvestorProcurementListItem } from '@/types/models'
import {
  agreementStatusLabel,
  agreementStatusTone,
  formatAggregateAmount,
  formatBalanceLabel,
  formatFunctionalAmount,
  formatShortDate,
  procurementStatusLabel,
  procurementStatusTone,
  procurementTypeLabel,
} from '@/modules/investors/presentation'
import { formatPrice } from '@/utils/currency'

type DashboardMode = 'overview' | 'procurements' | 'agreements'

const router = useRouter()
const route = useRoute()
const toast = useToast()
const auth = useAuthStore()

const aggregate = ref<InvestorDashboardAggregate | null>(null)
const agreements = ref<InvestorAgreementListItem[]>([])
const procurements = ref<InvestorProcurementListItem[]>([])
const isLoading = ref(true)
const errorMessage = ref('')

const hasActiveBusinessLink = computed(() => auth.tenantId !== null)
const dashboardMode = computed<DashboardMode>(() => {
  if (route.name === 'investor-procurements') return 'procurements'
  if (route.name === 'investor-agreements') return 'agreements'
  return 'overview'
})

const activeAgreementCount = computed(() =>
  agreements.value.filter((agreement) => agreementStatusTone(agreement.status) === 'success').length,
)

const previewAgreements = computed(() =>
  dashboardMode.value === 'overview' ? agreements.value.slice(0, 3) : agreements.value,
)

const previewProcurements = computed(() =>
  dashboardMode.value === 'overview' ? procurements.value.slice(0, 4) : procurements.value,
)

const heroConfig = computed(() => {
  if (dashboardMode.value === 'agreements') {
    return {
      kicker: 'Связанные инвестдоговоры',
      title: 'Баланс, распределение и остаток по каждому договору.',
      amount: formatAggregateAmount(aggregate.value, 'capital_net', 'USD'),
      foot: `${activeAgreementCount.value} активн. · начислено ${formatAggregateAmount(aggregate.value, 'profit_accrued', 'UZS')}`,
    }
  }

  if (dashboardMode.value === 'procurements') {
    return {
      kicker: 'Связанные приходы',
      title: 'Смотрите, где ваш капитал уже продан, а где ещё лежит в товаре.',
      amount: formatCapitalState('tracked_cost_uzs'),
      foot: `${procurements.value.length} приходов · прогноз ${formatCapitalState('projected_partner_profit_uzs')}`,
    }
  }

  return {
    kicker: 'Общий обзор',
    title: 'Один экран для капитала, прибыли и всех связанных приходов.',
    amount: formatFunctionalAmount(aggregate.value, 'profit_pending_payout'),
    foot: `Начислено ${formatAggregateAmount(aggregate.value, 'profit_accrued', 'UZS')} · выплачено ${formatAggregateAmount(aggregate.value, 'dividends_paid', 'USD')}`,
  }
})

const summaryStats = computed(() => [
  {
    label: 'К выплате',
    value: formatFunctionalAmount(aggregate.value, 'profit_pending_payout'),
    hint: 'Что бизнес должен сейчас',
    accent: true,
  },
  {
    label: 'Вложено',
    value: formatAggregateAmount(aggregate.value, 'capital_in', 'USD'),
    hint: 'Все вносы капитала',
  },
  {
    label: 'В товаре',
    value: formatCapitalState('tracked_cost_uzs'),
    hint: 'Capital still tracked in stock',
  },
  {
    label: 'Прогноз инвестора',
    value: formatCapitalState('projected_partner_profit_uzs'),
    hint: 'Potential profit on remaining goods',
  },
])

function formatCapitalState(field: keyof InvestorDashboardAggregate['capital_state']): string {
  return formatPrice(aggregate.value?.capital_state?.[field] ?? '0', 'UZS')
}

function openDashboardMode(mode: DashboardMode): void {
  if (mode === dashboardMode.value) return
  const name = mode === 'overview'
    ? 'investor-dashboard'
    : mode === 'agreements'
      ? 'investor-agreements'
      : 'investor-procurements'
  router.push({ name })
}

function openProcurement(procurementId: number): void {
  router.push({ name: 'investor-procurement', params: { id: procurementId } })
}

function openAgreement(agreementId: number): void {
  router.push({ name: 'investor-agreement', params: { id: agreementId } })
}

function openSettings(): void {
  router.push({ name: 'settings' })
}

function agreementMeta(agreement: InvestorAgreementListItem): string {
  return [
    agreement.supplier_name || 'Без поставщика',
    formatShortDate(agreement.opened_at),
    `${agreement.procurements_count} приход.`,
  ].join(' · ')
}

function procurementMeta(procurement: InvestorProcurementListItem): string {
  return [
    procurement.supplier_name || 'Без поставщика',
    procurement.received_at ? `Принят ${formatShortDate(procurement.received_at)}` : `Открыт ${formatShortDate(procurement.opened_at)}`,
  ].join(' · ')
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

onMounted(loadDashboard)
</script>

<template>
  <div class="investor-shell">
    <header class="investor-header investor-header--actions">
      <div class="investor-header__copy">
        <strong class="investor-header__title">Кабинет инвестора</strong>
        <span class="investor-header__caption">
          {{ dashboardMode === 'overview' ? 'Общий обзор капитала' : dashboardMode === 'agreements' ? 'Договоры и распределение' : 'Приходы и капитал в товаре' }}
        </span>
      </div>
      <div class="investor-header__actions">
        <button type="button" aria-label="Настройки" @click="openSettings">
          <Settings :size="16" :stroke-width="1.75" />
        </button>
        <button type="button" aria-label="Обновить" @click="loadDashboard">
          <RefreshCcw :size="16" :stroke-width="1.75" />
        </button>
      </div>
    </header>

    <main class="investor-content">
      <template v-if="isLoading">
        <div class="investor-hero investor-skeleton skeleton" aria-hidden="true" />
        <div class="investor-summary-band">
          <div class="investor-summary-stat investor-skeleton skeleton" />
          <div class="investor-summary-stat investor-skeleton skeleton" />
          <div class="investor-summary-stat investor-skeleton skeleton" />
          <div class="investor-summary-stat investor-skeleton skeleton" />
        </div>
      </template>

      <section v-else-if="errorMessage" class="investor-state investor-state--error" role="alert">
        <p>{{ errorMessage }}</p>
      </section>

      <section v-else-if="!hasActiveBusinessLink" class="investor-state">
        <strong>Кабинет пока не подключён</strong>
        <p>
          Этот investor-аккаунт ещё не связан ни с одним бизнесом.
          Откройте invite-ссылку от owner и примите её из текущего аккаунта.
        </p>
      </section>

      <template v-else>
        <section class="investor-hero">
          <div class="investor-hero__copy">
            <span class="investor-hero__kicker">{{ heroConfig.kicker }}</span>
            <h1 class="investor-hero__title">{{ heroConfig.title }}</h1>
            <div class="investor-hero__meta">
              <span class="investor-chip investor-chip--glass">Связь активна</span>
              <span class="investor-chip investor-chip--glass">{{ agreements.length }} договоров</span>
              <span class="investor-chip investor-chip--glass">{{ procurements.length }} приходов</span>
            </div>
          </div>

          <div class="investor-hero__value">
            <strong class="investor-hero__amount tabular-nums">{{ heroConfig.amount }}</strong>
            <span class="investor-hero__foot">{{ heroConfig.foot }}</span>
          </div>
        </section>

        <nav class="investor-segments" aria-label="Разделы кабинета инвестора">
          <button
            type="button"
            class="investor-segment"
            :class="{ 'is-active': dashboardMode === 'overview' }"
            @click="openDashboardMode('overview')"
          >
            Обзор
          </button>
          <button
            type="button"
            class="investor-segment"
            :class="{ 'is-active': dashboardMode === 'agreements' }"
            @click="openDashboardMode('agreements')"
          >
            Договоры
          </button>
          <button
            type="button"
            class="investor-segment"
            :class="{ 'is-active': dashboardMode === 'procurements' }"
            @click="openDashboardMode('procurements')"
          >
            Приходы
          </button>
        </nav>

        <section class="investor-summary-band">
          <article
            v-for="stat in summaryStats"
            :key="stat.label"
            class="investor-summary-stat"
            :class="{ 'investor-summary-stat--accent': stat.accent }"
          >
            <span class="investor-summary-stat__label">{{ stat.label }}</span>
            <strong class="investor-summary-stat__value tabular-nums">{{ stat.value }}</strong>
            <span class="investor-summary-stat__hint">{{ stat.hint }}</span>
          </article>
        </section>

        <section
          v-if="dashboardMode !== 'procurements'"
          class="investor-panel"
        >
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">Мои договоры</h2>
              <p class="investor-panel__hint">
                Каждый договор показывает общий баланс, поставщика и сколько приходов уже отработало по этой связке.
              </p>
            </div>
            <span class="investor-panel__icon">
              <ScrollText :size="18" :stroke-width="2" />
            </span>
          </div>

          <div v-if="previewAgreements.length === 0" class="investor-empty">
            Инвестдоговоров с вашим участием пока нет.
          </div>

          <div v-else class="investor-list">
            <button
              v-for="agreement in previewAgreements"
              :key="agreement.id"
              type="button"
              class="investor-list-row"
              @click="openAgreement(agreement.id)"
            >
              <div class="investor-list-row__main">
                <div class="dashboard-row-head">
                  <strong class="investor-list-row__title">Договор #{{ agreement.id }}</strong>
                  <span class="investor-chip" :class="`investor-chip--${agreementStatusTone(agreement.status)}`">
                    {{ agreementStatusLabel(agreement.status) }}
                  </span>
                </div>
                <span class="investor-list-row__meta">{{ agreementMeta(agreement) }}</span>
              </div>

              <div class="investor-list-row__side dashboard-row-side">
                <div class="dashboard-row-side__copy">
                  <span class="investor-list-row__value tabular-nums">{{ formatBalanceLabel(agreement.balances) }}</span>
                  <span class="investor-list-row__caption">Баланс договора</span>
                </div>
                <ChevronRight class="investor-list-row__chevron" :size="16" :stroke-width="1.9" />
              </div>
            </button>
          </div>

          <button
            v-if="dashboardMode === 'overview' && agreements.length > previewAgreements.length"
            type="button"
            class="investor-inline-button"
            @click="openDashboardMode('agreements')"
          >
            Все договоры
            <ChevronRight :size="16" :stroke-width="1.9" />
          </button>
        </section>

        <section
          v-if="dashboardMode !== 'agreements'"
          class="investor-panel"
        >
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">Мои приходы</h2>
              <p class="investor-panel__hint">
                Здесь видно, в каких приходах сейчас лежит капитал, а какие уже закрыли часть прибыли через продажи.
              </p>
            </div>
            <span class="investor-panel__icon">
              <PackageSearch :size="18" :stroke-width="2" />
            </span>
          </div>

          <div v-if="previewProcurements.length === 0" class="investor-empty">
            Приходов с вашим участием пока нет.
          </div>

          <div v-else class="investor-list">
            <button
              v-for="procurement in previewProcurements"
              :key="procurement.id"
              type="button"
              class="investor-list-row"
              @click="openProcurement(procurement.id)"
            >
              <div class="investor-list-row__main">
                <div class="dashboard-row-head">
                  <strong class="investor-list-row__title">
                    {{ procurementTypeLabel(procurement.procurement_type) }} #{{ procurement.id }}
                  </strong>
                  <span class="investor-chip" :class="`investor-chip--${procurementStatusTone(procurement.status)}`">
                    {{ procurementStatusLabel(procurement.status) }}
                  </span>
                </div>
                <span class="investor-list-row__meta">{{ procurementMeta(procurement) }}</span>
              </div>

              <div class="investor-list-row__side dashboard-row-side">
                <div class="dashboard-row-side__copy">
                  <span class="investor-list-row__value">Открыть</span>
                  <span class="investor-list-row__caption">
                    {{ procurement.received_at ? 'Есть движение по товару' : 'В процессе закупки' }}
                  </span>
                </div>
                <ChevronRight class="investor-list-row__chevron" :size="16" :stroke-width="1.9" />
              </div>
            </button>
          </div>

          <button
            v-if="dashboardMode === 'overview' && procurements.length > previewProcurements.length"
            type="button"
            class="investor-inline-button"
            @click="openDashboardMode('procurements')"
          >
            Все приходы
            <ChevronRight :size="16" :stroke-width="1.9" />
          </button>
        </section>

        <section
          v-if="dashboardMode !== 'agreements'"
          class="investor-panel"
        >
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">Капитал в товаре</h2>
              <p class="investor-panel__hint">
                Срез по себестоимости и прогнозной выручке помогает быстро понять, сколько капитала уже вернулось, а сколько ещё работает на полке.
              </p>
            </div>
            <span class="investor-panel__icon">
              <Scale :size="18" :stroke-width="2" />
            </span>
          </div>

          <div class="investor-grid-2">
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Продано по себестоимости</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatCapitalState('sold_cost_uzs') }}</strong>
              <span class="investor-detail-card__hint">Часть капитала уже прошла через продажи.</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Осталось в товаре</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatCapitalState('in_stock_cost_uzs') }}</strong>
              <span class="investor-detail-card__hint">Себестоимость товаров, которые ещё лежат в остатке.</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Выручка по проданному</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatCapitalState('sold_revenue_uzs') }}</strong>
              <span class="investor-detail-card__hint">Что продажи уже принесли на этом капитале.</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Прогноз выручки</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatCapitalState('projected_revenue_uzs') }}</strong>
              <span class="investor-detail-card__hint">Потенциальная выручка, если остаток продастся по текущей цене.</span>
            </article>
          </div>
        </section>

        <section
          v-if="dashboardMode !== 'procurements'"
          class="investor-panel"
        >
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">Выплаты и чистый остаток</h2>
              <p class="investor-panel__hint">
                Быстрый cash-view по вашему кабинету без перехода в детальные отчёты.
              </p>
            </div>
            <span class="investor-panel__icon">
              <Landmark :size="18" :stroke-width="2" />
            </span>
          </div>

          <div class="investor-grid-2">
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Чистый капитал</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatAggregateAmount(aggregate, 'capital_net', 'USD') }}</strong>
              <span class="investor-detail-card__hint">Вносы минус возвраты капитала.</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Начисленная прибыль</span>
              <strong class="investor-detail-card__value tabular-nums investor-positive">{{ formatAggregateAmount(aggregate, 'profit_accrued', 'UZS') }}</strong>
              <span class="investor-detail-card__hint">Прибыль, которую система уже отнесла на вас.</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Дивиденды выплачены</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatAggregateAmount(aggregate, 'dividends_paid', 'USD') }}</strong>
              <span class="investor-detail-card__hint">Фактические выплаты, которые вы уже получили.</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Бизнес должен</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatFunctionalAmount(aggregate, 'profit_pending_payout') }}</strong>
              <span class="investor-detail-card__hint">Невыплаченная прибыль на текущий момент.</span>
            </article>
          </div>
        </section>

        <section v-if="dashboardMode === 'overview'" class="investor-panel">
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">Что смотреть в первую очередь</h2>
            </div>
            <span class="investor-panel__icon">
              <TrendingUp :size="18" :stroke-width="2" />
            </span>
          </div>
          <p class="investor-note">
            Если нужно понять, сколько можно выводить сейчас, смотрите «К выплате». Если задача понять, где застрял капитал, идите в «Приходы» и откройте конкретный приход. Если нужен контекст по договору и общему балансу, откройте «Договоры».
          </p>
          <button type="button" class="investor-link-button" @click="openDashboardMode('procurements')">
            Перейти в приходы
            <PackageSearch :size="16" :stroke-width="1.9" />
          </button>
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped>
.dashboard-row-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.dashboard-row-side {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-2);
}

.dashboard-row-side__copy {
  display: grid;
  gap: 4px;
}

@media (max-width: 420px) {
  .dashboard-row-side {
    grid-template-columns: 1fr;
    justify-items: end;
  }

  .dashboard-row-side .investor-list-row__chevron {
    display: none;
  }
}
</style>
