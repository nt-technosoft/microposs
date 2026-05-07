<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
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
import { useFxRate } from '@/composables/useFxRate'
import { useToast } from '@/composables/useToast'
import { useAuthStore } from '@/stores/auth'
import type { InvestorDashboardAggregate, InvestorProcurementListItem } from '@/types/models'
import {
  agreementStatusLabel,
  agreementStatusTone,
  formatBalanceLabel,
  formatShortDate,
  procurementStatusLabel,
  procurementStatusTone,
  procurementTypeLabel,
} from '@/modules/investors/presentation'
import { formatPrice } from '@/utils/currency'

type DashboardMode = 'overview' | 'procurements' | 'agreements'
type ReportCurrency = 'UZS' | 'USD'

const router = useRouter()
const route = useRoute()
const toast = useToast()
const auth = useAuthStore()
const { t } = useI18n()
const {
  rate: latestUsdRate,
  error: latestUsdRateError,
  load: loadLatestUsdRate,
} = useFxRate()

const aggregate = ref<InvestorDashboardAggregate | null>(null)
const agreements = ref<InvestorAgreementListItem[]>([])
const procurements = ref<InvestorProcurementListItem[]>([])
const isLoading = ref(true)
const errorMessage = ref('')
const reportCurrency = ref<ReportCurrency>('USD')

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
      kicker: t('investors.heroAgreementsKicker'),
      title: t('investors.heroAgreementsTitle'),
      amount: formatLedgerTotal('capital_net'),
      foot: t('investors.heroAgreementsFoot', {
        count: activeAgreementCount.value,
        amount: formatLedgerTotal('profit_accrued'),
      }),
    }
  }

  if (dashboardMode.value === 'procurements') {
    return {
      kicker: t('investors.heroProcurementsKicker'),
      title: t('investors.heroProcurementsTitle'),
      amount: formatCapitalState('tracked_cost_uzs'),
      foot: t('investors.heroProcurementsFoot', {
        count: procurements.value.length,
        amount: formatCapitalState('projected_partner_profit_uzs'),
      }),
    }
  }

  return {
    kicker: t('investors.heroOverviewKicker'),
    title: t('investors.heroOverviewTitle'),
    amount: formatLedgerTotal('profit_pending_payout'),
    foot: t('investors.accruedPaid', {
      accrued: formatLedgerTotal('profit_accrued'),
      paid: formatLedgerTotal('dividends_paid'),
    }),
  }
})

const summaryStats = computed(() => [
  {
    label: t('investors.pendingPayout'),
    value: formatLedgerTotal('profit_pending_payout'),
    hint: t('investors.businessOwesNow'),
    accent: true,
  },
  {
    label: t('investors.contributed'),
    value: formatLedgerTotal('capital_in'),
    hint: t('investors.allCapitalContributions'),
  },
  {
    label: t('investors.inGoods'),
    value: formatCapitalState('tracked_cost_uzs'),
    hint: t('investors.capitalStillInStock'),
  },
  {
    label: t('investors.investorForecast'),
    value: formatCapitalState('projected_partner_profit_uzs'),
    hint: t('investors.expectedProfitOnRemaining'),
  },
])

function formatCapitalState(field: keyof InvestorDashboardAggregate['capital_state']): string {
  return formatReportPrice(aggregate.value?.capital_state?.[field] ?? '0')
}

function reportNumberFromUzs(value: string | number | null | undefined): number {
  const amount = Number.parseFloat(String(value ?? '0'))
  if (!Number.isFinite(amount)) return 0
  if (reportCurrency.value === 'UZS') return amount
  const fx = Number.parseFloat(latestUsdRate.value || '0')
  return Number.isFinite(fx) && fx > 0 ? amount / fx : amount
}

function formatReportPrice(value: string | number | null | undefined): string {
  return formatPrice(reportNumberFromUzs(value), reportCurrency.value)
}

function formatLedgerTotal(field: keyof InvestorDashboardAggregate['functional_uzs']): string {
  return formatReportPrice(aggregate.value?.functional_uzs?.[field] ?? '0')
}

async function setReportCurrency(currency: ReportCurrency): Promise<void> {
  if (reportCurrency.value === currency) return
  reportCurrency.value = currency
  if (currency === 'USD' && !latestUsdRate.value) {
    try {
      await loadLatestUsdRate()
    } catch {
      reportCurrency.value = 'UZS'
      toast.error(latestUsdRateError.value || t('procurements.syncUsdRateFirst'))
    }
  }
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
    agreement.supplier_name || t('procurements.supplierMissing'),
    formatShortDate(agreement.opened_at),
    t('investors.procurementsCount', { count: agreement.procurements_count }),
  ].join(' · ')
}

function procurementMeta(procurement: InvestorProcurementListItem): string {
  return [
    procurement.supplier_name || t('procurements.supplierMissing'),
    procurement.received_at
      ? t('investors.receivedAt', { date: formatShortDate(procurement.received_at) })
      : t('investors.openedAt', { date: formatShortDate(procurement.opened_at) }),
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
    if (reportCurrency.value === 'USD' && !latestUsdRate.value) {
      try {
        await loadLatestUsdRate()
      } catch {
        reportCurrency.value = 'UZS'
      }
    }
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : t('investors.dashboardLoadFailed')
    toast.error(t('investors.dashboardLoadError'))
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
        <strong class="investor-header__title">{{ t('investors.dashboard') }}</strong>
        <span class="investor-header__caption">
          {{ dashboardMode === 'overview'
            ? t('investors.overviewCaption')
            : dashboardMode === 'agreements'
              ? t('investors.agreementsCaption')
              : t('investors.procurementsCaption') }}
        </span>
      </div>
      <div class="investor-header__actions">
        <button type="button" :aria-label="t('nav.settings')" @click="openSettings">
          <Settings :size="16" :stroke-width="1.75" />
        </button>
        <button type="button" :aria-label="t('common.refresh')" @click="loadDashboard">
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
        <strong>{{ t('investors.notConnectedTitle') }}</strong>
        <p>
          {{ t('investors.notConnectedText') }}
        </p>
      </section>

      <template v-else>
        <section class="investor-hero">
          <div class="investor-hero__copy">
            <span class="investor-hero__kicker">{{ heroConfig.kicker }}</span>
            <h1 class="investor-hero__title">{{ heroConfig.title }}</h1>
            <div class="investor-hero__meta">
              <span class="investor-chip investor-chip--glass">{{ t('investors.linkActive') }}</span>
              <span class="investor-chip investor-chip--glass">{{ t('investors.agreementsCount', { count: agreements.length }) }}</span>
              <span class="investor-chip investor-chip--glass">{{ t('investors.procurementsCount', { count: procurements.length }) }}</span>
            </div>
          </div>

          <div class="investor-hero__value">
            <div class="investor-currency-switch" role="group" :aria-label="t('investors.metricCurrency')">
              <button type="button" :class="{ active: reportCurrency === 'UZS' }" @click="setReportCurrency('UZS')">UZS</button>
              <button type="button" :class="{ active: reportCurrency === 'USD' }" @click="setReportCurrency('USD')">USD</button>
            </div>
            <strong class="investor-hero__amount tabular-nums">{{ heroConfig.amount }}</strong>
            <span class="investor-hero__foot">{{ heroConfig.foot }}</span>
          </div>
        </section>

        <nav class="investor-segments" :aria-label="t('investors.dashboardSections')">
          <button
            type="button"
            class="investor-segment"
            :class="{ 'is-active': dashboardMode === 'overview' }"
            @click="openDashboardMode('overview')"
          >
            {{ t('reports.overview') }}
          </button>
          <button
            type="button"
            class="investor-segment"
            :class="{ 'is-active': dashboardMode === 'agreements' }"
            @click="openDashboardMode('agreements')"
          >
            {{ t('procurements.agreements') }}
          </button>
          <button
            type="button"
            class="investor-segment"
            :class="{ 'is-active': dashboardMode === 'procurements' }"
            @click="openDashboardMode('procurements')"
          >
            {{ t('procurements.title') }}
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
              <h2 class="investor-panel__title">{{ t('investors.myAgreements') }}</h2>
              <p class="investor-panel__hint">
                {{ t('investors.myAgreementsHint') }}
              </p>
            </div>
            <span class="investor-panel__icon">
              <ScrollText :size="18" :stroke-width="2" />
            </span>
          </div>

          <div v-if="previewAgreements.length === 0" class="investor-empty">
            {{ t('investors.noMyAgreements') }}
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
                  <strong class="investor-list-row__title">{{ t('investors.agreementNumber', { id: agreement.id }) }}</strong>
                  <span class="investor-chip" :class="`investor-chip--${agreementStatusTone(agreement.status)}`">
                    {{ agreementStatusLabel(agreement.status) }}
                  </span>
                </div>
                <span class="investor-list-row__meta">{{ agreementMeta(agreement) }}</span>
              </div>

              <div class="investor-list-row__side dashboard-row-side">
                <div class="dashboard-row-side__copy">
                  <span class="investor-list-row__value tabular-nums">{{ formatBalanceLabel(agreement.balances) }}</span>
                  <span class="investor-list-row__caption">{{ t('investors.agreementBalance') }}</span>
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
            {{ t('investors.allAgreements') }}
            <ChevronRight :size="16" :stroke-width="1.9" />
          </button>
        </section>

        <section
          v-if="dashboardMode !== 'agreements'"
          class="investor-panel"
        >
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">{{ t('investors.myProcurements') }}</h2>
              <p class="investor-panel__hint">
                {{ t('investors.myProcurementsHint') }}
              </p>
            </div>
            <span class="investor-panel__icon">
              <PackageSearch :size="18" :stroke-width="2" />
            </span>
          </div>

          <div v-if="previewProcurements.length === 0" class="investor-empty">
            {{ t('investors.noMyProcurements') }}
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
                  <span class="investor-list-row__value">{{ t('common.details') }}</span>
                  <span class="investor-list-row__caption">
                    {{ procurement.received_at ? t('investors.goodsMoved') : t('investors.procurementInProgress') }}
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
            {{ t('investors.allProcurements') }}
            <ChevronRight :size="16" :stroke-width="1.9" />
          </button>
        </section>

        <section
          v-if="dashboardMode !== 'agreements'"
          class="investor-panel"
        >
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">{{ t('investors.capitalInGoods') }}</h2>
              <p class="investor-panel__hint">
                {{ t('investors.capitalInGoodsHint') }}
              </p>
            </div>
            <span class="investor-panel__icon">
              <Scale :size="18" :stroke-width="2" />
            </span>
          </div>

          <div class="investor-grid-2">
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.soldByCost') }}</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatCapitalState('sold_cost_uzs') }}</strong>
              <span class="investor-detail-card__hint">{{ t('investors.soldByCostHint') }}</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.remainingInGoods') }}</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatCapitalState('in_stock_cost_uzs') }}</strong>
              <span class="investor-detail-card__hint">{{ t('investors.remainingInGoodsHint') }}</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.revenueOnSold') }}</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatCapitalState('sold_revenue_uzs') }}</strong>
              <span class="investor-detail-card__hint">{{ t('investors.revenueOnSoldHint') }}</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.revenueForecast') }}</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatCapitalState('projected_revenue_uzs') }}</strong>
              <span class="investor-detail-card__hint">{{ t('investors.revenueForecastHint') }}</span>
            </article>
          </div>
        </section>

        <section
          v-if="dashboardMode !== 'procurements'"
          class="investor-panel"
        >
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">{{ t('investors.payoutsAndNet') }}</h2>
              <p class="investor-panel__hint">
                {{ t('investors.payoutsAndNetHint') }}
              </p>
            </div>
            <span class="investor-panel__icon">
              <Landmark :size="18" :stroke-width="2" />
            </span>
          </div>

          <div class="investor-grid-2">
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.netCapital') }}</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatLedgerTotal('capital_net') }}</strong>
              <span class="investor-detail-card__hint">{{ t('investors.netCapitalHint') }}</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.accruedProfit') }}</span>
              <strong class="investor-detail-card__value tabular-nums investor-positive">{{ formatLedgerTotal('profit_accrued') }}</strong>
              <span class="investor-detail-card__hint">{{ t('investors.accruedProfitHint') }}</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.reversedByReturns') }}</span>
              <strong class="investor-detail-card__value tabular-nums investor-negative">{{ formatLedgerTotal('profit_reversed') }}</strong>
              <span class="investor-detail-card__hint">{{ t('investors.reversedByReturnsHint') }}</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.writeoffLosses') }}</span>
              <strong class="investor-detail-card__value tabular-nums investor-negative">{{ formatLedgerTotal('losses_incurred') }}</strong>
              <span class="investor-detail-card__hint">{{ t('investors.writeoffLossesHint') }}</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.dividendsPaid') }}</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatLedgerTotal('dividends_paid') }}</strong>
              <span class="investor-detail-card__hint">{{ t('investors.dividendsPaidHint') }}</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.businessOwes') }}</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatLedgerTotal('profit_pending_payout') }}</strong>
              <span class="investor-detail-card__hint">{{ t('investors.businessOwesHint') }}</span>
            </article>
          </div>
        </section>

        <section v-if="dashboardMode === 'overview'" class="investor-panel">
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">{{ t('investors.firstLookTitle') }}</h2>
            </div>
            <span class="investor-panel__icon">
              <TrendingUp :size="18" :stroke-width="2" />
            </span>
          </div>
          <p class="investor-note">
            {{ t('investors.firstLookText') }}
          </p>
          <button type="button" class="investor-link-button" @click="openDashboardMode('procurements')">
            {{ t('investors.goToProcurements') }}
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

.investor-currency-switch {
  justify-self: end;
  display: inline-grid;
  grid-template-columns: repeat(2, minmax(44px, 1fr));
  padding: 3px;
  border-radius: 999px;
  background: color-mix(in srgb, white 18%, transparent);
  border: 1px solid color-mix(in srgb, white 16%, transparent);
}

.investor-currency-switch button {
  min-height: 28px;
  padding: 0 var(--space-2);
  border-radius: 999px;
  color: color-mix(in srgb, white 78%, transparent);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.investor-currency-switch button.active {
  background: white;
  color: var(--color-brand-800);
}

@media (max-width: 420px) {
  .dashboard-row-side {
    grid-template-columns: 1fr;
    justify-items: end;
  }

  .dashboard-row-side .investor-list-row__chevron {
    display: none;
  }

  .investor-currency-switch {
    justify-self: stretch;
    width: 100%;
  }
}
</style>
