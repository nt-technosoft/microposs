<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, RefreshCcw, Scale, ScrollText, Wallet } from 'lucide-vue-next'

import { fetchInvestorProcurementDetail } from '@/api/investors'
import { useFxRate } from '@/composables/useFxRate'
import { useToast } from '@/composables/useToast'
import type { InvestorLedgerEntry, InvestorProcurementDetail } from '@/types/models'
import {
  formatDateTime,
  ledgerEntryLabel,
  ledgerEntryTone,
  procurementStatusLabel,
  procurementStatusTone,
  procurementTypeLabel,
} from '@/modules/investors/presentation'
import { formatPrice } from '@/utils/currency'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const {
  rate: latestUsdRate,
  error: latestUsdRateError,
  load: loadLatestUsdRate,
} = useFxRate()

const procurement = ref<InvestorProcurementDetail | null>(null)
const isLoading = ref(true)
const errorMessage = ref('')
const reportCurrency = ref<'UZS' | 'USD'>('USD')

const procurementId = computed(() => Number(route.params.id))

function formatCapitalState(field: keyof InvestorProcurementDetail['capital_state']): string {
  return formatReportPrice(procurement.value?.capital_state?.[field] ?? '0')
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

function formatLedgerTotal(field: keyof InvestorProcurementDetail['investor_aggregate']['functional_uzs']): string {
  return formatReportPrice(procurement.value?.investor_aggregate.functional_uzs?.[field] ?? '0')
}

function entryAmountLabel(entry: InvestorLedgerEntry): string {
  return formatReportPrice(entry.functional_amount_uzs)
}

function entrySecondaryHint(entry: InvestorLedgerEntry): string {
  const native = String(entry.currency || 'UZS').toUpperCase()
  if (native === reportCurrency.value) return ''
  return `Оригинал ${formatPrice(entry.amount, native)}`
}

function sourceRefLabel(rawRef: string | null | undefined): string {
  if (!rawRef) return ''
  const parts = rawRef.split(':').filter(Boolean)
  const source = parts[0]
  const id = parts[1]
  const nested = parts[2]
  const nestedId = parts[3]
  const labels: Record<string, string> = {
    sale: 'Продажа',
    sale_line: 'Продажа',
    return: 'Возврат',
    risk_event: 'Списание',
    contribution: 'Взнос',
    dividend_payment: 'Выплата прибыли',
    procurement: 'Приход',
  }
  if (source === 'return' && nested === 'line' && id && nestedId) return `Возврат #${id}`
  if (id) return `${labels[source] ?? source.replaceAll('_', ' ')} #${id}`
  return labels[source] ?? rawRef.replaceAll('_', ' ')
}

function entryToneClass(entry: InvestorLedgerEntry): string {
  const tone = ledgerEntryTone(entry.entry_type)
  if (tone === 'positive') return 'investor-positive'
  if (tone === 'negative') return 'investor-negative'
  return 'investor-neutral'
}

async function loadContract(): Promise<void> {
  if (!Number.isFinite(procurementId.value) || procurementId.value <= 0) {
    errorMessage.value = 'Некорректный ID прихода'
    isLoading.value = false
    return
  }

  isLoading.value = true
  errorMessage.value = ''

  try {
    procurement.value = await fetchInvestorProcurementDetail(procurementId.value)
    if (reportCurrency.value === 'USD' && !latestUsdRate.value) {
      try {
        await loadLatestUsdRate()
      } catch {
        reportCurrency.value = 'UZS'
      }
    }
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить приход'
  } finally {
    isLoading.value = false
  }
}

async function setReportCurrency(currency: 'UZS' | 'USD'): Promise<void> {
  if (reportCurrency.value === currency) return
  reportCurrency.value = currency
  if (currency === 'USD' && !latestUsdRate.value) {
    try {
      await loadLatestUsdRate()
    } catch {
      reportCurrency.value = 'UZS'
      toast.error(latestUsdRateError.value || 'Курс USD/UZS не найден')
    }
  }
}

onMounted(loadContract)
</script>

<template>
  <div class="investor-shell">
    <header class="investor-header">
      <button class="investor-header__button" type="button" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>

      <div class="investor-header__copy">
        <strong class="investor-header__title">Деталь прихода</strong>
        <span class="investor-header__caption">Капитал, товар и журнал начислений</span>
      </div>

      <button class="investor-header__button" type="button" aria-label="Обновить" @click="loadContract">
        <RefreshCcw :size="16" :stroke-width="1.75" />
      </button>
    </header>

    <main class="investor-content">
      <template v-if="isLoading">
        <div class="investor-hero investor-skeleton skeleton" aria-hidden="true" />
        <div class="investor-panel investor-skeleton skeleton" />
      </template>

      <section v-else-if="errorMessage" class="investor-state investor-state--error" role="alert">
        <p>{{ errorMessage }}</p>
      </section>

      <template v-else-if="procurement">
        <section class="investor-hero">
          <div class="investor-hero__copy">
            <span class="investor-hero__kicker">Приход #{{ procurement.id }}</span>
            <h1 class="investor-hero__title">
              {{ procurement.supplier_name || procurementTypeLabel(procurement.procurement_type) }}
            </h1>
            <div class="investor-hero__meta">
              <span class="investor-chip investor-chip--glass">
                {{ procurementTypeLabel(procurement.procurement_type) }}
              </span>
              <span class="investor-chip investor-chip--glass">
                {{ procurementStatusLabel(procurement.status) }}
              </span>
              <span class="investor-chip investor-chip--glass">
                Открыт {{ formatDateTime(procurement.opened_at) }}
              </span>
            </div>
          </div>

          <div class="investor-hero__value">
            <div class="investor-currency-switch" role="group" aria-label="Валюта показателей">
              <button type="button" :class="{ active: reportCurrency === 'UZS' }" @click="setReportCurrency('UZS')">UZS</button>
              <button type="button" :class="{ active: reportCurrency === 'USD' }" @click="setReportCurrency('USD')">USD</button>
            </div>
            <strong class="investor-hero__amount tabular-nums">
              {{ formatLedgerTotal('profit_pending_payout') }}
            </strong>
            <span class="investor-hero__foot">
              Начислено {{ formatLedgerTotal('profit_accrued') }}
              · вложено {{ formatLedgerTotal('capital_in') }}
            </span>
          </div>
        </section>

        <section class="investor-summary-band">
          <article class="investor-summary-stat investor-summary-stat--accent">
            <span class="investor-summary-stat__label">Вложено в приход</span>
            <strong class="investor-summary-stat__value tabular-nums">
              {{ formatLedgerTotal('capital_in') }}
            </strong>
            <span class="investor-summary-stat__hint">Ваш вклад по этому приходу</span>
          </article>
          <article class="investor-summary-stat">
            <span class="investor-summary-stat__label">Чистый капитал</span>
            <strong class="investor-summary-stat__value tabular-nums">
              {{ formatLedgerTotal('capital_net') }}
            </strong>
            <span class="investor-summary-stat__hint">Вносы минус возвраты по приходу</span>
          </article>
          <article class="investor-summary-stat">
            <span class="investor-summary-stat__label">Отслеживается в товаре</span>
            <strong class="investor-summary-stat__value tabular-nums">
              {{ formatCapitalState('tracked_cost_uzs') }}
            </strong>
            <span class="investor-summary-stat__hint">Сколько капитала ещё лежит в остатке</span>
          </article>
          <article class="investor-summary-stat">
            <span class="investor-summary-stat__label">Прогноз прибыли</span>
            <strong class="investor-summary-stat__value tabular-nums">
              {{ formatCapitalState('projected_partner_profit_uzs') }}
            </strong>
            <span class="investor-summary-stat__hint">Ожидаемая прибыль по остатку</span>
          </article>
        </section>

        <section class="investor-panel">
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">Картина прихода</h2>
              <p class="investor-panel__hint">
                Базовый статус прихода и текстовый контекст, если owner оставлял заметки.
              </p>
            </div>
            <span class="investor-panel__icon">
              <Wallet :size="18" :stroke-width="2" />
            </span>
          </div>

          <div class="investor-grid-2">
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Поставщик</span>
              <strong class="investor-detail-card__value">{{ procurement.supplier_name || '—' }}</strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Статус</span>
              <div class="detail-chip-row">
                <span class="investor-chip" :class="`investor-chip--${procurementStatusTone(procurement.status)}`">
                  {{ procurementStatusLabel(procurement.status) }}
                </span>
              </div>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Открыт</span>
              <strong class="investor-detail-card__value">{{ formatDateTime(procurement.opened_at) }}</strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Принят</span>
              <strong class="investor-detail-card__value">{{ formatDateTime(procurement.received_at) }}</strong>
            </article>
          </div>

          <p v-if="procurement.notes" class="investor-note procurement-note">
            {{ procurement.notes }}
          </p>
        </section>

        <section class="investor-panel">
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">Ваш капитал по приходу</h2>
              <p class="investor-panel__hint">
                Здесь собраны все начисления, убытки и выплаты только по вашему участию в этом приходе.
              </p>
            </div>
            <span class="investor-panel__icon">
              <Scale :size="18" :stroke-width="2" />
            </span>
          </div>

          <div class="investor-grid-2">
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Начисленная прибыль</span>
              <strong class="investor-detail-card__value tabular-nums investor-positive">
                {{ formatLedgerTotal('profit_accrued') }}
              </strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">К выплате</span>
              <strong class="investor-detail-card__value tabular-nums">
                {{ formatLedgerTotal('profit_pending_payout') }}
              </strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Возврат капитала</span>
              <strong class="investor-detail-card__value tabular-nums">
                {{ formatLedgerTotal('capital_out') }}
              </strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Дивиденды выплачены</span>
              <strong class="investor-detail-card__value tabular-nums">
                {{ formatLedgerTotal('dividends_paid') }}
              </strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Убытки</span>
              <strong class="investor-detail-card__value tabular-nums investor-negative">
                {{ formatLedgerTotal('losses_incurred') }}
              </strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Корректировки прибыли</span>
              <strong class="investor-detail-card__value tabular-nums investor-negative">
                {{ formatLedgerTotal('profit_reversed') }}
              </strong>
            </article>
          </div>
        </section>

        <section class="investor-panel">
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">Капитал в товаре</h2>
              <p class="investor-panel__hint">
                Отдельно видно, сколько капитала уже вышло через продажи, а сколько ещё лежит в остатке.
              </p>
            </div>
            <span class="investor-panel__icon">
              <Wallet :size="18" :stroke-width="2" />
            </span>
          </div>

          <div class="investor-grid-2">
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Продано по себестоимости</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatCapitalState('sold_cost_uzs') }}</strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Осталось в товаре</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatCapitalState('in_stock_cost_uzs') }}</strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Выручка по проданному</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatCapitalState('sold_revenue_uzs') }}</strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Прогноз выручки</span>
              <strong class="investor-detail-card__value tabular-nums">{{ formatCapitalState('projected_revenue_uzs') }}</strong>
            </article>
            <article class="investor-detail-card detail-card--wide">
              <span class="investor-detail-card__label">Прогноз прибыли инвестора</span>
              <strong class="investor-detail-card__value tabular-nums investor-positive">
                {{ formatCapitalState('projected_partner_profit_uzs') }}
              </strong>
            </article>
          </div>
        </section>

        <section class="investor-panel">
          <div class="investor-panel__head">
            <div class="investor-panel__copy">
              <h2 class="investor-panel__title">Журнал операций</h2>
              <p class="investor-panel__hint">
                Последовательность проводок, которые меняли ваш капитал или прибыль по этому приходу.
              </p>
            </div>
            <span class="investor-panel__icon">
              <ScrollText :size="18" :stroke-width="2" />
            </span>
          </div>

          <div v-if="procurement.investor_ledger.entries.length === 0" class="investor-empty">
            Записей по приходу пока нет.
          </div>

          <div v-else class="ledger-stack">
            <article
              v-for="entry in procurement.investor_ledger.entries"
              :key="entry.id"
              class="ledger-row"
            >
              <div class="ledger-row__marker" :class="entryToneClass(entry)" />
              <div class="ledger-row__main">
                <strong class="ledger-row__title">{{ ledgerEntryLabel(entry.entry_type) }}</strong>
                <span class="ledger-row__meta">{{ formatDateTime(entry.date) }}</span>
                <span v-if="entry.source_ref" class="ledger-row__meta">{{ sourceRefLabel(entry.source_ref) }}</span>
              </div>
              <div class="ledger-row__side">
                <strong class="ledger-row__amount tabular-nums" :class="entryToneClass(entry)">
                  {{ entryAmountLabel(entry) }}
                </strong>
                <span v-if="entrySecondaryHint(entry)" class="ledger-row__meta">
                  {{ entrySecondaryHint(entry) }}
                </span>
              </div>
            </article>
          </div>
        </section>
      </template>

      <section v-else class="investor-state investor-state--error">
        <p>Приход не найден или недоступен.</p>
      </section>
    </main>
  </div>
</template>

<style scoped>
.detail-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.procurement-note {
  padding: var(--space-3);
  border-radius: 18px;
  background: rgba(250, 250, 248, 0.9);
  border: 1px solid rgba(12, 69, 51, 0.06);
}

.detail-card--wide {
  grid-column: 1 / -1;
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

.ledger-stack {
  display: grid;
  gap: var(--space-3);
}

.ledger-row {
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr) auto;
  gap: var(--space-3);
  align-items: start;
  padding: var(--space-3);
  border-radius: 18px;
  background: rgba(250, 250, 248, 0.92);
  border: 1px solid rgba(12, 69, 51, 0.06);
}

.ledger-row__marker {
  width: 10px;
  height: 10px;
  margin-top: 6px;
  border-radius: 999px;
  background: var(--color-info);
}

.ledger-row__main,
.ledger-row__side {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.ledger-row__title {
  font-size: var(--text-sm);
  line-height: 1.35;
  color: var(--color-text-primary);
}

.ledger-row__meta {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: 1.45;
}

.ledger-row__side {
  justify-items: end;
  text-align: right;
}

.ledger-row__amount {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

@media (max-width: 420px) {
  .investor-currency-switch {
    justify-self: stretch;
    width: 100%;
  }

  .ledger-row {
    grid-template-columns: 10px minmax(0, 1fr);
  }

  .ledger-row__side {
    grid-column: 2;
    justify-items: start;
    text-align: left;
  }
}
</style>
