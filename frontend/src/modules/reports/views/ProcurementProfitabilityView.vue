<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ChevronDown, ExternalLink, PackageSearch, Scale, Wallet } from 'lucide-vue-next'

import {
  fetchProcurementProfitabilityDetail,
  type ProcurementProfitabilityDetail,
  type ProcurementProfitabilityDetailItem,
} from '@/api/finance'
import { fetchProcurement, type ProcurementDetail } from '@/api/partnerships'
import { formatPrice } from '@/utils/currency'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const error = ref<string | null>(null)
const report = ref<ProcurementProfitabilityDetail | null>(null)
const procurementDetail = ref<ProcurementDetail | null>(null)
const expandedItemId = ref<number | null>(null)
const selectedReportCurrency = ref<'UZS' | 'USD' | ''>('')

const procurementId = computed(() => Number(route.params.id))
const summary = computed(() => report.value?.procurement ?? null)
const itemRows = computed(() => report.value?.items ?? [])
const activeReportCurrency = computed(() => report.value?.report_currency?.currency ?? 'UZS')
const participantTotals = computed(() => procurementDetail.value?.balance.participant_totals ?? [])
const balanceHistory = computed(() => procurementDetail.value?.balance.history ?? [])
const visibleHistory = computed(() => balanceHistory.value.slice(0, 4))

function formatAmount(value: string | number, currency = 'UZS'): string {
  return formatPrice(value, currency)
}

function formatReportAmount(
  row: { display?: { currency: string; amounts: Record<string, string> } } | null | undefined,
  key: string,
  fallback: string | number,
): string {
  if (row?.display?.amounts?.[key] !== undefined) {
    return formatPrice(row.display.amounts[key], row.display.currency)
  }
  return formatAmount(fallback)
}

function formatPercent(value: string | number | null | undefined): string {
  const numeric = typeof value === 'number' ? value : Number.parseFloat(String(value ?? '0'))
  return `${numeric.toLocaleString('ru-RU', { maximumFractionDigits: 2 })}%`
}

function formatRatioPercent(value: string | number | null | undefined): string {
  const numeric = typeof value === 'number' ? value : Number.parseFloat(String(value ?? '0'))
  return `${(numeric * 100).toLocaleString('ru-RU', { maximumFractionDigits: 2 })}%`
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'long',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function procurementTypeLabel(type: string | null | undefined): string {
  if (type === 'PARTNERSHIP') return 'Партнёрская закупка'
  if (type === 'MUSHARAKA') return 'Мушарака'
  if (type === 'OWN_FUNDS') return 'Свои средства'
  if (type === 'DISTRIBUTOR') return 'Дистрибьютор'
  return type || '—'
}

function procurementStatusLabel(status: string | null | undefined): string {
  if (status === 'PARTIALLY_RECEIVED') return 'Частично оприходована'
  if (status === 'RECEIVED') return 'Завершена'
  if (status === 'OPEN') return 'Открыта'
  if (status === 'CLOSED') return 'Закрыта'
  if (status === 'CANCELLED') return 'Отменена'
  return status || '—'
}

function historyAmountClass(kind: string): string {
  if (kind === 'CONTRIBUTION') return 'history-amount positive'
  if (kind === 'EXCHANGE') return 'history-amount'
  return 'history-amount negative'
}

function historySign(kind: string): string {
  if (kind === 'EXCHANGE') return ''
  return kind === 'CONTRIBUTION' ? '+' : '−'
}

function historyAmountLabel(entry: ProcurementDetail['balance']['history'][number]): string {
  if (entry.kind === 'EXCHANGE' && entry.secondary_amount && entry.secondary_currency) {
    return `${formatAmount(entry.amount, entry.currency)} → ${formatAmount(entry.secondary_amount, entry.secondary_currency)}`
  }
  return `${historySign(entry.kind)} ${formatAmount(entry.amount, entry.currency)}`
}

function toggleItem(itemId: number): void {
  expandedItemId.value = expandedItemId.value === itemId ? null : itemId
}

function openOperationalCard(): void {
  router.push({ name: 'procurement-detail', params: { id: procurementId.value } })
}

async function load(): Promise<void> {
  if (!Number.isFinite(procurementId.value) || procurementId.value <= 0) {
    error.value = 'Некорректный ID закупки'
    return
  }

  loading.value = true
  error.value = null
  try {
    const [reportPayload, procurementPayload] = await Promise.all([
      fetchProcurementProfitabilityDetail(
        procurementId.value,
        selectedReportCurrency.value ? { report_currency: selectedReportCurrency.value } : undefined,
      ),
      fetchProcurement(procurementId.value),
    ])
    report.value = reportPayload
    procurementDetail.value = procurementPayload
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Не удалось загрузить аудит закупки'
  } finally {
    loading.value = false
  }
}

async function setReportCurrency(currency: 'UZS' | 'USD'): Promise<void> {
  selectedReportCurrency.value = currency
  await load()
}

onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-header">
      <button class="icon-btn" type="button" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>
      <div class="header-copy">
        <h1 class="title">Аудит закупки</h1>
        <p class="subtitle">Реализованная и ожидаемая прибыль по одному приходу</p>
      </div>
      <button class="ghost-btn" type="button" @click="openOperationalCard">
        <ExternalLink :size="14" :stroke-width="2" />
        Приход
      </button>
    </header>

    <main class="content">
      <section v-if="loading" class="hero">
        <p class="muted">Собираю прибыльность закупки...</p>
      </section>

      <section v-else-if="error" class="hero hero--error">
        <p>{{ error }}</p>
      </section>

      <template v-else-if="summary && procurementDetail">
        <section class="hero">
          <div class="hero-copy">
            <p class="hero-kicker">Приход #{{ summary.procurement_id }}</p>
            <h2 class="hero-title">{{ summary.supplier_name || 'Закупка без поставщика' }}</h2>
            <div class="hero-meta">
              <span>{{ procurementTypeLabel(summary.procurement_type) }}</span>
              <span>{{ procurementStatusLabel(summary.status) }}</span>
              <span>{{ formatDateTime(summary.received_at || summary.opened_at) }}</span>
            </div>
          </div>
          <div class="hero-value">
            <div class="report-currency-switch" role="group" aria-label="Валюта аудита">
              <button type="button" :class="{ active: activeReportCurrency === 'UZS' }" @click="setReportCurrency('UZS')">UZS</button>
              <button type="button" :class="{ active: activeReportCurrency === 'USD' }" @click="setReportCurrency('USD')">USD</button>
            </div>
            <span class="hero-label">Факт. прибыль</span>
            <strong class="hero-amount tabular-nums">{{ formatReportAmount(summary, 'gross_profit', summary.gross_profit) }}</strong>
            <span class="hero-note">Прогноз {{ formatReportAmount(summary, 'projected_gross_profit', summary.projected_gross_profit) }}</span>
          </div>
        </section>

        <section class="summary-band">
          <article class="summary-metric">
            <span class="metric-label">Выручка</span>
            <strong class="metric-value tabular-nums">{{ formatReportAmount(summary, 'revenue', summary.revenue) }}</strong>
          </article>
          <article class="summary-metric">
            <span class="metric-label">Себестоимость</span>
            <strong class="metric-value tabular-nums">{{ formatReportAmount(summary, 'cogs', summary.cogs) }}</strong>
          </article>
          <article class="summary-metric">
            <span class="metric-label">В остатке</span>
            <strong class="metric-value tabular-nums">{{ formatReportAmount(summary, 'remaining_landed_cost', summary.remaining_landed_cost) }}</strong>
          </article>
          <article class="summary-metric">
            <span class="metric-label">Продано / остаток</span>
            <strong class="metric-value tabular-nums">{{ summary.quantity_sold }} / {{ summary.remaining_quantity }}</strong>
          </article>
        </section>

        <section class="section">
          <div class="section-head">
            <div>
              <p class="section-kicker">Формула закупки</p>
              <h3 class="section-title">Итог</h3>
            </div>
            <Scale :size="18" :stroke-width="2" class="section-icon" />
          </div>

          <div class="formula-list">
            <div class="formula-row">
              <span>Фактическая прибыль</span>
              <strong class="mono">{{ formatReportAmount(summary, 'gross_profit', summary.gross_profit) }}</strong>
            </div>
            <div class="formula-row">
              <span>Инвесторы из факта</span>
              <strong class="mono">{{ formatReportAmount(summary, 'investor_profit', summary.investor_profit) }}</strong>
            </div>
            <div class="formula-row">
              <span>Бизнес из факта</span>
              <strong class="mono">{{ formatReportAmount(summary, 'business_profit', summary.business_profit) }}</strong>
            </div>
            <div class="formula-row">
              <span>Прогноз по остатку</span>
              <strong class="mono">{{ formatReportAmount(summary, 'projected_gross_profit', summary.projected_gross_profit) }}</strong>
            </div>
            <div class="formula-row">
              <span>Инвесторы из прогноза</span>
              <strong class="mono">{{ formatReportAmount(summary, 'projected_investor_profit', summary.projected_investor_profit) }}</strong>
            </div>
            <div class="formula-row">
              <span>Бизнес из прогноза</span>
              <strong class="mono">{{ formatReportAmount(summary, 'projected_business_profit', summary.projected_business_profit) }}</strong>
            </div>
          </div>
        </section>

        <section class="section">
          <div class="section-head">
            <div>
              <p class="section-kicker">Purchase line → sold → remaining</p>
              <h3 class="section-title">Строки закупки</h3>
            </div>
            <PackageSearch :size="18" :stroke-width="2" class="section-icon" />
          </div>

          <div class="item-list">
            <article
              v-for="item in itemRows"
              :key="item.procurement_item_id"
              class="item-row"
              :class="{ open: expandedItemId === item.procurement_item_id }"
            >
              <button type="button" class="item-toggle" @click="toggleItem(item.procurement_item_id)">
                <div class="item-main">
                  <div class="item-title-row">
                    <strong class="item-title">{{ item.product_name }}</strong>
                    <span class="item-badge">{{ item.purchased_quantity }} шт.</span>
                  </div>
                  <div class="item-meta">
                    <span>Продано {{ item.sold_quantity }}</span>
                    <span>Остаток {{ item.remaining_quantity }}</span>
                    <span>Маржа {{ formatPercent(item.margin_percent) }}</span>
                  </div>
                </div>
                <div class="item-side">
                  <strong class="item-profit tabular-nums">{{ formatReportAmount(item, 'gross_profit', item.gross_profit) }}</strong>
                  <span class="item-projection">Прогноз {{ formatReportAmount(item, 'projected_gross_profit', item.projected_gross_profit) }}</span>
                  <ChevronDown :size="16" :stroke-width="1.8" class="item-chevron" :class="{ open: expandedItemId === item.procurement_item_id }" />
                </div>
              </button>

              <div v-if="expandedItemId === item.procurement_item_id" class="item-details">
                <div class="detail-grid">
                  <div class="detail-box">
                    <span class="detail-label">Закупка / landed</span>
                    <strong class="mono">{{ formatReportAmount(item, 'unit_purchase_price', item.unit_purchase_price) }} / {{ formatReportAmount(item, 'landed_cost_per_unit', item.landed_cost_per_unit) }}</strong>
                  </div>
                  <div class="detail-box">
                    <span class="detail-label">Текущая цена</span>
                    <strong class="mono">{{ formatReportAmount(item, 'current_unit_price', item.current_unit_price) }}</strong>
                  </div>
                  <div class="detail-box">
                    <span class="detail-label">Факт выручки / COGS</span>
                    <strong class="mono">{{ formatReportAmount(item, 'revenue', item.revenue) }} / {{ formatReportAmount(item, 'cogs', item.cogs) }}</strong>
                  </div>
                  <div class="detail-box">
                    <span class="detail-label">Markup</span>
                    <strong class="mono">{{ formatPercent(item.markup_percent) }}</strong>
                  </div>
                  <div class="detail-box">
                    <span class="detail-label">Инвестор / бизнес</span>
                    <strong class="mono">{{ formatReportAmount(item, 'investor_profit', item.investor_profit) }} / {{ formatReportAmount(item, 'business_profit', item.business_profit) }}</strong>
                  </div>
                  <div class="detail-box">
                    <span class="detail-label">Остаток / прогноз</span>
                    <strong class="mono">{{ formatReportAmount(item, 'remaining_landed_cost', item.remaining_landed_cost) }} / {{ formatReportAmount(item, 'projected_revenue', item.projected_revenue) }}</strong>
                  </div>
                  <div class="detail-box">
                    <span class="detail-label">Прогноз инвестора</span>
                    <strong class="mono">{{ formatReportAmount(item, 'projected_investor_profit', item.projected_investor_profit) }}</strong>
                  </div>
                  <div class="detail-box">
                    <span class="detail-label">Прогноз бизнеса</span>
                    <strong class="mono">{{ formatReportAmount(item, 'projected_business_profit', item.projected_business_profit) }}</strong>
                  </div>
                </div>
              </div>
            </article>
          </div>
        </section>

        <section class="section split-section">
          <div class="section-head">
            <div>
              <p class="section-kicker">Ownership and balance</p>
              <h3 class="section-title">Капитал и движения</h3>
            </div>
            <Wallet :size="18" :stroke-width="2" class="section-icon" />
          </div>

          <div v-if="participantTotals.length" class="participant-list">
            <article v-for="participant in participantTotals" :key="participant.partner_id" class="participant-row">
              <div class="participant-main">
                <div class="participant-title-row">
                  <strong class="participant-name">{{ participant.partner_name }}</strong>
                  <span class="participant-badge">{{ participant.role === 'INVESTOR' ? 'Инвестор' : 'Бизнес' }}</span>
                </div>
                <div class="participant-meta">
                  <span>План {{ formatAmount(participant.planned_capital_share, participant.contract_currency) }}</span>
                  <span>Внёс {{ formatAmount(participant.contributed_amount, participant.contract_currency) }}</span>
                  <span>Нетто {{ formatAmount(participant.net_capital, participant.contract_currency) }}</span>
                </div>
              </div>
              <div class="participant-side">
                <strong class="mono">{{ formatRatioPercent(participant.actual_capital_share) }}</strong>
                <span class="participant-side-note">Профит {{ formatRatioPercent(participant.planned_profit_share) }}</span>
              </div>
            </article>
          </div>

          <div v-if="visibleHistory.length" class="history-list">
            <div class="history-head">
              <span class="section-kicker">Последние движения</span>
              <button class="inline-link" type="button" @click="openOperationalCard">Полная история</button>
            </div>
            <article v-for="entry in visibleHistory" :key="entry.id" class="history-row">
              <div class="history-main">
                <strong class="history-title">{{ entry.title }}</strong>
                <span class="history-meta">
                  {{ formatDateTime(entry.date) }}
                  <template v-if="entry.partner_name"> · {{ entry.partner_name }}</template>
                </span>
                <span v-if="entry.note" class="history-note">{{ entry.note }}</span>
              </div>
              <strong :class="historyAmountClass(entry.kind)">
                {{ historyAmountLabel(entry) }}
              </strong>
            </article>
          </div>
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped>
.page {
  min-height: 100%;
  background: var(--color-bg);
}

.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 18px 16px 14px;
  border-bottom: 1px solid var(--color-border);
  background: color-mix(in srgb, var(--color-surface) 92%, white 8%);
}

.header-copy {
  min-width: 0;
  flex: 1;
}

.title {
  margin: 0;
  font-size: 22px;
  line-height: 1.1;
}

.subtitle {
  margin: 4px 0 0;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.icon-btn,
.ghost-btn {
  border: 0;
  background: transparent;
  color: var(--color-text);
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 12px;
}

.ghost-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 12px;
  color: var(--color-brand-700);
  background: color-mix(in srgb, var(--color-brand-500) 10%, white 90%);
  font-size: 13px;
  font-weight: 600;
}

.content {
  padding: 16px;
  display: grid;
  gap: 14px;
}

.hero,
.section,
.summary-band {
  border: 1px solid var(--color-border);
  background: var(--color-surface);
}

.hero {
  display: grid;
  gap: 16px;
  padding: 18px;
  border-radius: 20px;
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--color-brand-500) 10%, white 90%), var(--color-surface));
}

.hero--error {
  background: color-mix(in srgb, var(--color-danger) 8%, white 92%);
}

.hero-kicker,
.section-kicker,
.metric-label,
.detail-label {
  margin: 0;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.hero-title,
.section-title {
  margin: 0;
  font-size: 20px;
  line-height: 1.15;
}

.hero-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-top: 8px;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.hero-value {
  display: grid;
  gap: 4px;
}

.report-currency-switch {
  justify-self: start;
  display: inline-grid;
  grid-template-columns: repeat(2, minmax(44px, 1fr));
  gap: 2px;
  padding: 3px;
  border-radius: 999px;
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-subtle);
}

.report-currency-switch button {
  min-height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  color: var(--color-text-secondary);
  font-size: 12px;
  font-weight: 700;
}

.report-currency-switch button.active {
  background: var(--color-bg-elevated);
  color: var(--color-brand-700);
}

.hero-label,
.hero-note {
  font-size: 13px;
  color: var(--color-text-secondary);
}

.hero-amount {
  font-size: clamp(28px, 5vw, 38px);
  line-height: 1;
}

.summary-band {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  overflow: hidden;
  border-radius: 18px;
}

.summary-metric {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  background: var(--color-surface);
}

.metric-value {
  font-size: 18px;
  line-height: 1.1;
}

.section {
  display: grid;
  gap: 14px;
  padding: 16px;
  border-radius: 18px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.section-icon {
  color: var(--color-text-secondary);
}

.formula-list,
.item-list,
.participant-list,
.history-list {
  display: grid;
  gap: 10px;
}

.formula-row,
.participant-row,
.history-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.formula-row {
  padding: 12px 0;
  border-bottom: 1px solid var(--color-border);
}

.formula-row:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

.item-row {
  border-bottom: 1px solid var(--color-border);
}

.item-row:last-child {
  border-bottom: 0;
}

.item-toggle {
  width: 100%;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 0;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
}

.item-main,
.participant-main,
.history-main {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.item-title-row,
.participant-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.item-title,
.participant-name,
.history-title {
  font-size: 16px;
}

.item-badge,
.participant-badge {
  padding: 5px 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-brand-500) 9%, white 91%);
  color: var(--color-brand-700);
  font-size: 12px;
  font-weight: 600;
}

.item-meta,
.participant-meta,
.history-meta,
.history-note {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 12px;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.item-side,
.participant-side {
  display: grid;
  justify-items: end;
  gap: 4px;
  text-align: right;
}

.item-profit {
  font-size: 18px;
  line-height: 1.1;
}

.item-projection,
.participant-side-note {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.item-chevron {
  color: var(--color-text-secondary);
  transition: transform 180ms ease;
}

.item-chevron.open {
  transform: rotate(180deg);
}

.item-details {
  padding: 0 0 14px;
}

.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.detail-box {
  display: grid;
  gap: 6px;
  padding: 12px;
  border-radius: 14px;
  background: color-mix(in srgb, var(--color-border) 28%, white 72%);
}

.split-section {
  gap: 18px;
}

.history-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.history-amount {
  white-space: nowrap;
}

.inline-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--color-brand-700);
  font-size: 13px;
  font-weight: 600;
}

.mono,
.tabular-nums {
  font-variant-numeric: tabular-nums;
}

.muted {
  margin: 0;
  color: var(--color-text-secondary);
}

.positive {
  color: var(--color-success);
}

.negative {
  color: var(--color-danger);
}

@media (min-width: 768px) {
  .content {
    grid-template-columns: minmax(0, 1fr);
    max-width: 1120px;
    margin: 0 auto;
    padding: 24px;
  }

  .hero {
    grid-template-columns: minmax(0, 1.4fr) minmax(220px, 0.8fr);
    align-items: end;
  }

  .summary-band {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .detail-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
</style>
