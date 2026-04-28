<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, RefreshCcw, Scale, ScrollText, Wallet } from 'lucide-vue-next'

import { fetchInvestorProcurementDetail } from '@/api/investors'
import type { InvestorLedgerEntry, InvestorProcurementDetail } from '@/types/models'
import {
  formatAggregateAmount,
  formatDateTime,
  formatFunctionalAmount,
  ledgerEntryLabel,
  ledgerEntryTone,
  procurementStatusLabel,
  procurementStatusTone,
  procurementTypeLabel,
} from '@/modules/investors/presentation'
import { formatPrice } from '@/utils/currency'

const route = useRoute()
const router = useRouter()

const procurement = ref<InvestorProcurementDetail | null>(null)
const isLoading = ref(true)
const errorMessage = ref('')

const procurementId = computed(() => Number(route.params.id))

function formatCapitalState(field: keyof InvestorProcurementDetail['capital_state']): string {
  return formatPrice(procurement.value?.capital_state?.[field] ?? '0', 'UZS')
}

function entryFunctionalHint(entry: InvestorLedgerEntry): string {
  if (entry.currency === 'UZS') return ''
  return `≈ ${formatPrice(entry.functional_amount_uzs, 'UZS')}`
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
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить приход'
  } finally {
    isLoading.value = false
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
            <strong class="investor-hero__amount tabular-nums">
              {{ formatFunctionalAmount(procurement.investor_aggregate, 'profit_pending_payout') }}
            </strong>
            <span class="investor-hero__foot">
              Начислено {{ formatAggregateAmount(procurement.investor_aggregate, 'profit_accrued', 'UZS') }}
              · вложено {{ formatAggregateAmount(procurement.investor_aggregate, 'capital_in', 'USD') }}
            </span>
          </div>
        </section>

        <section class="investor-summary-band">
          <article class="investor-summary-stat investor-summary-stat--accent">
            <span class="investor-summary-stat__label">Вложено в приход</span>
            <strong class="investor-summary-stat__value tabular-nums">
              {{ formatAggregateAmount(procurement.investor_aggregate, 'capital_in', 'USD') }}
            </strong>
            <span class="investor-summary-stat__hint">Ваш capital in по этому приходу</span>
          </article>
          <article class="investor-summary-stat">
            <span class="investor-summary-stat__label">Чистый капитал</span>
            <strong class="investor-summary-stat__value tabular-nums">
              {{ formatAggregateAmount(procurement.investor_aggregate, 'capital_net', 'USD') }}
            </strong>
            <span class="investor-summary-stat__hint">Вносы минус возвраты по приходу</span>
          </article>
          <article class="investor-summary-stat">
            <span class="investor-summary-stat__label">Отслеживается в товаре</span>
            <strong class="investor-summary-stat__value tabular-nums">
              {{ formatCapitalState('tracked_cost_uzs') }}
            </strong>
            <span class="investor-summary-stat__hint">Сколько капитала ещё крутится в stock</span>
          </article>
          <article class="investor-summary-stat">
            <span class="investor-summary-stat__label">Прогноз прибыли</span>
            <strong class="investor-summary-stat__value tabular-nums">
              {{ formatCapitalState('projected_partner_profit_uzs') }}
            </strong>
            <span class="investor-summary-stat__hint">Potential upside on the remaining goods</span>
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
                {{ formatAggregateAmount(procurement.investor_aggregate, 'profit_accrued', 'UZS') }}
              </strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">К выплате</span>
              <strong class="investor-detail-card__value tabular-nums">
                {{ formatFunctionalAmount(procurement.investor_aggregate, 'profit_pending_payout') }}
              </strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Возврат капитала</span>
              <strong class="investor-detail-card__value tabular-nums">
                {{ formatAggregateAmount(procurement.investor_aggregate, 'capital_out', 'USD') }}
              </strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Дивиденды выплачены</span>
              <strong class="investor-detail-card__value tabular-nums">
                {{ formatAggregateAmount(procurement.investor_aggregate, 'dividends_paid', 'USD') }}
              </strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Убытки</span>
              <strong class="investor-detail-card__value tabular-nums investor-negative">
                {{ formatAggregateAmount(procurement.investor_aggregate, 'losses_incurred', 'UZS') }}
              </strong>
            </article>
            <article class="investor-detail-card">
              <span class="investor-detail-card__label">Корректировки прибыли</span>
              <strong class="investor-detail-card__value tabular-nums investor-negative">
                {{ formatAggregateAmount(procurement.investor_aggregate, 'profit_reversed', 'UZS') }}
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
                <span v-if="entry.source_ref" class="ledger-row__meta">{{ entry.source_ref }}</span>
              </div>
              <div class="ledger-row__side">
                <strong class="ledger-row__amount tabular-nums" :class="entryToneClass(entry)">
                  {{ formatPrice(entry.amount, entry.currency) }}
                </strong>
                <span v-if="entryFunctionalHint(entry)" class="ledger-row__meta">
                  {{ entryFunctionalHint(entry) }}
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
