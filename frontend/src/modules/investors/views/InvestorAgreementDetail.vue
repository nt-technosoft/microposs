<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ChevronDown, ChevronRight, PackageSearch, RefreshCcw, Scale, Wallet } from 'lucide-vue-next'

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

function toggleProcurement(id: number): void {
  expandedProcurementId.value = expandedProcurementId.value === id ? null : id
}

function openProcurement(procurementId: number): void {
  router.push({ name: 'investor-procurement', params: { id: procurementId } })
}

async function load(): Promise<void> {
  if (!Number.isFinite(agreementId.value) || agreementId.value <= 0) {
    error.value = 'Некорректный ID договора'
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
    error.value = err instanceof Error ? err.message : 'Не удалось загрузить договор'
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
      <button class="investor-header__button" type="button" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>

      <div class="investor-header__copy">
        <strong class="investor-header__title">Деталь договора</strong>
        <span class="investor-header__caption">Ваш баланс, прибыль и связанные приходы</span>
      </div>

      <button class="investor-header__button" type="button" aria-label="Обновить" @click="load">
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
            <span class="investor-hero__kicker">Договор #{{ summary.agreement_id }}</span>
            <h1 class="investor-hero__title">
              {{ summary.supplier_name || 'Договор без поставщика' }}
            </h1>
            <div class="investor-hero__meta">
              <span class="investor-chip investor-chip--glass">
                {{ agreementStatusLabel(summary.status) }}
              </span>
              <span class="investor-chip investor-chip--glass">
                Открыт {{ formatDateTime(summary.opened_at) }}
              </span>
              <span class="investor-chip investor-chip--glass">
                {{ summary.procurements_count }} приходов
              </span>
            </div>
          </div>

          <div class="investor-hero__value">
            <div class="investor-currency-switch" role="group" aria-label="Валюта показателей">
              <button type="button" :class="{ active: activeReportCurrency === 'UZS' }" @click="setReportCurrency('UZS')">UZS</button>
              <button type="button" :class="{ active: activeReportCurrency === 'USD' }" @click="setReportCurrency('USD')">USD</button>
            </div>
            <strong class="investor-hero__amount tabular-nums">
              {{ formatReportAmount(currentPartner, 'profit_pending_payout', currentPartner?.profit_pending_payout ?? '0') }}
            </strong>
            <span class="investor-hero__foot">
              Начислено {{ formatReportAmount(currentPartner, 'profit_accrued', currentPartner?.profit_accrued ?? '0') }}
              · выплачено {{ formatReportAmount(currentPartner, 'dividends_paid', currentPartner?.dividends_paid ?? '0') }}
            </span>
          </div>
        </section>

        <section class="investor-summary-band">
          <article class="investor-summary-stat investor-summary-stat--accent">
            <span class="investor-summary-stat__label">Плановый бюджет</span>
            <strong class="investor-summary-stat__value tabular-nums">
              {{ formatAmount(summary.planned_budget, summary.currency) }}
            </strong>
            <span class="investor-summary-stat__hint">База всего договора</span>
          </article>
          <article class="investor-summary-stat">
            <span class="investor-summary-stat__label">Баланс договора</span>
            <strong class="investor-summary-stat__value tabular-nums">
              {{ formatBalanceLabel(summary.balances) }}
            </strong>
            <span class="investor-summary-stat__hint">Свободный остаток по всем валютам</span>
          </article>
          <article class="investor-summary-stat">
            <span class="investor-summary-stat__label">Ваш остаток</span>
            <strong class="investor-summary-stat__value tabular-nums">
              {{ formatAmount(currentPartner?.agreement_available ?? '0', currentPartner?.agreement_currency) }}
            </strong>
            <span class="investor-summary-stat__hint">Не распределён в товар или не выведен</span>
          </article>
          <article class="investor-summary-stat">
            <span class="investor-summary-stat__label">Связанных приходов</span>
            <strong class="investor-summary-stat__value tabular-nums">{{ summary.procurements_count }}</strong>
            <span class="investor-summary-stat__hint">По ним уже двигается товар и прибыль</span>
          </article>
        </section>

        <section class="investor-panel">
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">Ваше участие в договоре</h2>
              <p class="investor-panel__hint">
                Капитал, распределение и прибыль именно по вашей стороне договора.
              </p>
            </div>
            <span class="investor-panel__icon">
              <Wallet :size="18" :stroke-width="2" />
            </span>
          </div>

          <div class="investor-grid-2">
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Плановый вклад</span>
              <strong class="investor-detail-card__value tabular-nums">
                {{ formatAmount(currentPartner?.planned_capital_share ?? '0', currentPartner?.agreement_currency) }}
              </strong>
              <span class="investor-detail-card__hint">Сумма, на которую вы изначально входили в договор.</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Плановая доля прибыли</span>
              <strong class="investor-detail-card__value tabular-nums">
                {{ formatRatioPercent(currentPartner?.planned_profit_share ?? '0') }}
              </strong>
              <span class="investor-detail-card__hint">Как договор делит profit между вами и бизнесом.</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Фактически внесено</span>
              <strong class="investor-detail-card__value tabular-nums">
                {{ formatAmount(currentPartner?.agreement_contributed ?? '0', currentPartner?.agreement_currency) }}
              </strong>
              <span class="investor-detail-card__hint">Сколько капитала реально поступило в договор.</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Ушло в товар</span>
              <strong class="investor-detail-card__value tabular-nums">
                {{ formatAmount(currentPartner?.agreement_allocated ?? '0', currentPartner?.agreement_currency) }}
              </strong>
              <span class="investor-detail-card__hint">Часть капитала, уже распределённая по закупкам.</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Оплачено, но ещё в пути</span>
              <strong class="investor-detail-card__value tabular-nums">
                {{ formatReportAmount(currentPartner, 'pending_prepaid_cost_estimate_uzs', currentPartner?.pending_prepaid_cost_estimate_uzs ?? '0') }}
              </strong>
              <span class="investor-detail-card__hint">Деньги уже ушли, но товар ещё не принят на склад.</span>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">К выплате</span>
              <strong class="investor-detail-card__value tabular-nums investor-positive">
                {{ formatReportAmount(currentPartner, 'profit_pending_payout', currentPartner?.profit_pending_payout ?? '0') }}
              </strong>
              <span class="investor-detail-card__hint">Невыплаченная прибыль по вашей стороне.</span>
            </article>
          </div>
        </section>

        <section class="investor-panel">
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">Картина по договору</h2>
              <p class="investor-panel__hint">
                Общий объём товара, себестоимость и уже заработанная прибыль по всей связке.
              </p>
            </div>
            <span class="investor-panel__icon">
              <Scale :size="18" :stroke-width="2" />
            </span>
          </div>

          <div class="investor-grid-2">
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Выручка</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatReportAmount(summary, 'revenue', summary.revenue) }}</strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Себестоимость продаж</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatReportAmount(summary, 'cogs', summary.cogs) }}</strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Фактическая прибыль</span>
              <strong class="investor-detail-card__value tabular-nums investor-positive">{{ formatReportAmount(summary, 'gross_profit', summary.gross_profit) }}</strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Ожидаемая прибыль</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatReportAmount(summary, 'projected_gross_profit', summary.projected_gross_profit) }}</strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Уже принято на склад</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatReportAmount(summary, 'received_landed_cost', summary.received_landed_cost) }}</strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Осталось в товаре</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatReportAmount(summary, 'remaining_landed_cost', summary.remaining_landed_cost) }}</strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Оплачено в пути</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatReportAmount(summary, 'pending_prepaid_cost', summary.pending_prepaid_cost) }}</strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Продано / осталось</span>
              <strong class="investor-detail-card__value tabular-nums">
                {{ summary.quantity_sold }} / {{ summary.remaining_quantity }}
              </strong>
            </article>
          </div>
        </section>

        <section class="investor-panel">
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">Связанные приходы</h2>
              <p class="investor-panel__hint">
                По каждому приходу можно быстро посмотреть статус, прибыль и перейти в детальный investor-аудит.
              </p>
            </div>
            <span class="investor-panel__icon">
              <PackageSearch :size="18" :stroke-width="2" />
            </span>
          </div>

          <div v-if="procurements.length === 0" class="investor-empty">
            Связанных приходов пока нет.
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
                    {{ procurement.supplier_name || 'Без поставщика' }}
                    · {{ formatDateTime(procurement.received_at || procurement.opened_at) }}
                  </span>
                </div>

                <div class="investor-list-row__side agreement-row__side">
                  <div class="agreement-row__side-copy">
                    <span class="investor-list-row__value tabular-nums">{{ formatReportAmount(procurement, 'gross_profit', procurement.gross_profit) }}</span>
                    <span class="investor-list-row__caption">Факт. прибыль</span>
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
                    <span class="investor-detail-card__label">Уже на складе</span>
                    <strong class="investor-detail-card__value tabular-nums">
                      {{ formatReportAmount(procurement, 'received_landed_cost', procurement.received_landed_cost ?? '0') }}
                    </strong>
                  </article>
                  <article class="investor-detail-card">
                    <span class="investor-detail-card__label">В пути</span>
                    <strong class="investor-detail-card__value tabular-nums">
                      {{ formatReportAmount(procurement, 'pending_prepaid_cost', procurement.pending_prepaid_cost ?? '0') }}
                    </strong>
                  </article>
                  <article class="investor-detail-card">
                    <span class="investor-detail-card__label">Остаток в товаре</span>
                    <strong class="investor-detail-card__value tabular-nums">
                      {{ formatReportAmount(procurement, 'remaining_landed_cost', procurement.remaining_landed_cost) }}
                    </strong>
                  </article>
                  <article class="investor-detail-card">
                    <span class="investor-detail-card__label">Ожидаемая прибыль</span>
                    <strong class="investor-detail-card__value tabular-nums">
                      {{ formatReportAmount(procurement, 'projected_gross_profit', procurement.projected_gross_profit) }}
                    </strong>
                  </article>
                  <article class="investor-detail-card">
                    <span class="investor-detail-card__label">Продано</span>
                    <strong class="investor-detail-card__value tabular-nums">{{ procurement.quantity_sold }}</strong>
                  </article>
                  <article class="investor-detail-card">
                    <span class="investor-detail-card__label">Остаток</span>
                    <strong class="investor-detail-card__value tabular-nums">{{ procurement.remaining_quantity }}</strong>
                  </article>
                </div>

                <button type="button" class="investor-link-button" @click="openProcurement(procurement.procurement_id)">
                  Открыть деталь прихода
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
