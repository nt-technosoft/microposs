<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ChevronDown, ChevronRight, PackageSearch, RefreshCcw, Scale, Wallet } from 'lucide-vue-next'
import { useI18n } from 'vue-i18n'

import { fetchInvestorAgreementDetail } from '@/api/investors'
import type { AgreementProfitabilityDetail } from '@/api/finance'
import {
  agreementStatusLabel,
  formatBalanceLabel,
  formatDateTime,
  formatRatioPercent,
  procurementStatusLabel,
  procurementStatusTone,
  procurementTypeLabel,
} from '@/modules/investors/presentation'
import { formatPrice } from '@/utils/currency'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const report = ref<AgreementProfitabilityDetail | null>(null)
const loading = ref(false)
const error = ref('')
const expandedProcurementId = ref<number | null>(null)
const selectedReportCurrency = ref<'UZS' | 'USD' | ''>('')

const agreementId = computed(() => Number(route.params.id))
const summary = computed(() => report.value?.agreement ?? null)
const currentPartner = computed(() =>
  report.value?.partners.find((row) => row.partner_id === report.value?.current_partner_id) ?? null,
)
const procurements = computed(() => report.value?.procurements ?? [])
const activeReportCurrency = computed(() => report.value?.report_currency?.currency ?? summary.value?.currency ?? 'UZS')

function amountNumber(value: string | number | null | undefined): number {
  const parsed = Number.parseFloat(String(value ?? '0'))
  return Number.isFinite(parsed) ? parsed : 0
}

function formatAmount(value: string | number | null | undefined, currency = 'UZS'): string {
  return formatPrice(value ?? '0', currency)
}

function formatReportAmount(
  row: { display?: { currency: string; amounts: Record<string, string> } } | null | undefined,
  key: string,
  fallback: string | number | null | undefined,
): string {
  if (row?.display?.amounts?.[key] !== undefined) {
    return formatAmount(row.display.amounts[key], row.display.currency)
  }
  return formatAmount(fallback)
}

function reportAmountNumber(
  row: { display?: { currency: string; amounts: Record<string, string> } } | null | undefined,
  key: string,
  fallback: string | number | null | undefined,
): number {
  return amountNumber(row?.display?.amounts?.[key] ?? fallback)
}

const currentPartnerNetProfit = computed(() => {
  const row = currentPartner.value
  if (!row) return formatAmount('0', activeReportCurrency.value)
  const currency = row.display?.currency ?? activeReportCurrency.value
  const net = (
    reportAmountNumber(row, 'profit_accrued', row.profit_accrued)
    - reportAmountNumber(row, 'profit_reversed', row.profit_reversed)
    - reportAmountNumber(row, 'losses_incurred', row.losses_incurred)
  )
  return formatAmount(net, currency)
})

const hasCurrentPartnerAdjustments = computed(() => {
  const row = currentPartner.value
  return Boolean(row && (
    amountNumber(row.profit_reversed) > 0
    || amountNumber(row.losses_incurred) > 0
  ))
})

function toggleProcurement(id: number): void {
  expandedProcurementId.value = expandedProcurementId.value === id ? null : id
}

function openProcurement(procurementId: number): void {
  router.push({ name: 'investor-procurement', params: { id: procurementId } })
}

async function load(): Promise<void> {
  if (!Number.isFinite(agreementId.value) || agreementId.value <= 0) {
    error.value = t('investors.invalidAgreementId')
    return
  }

  loading.value = true
  error.value = ''
  try {
    report.value = await fetchInvestorAgreementDetail(
      agreementId.value,
      selectedReportCurrency.value ? { report_currency: selectedReportCurrency.value } : undefined,
    )
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : t('investors.loadAgreementFailed')
  } finally {
    loading.value = false
  }
}

async function setReportCurrency(currency: 'UZS' | 'USD'): Promise<void> {
  if (selectedReportCurrency.value === currency && activeReportCurrency.value === currency) return
  selectedReportCurrency.value = currency
  await load()
}

onMounted(load)
</script>

<template>
  <div class="investor-shell">
    <header class="investor-header">
      <button class="investor-header__button" type="button" :aria-label="t('common.back')" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>

      <div class="investor-header__copy">
        <strong class="investor-header__title">{{ t('investors.agreementDetailTitle') }}</strong>
        <span class="investor-header__caption">{{ t('investors.agreementDetailCaption') }}</span>
      </div>

      <button class="investor-header__button" type="button" :aria-label="t('common.refresh')" @click="load">
        <RefreshCcw :size="16" :stroke-width="1.75" />
      </button>
    </header>

    <main class="investor-content">
      <template v-if="loading">
        <div class="investor-hero investor-skeleton skeleton" aria-hidden="true" />
        <div class="investor-panel investor-skeleton skeleton" />
      </template>

      <section v-else-if="error" class="investor-state investor-state--error">
        <p>{{ error }}</p>
      </section>

      <template v-else-if="summary">
        <section class="investor-hero">
          <div class="investor-hero__copy">
            <span class="investor-hero__kicker">{{ t('investors.agreementNumber', { id: summary.agreement_id }) }}</span>
            <h1 class="investor-hero__title">
              {{ summary.supplier_name || t('investors.agreementNoSupplier') }}
            </h1>
            <div class="investor-hero__meta">
              <span class="investor-chip investor-chip--glass">
                {{ agreementStatusLabel(summary.status) }}
              </span>
              <span class="investor-chip investor-chip--glass">
                {{ t('investors.openedAt', { date: formatDateTime(summary.opened_at) }) }}
              </span>
              <span class="investor-chip investor-chip--glass">
                {{ t('investors.procurementsCount', { count: summary.procurements_count }) }}
              </span>
            </div>
          </div>

          <div class="investor-hero__value">
            <div class="investor-currency-switch" role="group" :aria-label="t('investors.metricCurrency')">
              <button type="button" :class="{ active: activeReportCurrency === 'UZS' }" @click="setReportCurrency('UZS')">UZS</button>
              <button type="button" :class="{ active: activeReportCurrency === 'USD' }" @click="setReportCurrency('USD')">USD</button>
            </div>
            <strong class="investor-hero__amount tabular-nums">
              {{ formatReportAmount(currentPartner, 'profit_pending_payout', currentPartner?.profit_pending_payout ?? '0') }}
            </strong>
            <span class="investor-hero__foot">
              {{ t('investors.accruedPaid', {
                accrued: formatReportAmount(currentPartner, 'profit_accrued', currentPartner?.profit_accrued ?? '0'),
                paid: formatReportAmount(currentPartner, 'dividends_paid', currentPartner?.dividends_paid ?? '0'),
              }) }}
            </span>
          </div>
        </section>

        <section class="investor-summary-band">
          <article class="investor-summary-stat investor-summary-stat--accent">
            <span class="investor-summary-stat__label">{{ t('investors.plannedBudget') }}</span>
            <strong class="investor-summary-stat__value tabular-nums">
              {{ formatAmount(summary.planned_budget, summary.currency) }}
            </strong>
            <span class="investor-summary-stat__hint">{{ t('investors.wholeAgreementBase') }}</span>
          </article>
          <article class="investor-summary-stat">
            <span class="investor-summary-stat__label">{{ t('investors.agreementBalance') }}</span>
            <strong class="investor-summary-stat__value tabular-nums">
              {{ formatBalanceLabel(summary.balances) }}
            </strong>
            <span class="investor-summary-stat__hint">{{ t('investors.freeBalanceAllCurrencies') }}</span>
          </article>
          <article class="investor-summary-stat">
            <span class="investor-summary-stat__label">{{ t('investors.yourBalance') }}</span>
            <strong class="investor-summary-stat__value tabular-nums">
              {{ formatAmount(currentPartner?.agreement_available ?? '0', currentPartner?.agreement_currency) }}
            </strong>
            <span class="investor-summary-stat__hint">{{ t('investors.notAllocatedOrWithdrawn') }}</span>
          </article>
          <article class="investor-summary-stat">
            <span class="investor-summary-stat__label">{{ t('investors.linkedProcurementsCount') }}</span>
            <strong class="investor-summary-stat__value tabular-nums">{{ summary.procurements_count }}</strong>
            <span class="investor-summary-stat__hint">{{ t('investors.linkedProcurementsHint') }}</span>
          </article>
        </section>

        <section class="investor-panel">
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">{{ t('investors.yourParticipation') }}</h2>
              <p class="investor-panel__hint">
                {{ t('investors.yourParticipationHint') }}
              </p>
            </div>
            <span class="investor-panel__icon">
              <Wallet :size="18" :stroke-width="2" />
            </span>
          </div>

          <div class="investor-grid-2">
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.plannedContribution') }}</span>
              <strong class="investor-detail-card__value tabular-nums">
                {{ formatAmount(currentPartner?.planned_capital_share ?? '0', currentPartner?.agreement_currency) }}
              </strong>
              <span class="investor-detail-card__hint">{{ t('investors.plannedContributionHint') }}</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.plannedProfitShare') }}</span>
              <strong class="investor-detail-card__value tabular-nums">
                {{ formatRatioPercent(currentPartner?.planned_profit_share ?? '0') }}
              </strong>
              <span class="investor-detail-card__hint">{{ t('investors.plannedProfitShareHint') }}</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.actualContributed') }}</span>
              <strong class="investor-detail-card__value tabular-nums">
                {{ formatAmount(currentPartner?.agreement_contributed ?? '0', currentPartner?.agreement_currency) }}
              </strong>
              <span class="investor-detail-card__hint">{{ t('investors.actualContributedHint') }}</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.allocatedToGoods') }}</span>
              <strong class="investor-detail-card__value tabular-nums">
                {{ formatAmount(currentPartner?.agreement_allocated ?? '0', currentPartner?.agreement_currency) }}
              </strong>
              <span class="investor-detail-card__hint">{{ t('investors.allocatedToGoodsHint') }}</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.paidButInTransit') }}</span>
              <strong class="investor-detail-card__value tabular-nums">
                {{ formatReportAmount(currentPartner, 'pending_prepaid_cost_estimate_uzs', currentPartner?.pending_prepaid_cost_estimate_uzs ?? '0') }}
              </strong>
              <span class="investor-detail-card__hint">{{ t('investors.paidButInTransitHint') }}</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.pendingPayout') }}</span>
              <strong class="investor-detail-card__value tabular-nums investor-positive">
                {{ formatReportAmount(currentPartner, 'profit_pending_payout', currentPartner?.profit_pending_payout ?? '0') }}
              </strong>
              <span class="investor-detail-card__hint">{{ t('investors.pendingPayoutHint') }}</span>
            </article>
          </div>
        </section>

        <section class="investor-panel investor-adjustments-panel">
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">{{ t('investors.returnsWriteoffsTitle') }}</h2>
              <p class="investor-panel__hint">
                {{ t('investors.returnsWriteoffsHint') }}
              </p>
            </div>
            <span class="investor-panel__icon">
              <Scale :size="18" :stroke-width="2" />
            </span>
          </div>

          <div class="investor-adjustment-strip">
            <article class="investor-adjustment-card investor-adjustment-card--positive">
              <span>{{ t('investors.accrued') }}</span>
              <strong class="tabular-nums">
                {{ formatReportAmount(currentPartner, 'profit_accrued', currentPartner?.profit_accrued ?? '0') }}
              </strong>
            </article>
            <article class="investor-adjustment-card">
              <span>{{ t('investors.reversedByReturns') }}</span>
              <strong class="tabular-nums investor-negative">
                {{ formatReportAmount(currentPartner, 'profit_reversed', currentPartner?.profit_reversed ?? '0') }}
              </strong>
            </article>
            <article class="investor-adjustment-card">
              <span>{{ t('investors.writeoffLosses') }}</span>
              <strong class="tabular-nums investor-negative">
                {{ formatReportAmount(currentPartner, 'losses_incurred', currentPartner?.losses_incurred ?? '0') }}
              </strong>
            </article>
            <article class="investor-adjustment-card investor-adjustment-card--net">
              <span>{{ t('investors.netResult') }}</span>
              <strong class="tabular-nums">
                {{ currentPartnerNetProfit }}
              </strong>
            </article>
          </div>

          <p class="investor-adjustment-note">
            {{ hasCurrentPartnerAdjustments
              ? t('investors.adjustmentsIncluded')
              : t('investors.noAdjustments') }}
          </p>
        </section>

        <section class="investor-panel">
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">{{ t('investors.agreementPicture') }}</h2>
              <p class="investor-panel__hint">
                {{ t('investors.agreementPictureHint') }}
              </p>
            </div>
            <span class="investor-panel__icon">
              <Scale :size="18" :stroke-width="2" />
            </span>
          </div>

          <div class="investor-grid-2">
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('reports.revenue') }}</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatReportAmount(summary, 'revenue', summary.revenue) }}</strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('reports.salesCogs') }}</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatReportAmount(summary, 'cogs', summary.cogs) }}</strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('reports.factualProfit') }}</span>
              <strong class="investor-detail-card__value tabular-nums investor-positive">{{ formatReportAmount(summary, 'gross_profit', summary.gross_profit) }}</strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.expectedProfit') }}</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatReportAmount(summary, 'projected_gross_profit', summary.projected_gross_profit) }}</strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.receivedToStock') }}</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatReportAmount(summary, 'received_landed_cost', summary.received_landed_cost) }}</strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.remainingInGoods') }}</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatReportAmount(summary, 'remaining_landed_cost', summary.remaining_landed_cost) }}</strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('investors.paidInTransit') }}</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatReportAmount(summary, 'pending_prepaid_cost', summary.pending_prepaid_cost) }}</strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">{{ t('reports.soldRemaining') }}</span>
              <strong class="investor-detail-card__value tabular-nums">
                {{ summary.quantity_sold }} / {{ summary.remaining_quantity }}
              </strong>
            </article>
          </div>
        </section>

        <section class="investor-panel">
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">{{ t('investors.linkedProcurements') }}</h2>
              <p class="investor-panel__hint">
                {{ t('investors.linkedProcurementsDetailHint') }}
              </p>
            </div>
            <span class="investor-panel__icon">
              <PackageSearch :size="18" :stroke-width="2" />
            </span>
          </div>

          <div v-if="procurements.length === 0" class="investor-empty">
            {{ t('investors.noLinkedProcurements') }}
          </div>

          <div v-else class="investor-list agreement-list">
            <article
              v-for="procurement in procurements"
              :key="procurement.procurement_id"
              class="agreement-row"
            >
              <button type="button" class="investor-list-row agreement-row__toggle" @click="toggleProcurement(procurement.procurement_id)">
                <div class="investor-list-row__main">
                  <div class="agreement-row__head">
                    <strong class="investor-list-row__title">
                      {{ procurementTypeLabel(procurement.procurement_type) }} #{{ procurement.procurement_id }}
                    </strong>
                    <span class="investor-chip" :class="`investor-chip--${procurementStatusTone(procurement.status)}`">
                      {{ procurementStatusLabel(procurement.status) }}
                    </span>
                  </div>
                  <span class="investor-list-row__meta">
                    {{ procurement.supplier_name || t('procurements.supplierMissing') }}
                    · {{ formatDateTime(procurement.received_at || procurement.opened_at) }}
                  </span>
                </div>

                <div class="investor-list-row__side agreement-row__side">
                  <div class="agreement-row__side-copy">
                    <span class="investor-list-row__value tabular-nums">{{ formatReportAmount(procurement, 'gross_profit', procurement.gross_profit) }}</span>
                    <span class="investor-list-row__caption">{{ t('reports.factualProfit') }}</span>
                  </div>
                  <ChevronDown
                    class="agreement-row__chevron"
                    :class="{ 'is-open': expandedProcurementId === procurement.procurement_id }"
                    :size="16"
                    :stroke-width="1.9"
                  />
                </div>
              </button>

              <div v-if="expandedProcurementId === procurement.procurement_id" class="agreement-row__details">
                <div class="investor-grid-2">
                  <article class="investor-detail-card">
                    <span class="investor-detail-card__label">{{ t('investors.alreadyInStock') }}</span>
                    <strong class="investor-detail-card__value tabular-nums">
                      {{ formatReportAmount(procurement, 'received_landed_cost', procurement.received_landed_cost ?? '0') }}
                    </strong>
                  </article>
                  <article class="investor-detail-card">
                    <span class="investor-detail-card__label">{{ t('procurements.inTransit') }}</span>
                    <strong class="investor-detail-card__value tabular-nums">
                      {{ formatReportAmount(procurement, 'pending_prepaid_cost', procurement.pending_prepaid_cost ?? '0') }}
                    </strong>
                  </article>
                  <article class="investor-detail-card">
                    <span class="investor-detail-card__label">{{ t('investors.remainingInGoods') }}</span>
                    <strong class="investor-detail-card__value tabular-nums">
                      {{ formatReportAmount(procurement, 'remaining_landed_cost', procurement.remaining_landed_cost) }}
                    </strong>
                  </article>
                  <article class="investor-detail-card">
                    <span class="investor-detail-card__label">{{ t('investors.expectedProfit') }}</span>
                    <strong class="investor-detail-card__value tabular-nums">
                      {{ formatReportAmount(procurement, 'projected_gross_profit', procurement.projected_gross_profit) }}
                    </strong>
                  </article>
                  <article class="investor-detail-card">
                    <span class="investor-detail-card__label">{{ t('investors.sold') }}</span>
                    <strong class="investor-detail-card__value tabular-nums">{{ procurement.quantity_sold }}</strong>
                  </article>
                  <article class="investor-detail-card">
                    <span class="investor-detail-card__label">{{ t('reports.remaining') }}</span>
                    <strong class="investor-detail-card__value tabular-nums">{{ procurement.remaining_quantity }}</strong>
                  </article>
                </div>

                <button type="button" class="investor-link-button" @click="openProcurement(procurement.procurement_id)">
                  {{ t('investors.openProcurementDetail') }}
                  <ChevronRight :size="16" :stroke-width="1.9" />
                </button>
              </div>
            </article>
          </div>
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped>
.agreement-list {
  gap: var(--space-3);
}

.agreement-row {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-3);
  border-radius: 20px;
  background: rgba(250, 250, 248, 0.92);
  border: 1px solid rgba(12, 69, 51, 0.06);
}

.agreement-row__toggle {
  padding: 0;
  border-top: none;
}

.agreement-row__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-2);
}

.agreement-row__side {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-2);
}

.agreement-row__side-copy {
  display: grid;
  gap: 4px;
}

.agreement-row__chevron {
  color: var(--color-text-tertiary);
  transition: transform var(--duration-fast) var(--ease-out);
}

.agreement-row__chevron.is-open {
  transform: rotate(180deg);
}

.agreement-row__details {
  display: grid;
  gap: var(--space-3);
}

.investor-adjustments-panel {
  gap: var(--space-4);
}

.investor-adjustment-strip {
  display: grid;
  gap: var(--space-2);
}

.investor-adjustment-card {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  border-radius: 16px;
  background: rgba(250, 250, 248, 0.92);
  border: 1px solid rgba(12, 69, 51, 0.06);
}

.investor-adjustment-card span {
  min-width: 0;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.35;
}

.investor-adjustment-card strong {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  text-align: right;
  white-space: nowrap;
}

.investor-adjustment-card--positive strong {
  color: var(--color-success);
}

.investor-adjustment-card--net {
  background: rgba(12, 69, 51, 0.06);
  border-color: rgba(12, 69, 51, 0.1);
}

.investor-adjustment-note {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  line-height: 1.45;
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
  .agreement-row__side {
    grid-template-columns: 1fr auto;
  }

  .investor-currency-switch {
    justify-self: stretch;
    width: 100%;
  }
}
</style>
