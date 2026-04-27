<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, RefreshCcw, Scale, ScrollText, Wallet, Landmark, PackageSearch } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'

import {
  fetchSaleExplanation,
  type SaleExplanation,
  type SaleExplanationLine,
} from '@/api/sales'
import { formatPrice } from '@/utils/currency'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const error = ref<string | null>(null)
const explanation = ref<SaleExplanation | null>(null)

const saleId = computed(() => Number(route.params.id))
const sale = computed(() => explanation.value?.sale ?? null)

function formatAmount(value: string, currency = 'UZS'): string {
  return formatPrice(value, currency)
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

function paymentLabel(method: string | null | undefined): string {
  if (!method) return 'Не указано'
  const normalized = method.toUpperCase()
  if (normalized === 'CASH') return 'Наличные'
  if (normalized === 'CARD') return 'Карта'
  if (normalized === 'TRANSFER') return 'Перевод'
  if (normalized === 'CREDIT') return 'В долг'
  return method
}

function paymentMethodsLabel(methods: string[]): string {
  if (!methods.length) return 'Не указано'
  return methods.map((method) => paymentLabel(method)).join(' + ')
}

function partnerRoleLabel(role: string): string {
  return role === 'INVESTOR' ? 'Инвестор' : role === 'OPERATOR' ? 'Бизнес' : role
}

function procurementTypeLabel(type: string): string {
  if (type === 'PARTNERSHIP') return 'Партнёрская закупка'
  if (type === 'MUSHARAKA') return 'Мушарака'
  if (type === 'OWN_FUNDS') return 'Свои средства'
  if (type === 'DISTRIBUTOR') return 'Дистрибутор'
  return type
}

function procurementStatusLabel(status: string): string {
  if (status === 'RECEIVED') return 'Оприходована'
  if (status === 'OPEN') return 'Открыта'
  if (status === 'CLOSED') return 'Закрыта'
  if (status === 'CANCELLED') return 'Отменена'
  return status
}

function openProcurement(line: SaleExplanationLine): void {
  if (!line.procurement) return
  router.push({ name: 'procurement-detail', params: { id: line.procurement.id } })
}

async function load(): Promise<void> {
  if (!Number.isFinite(saleId.value) || saleId.value <= 0) {
    error.value = 'Некорректный ID продажи'
    return
  }

  loading.value = true
  error.value = null
  try {
    explanation.value = await fetchSaleExplanation(saleId.value)
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Не удалось загрузить объяснение продажи'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-header">
      <button class="icon-btn" type="button" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>
      <h1 class="title">Объяснение продажи</h1>
      <button class="icon-btn" type="button" aria-label="Обновить" @click="load">
        <RefreshCcw :size="18" :stroke-width="2" />
      </button>
    </header>

    <main class="content">
      <section v-if="loading" class="panel">
        <p class="muted">Загрузка объяснения...</p>
      </section>

      <section v-else-if="error" class="panel panel--error">
        <p>{{ error }}</p>
      </section>

      <template v-else-if="sale && explanation">
        <section class="hero-panel">
          <div class="hero-copy">
            <p class="hero-kicker">Продажа #{{ sale.id }}</p>
            <p class="hero-title">Почему эта цифра такая</p>
            <p class="muted">
              {{ formatDateTime(sale.created_at) }} · {{ sale.location_name }} · {{ sale.customer_name || 'Без клиента' }}
            </p>
            <p class="muted">{{ paymentMethodsLabel(sale.payment_methods) }}</p>
          </div>
          <strong class="hero-amount tabular-nums">{{ formatAmount(sale.gross_profit) }}</strong>
        </section>

        <section class="summary-grid">
          <article class="summary-tile">
            <span class="label">Выручка</span>
            <strong class="value tabular-nums">{{ formatAmount(sale.revenue) }}</strong>
          </article>
          <article class="summary-tile">
            <span class="label">Полная себестоимость</span>
            <strong class="value tabular-nums">{{ formatAmount(sale.landed_cost) }}</strong>
          </article>
          <article class="summary-tile">
            <span class="label">Инвесторы</span>
            <strong class="value tabular-nums">{{ formatAmount(sale.investor_profit) }}</strong>
          </article>
          <article class="summary-tile">
            <span class="label">Бизнес</span>
            <strong class="value tabular-nums">{{ formatAmount(sale.business_profit) }}</strong>
          </article>
        </section>

        <section class="panel">
          <div class="section-head">
            <div>
              <p class="section-kicker">Логика суммы</p>
              <h2 class="section-title">Формула</h2>
            </div>
            <Scale :size="18" :stroke-width="2" class="section-icon" />
          </div>
          <div class="rows">
            <div class="row">
              <span>1. Выручка продажи</span>
              <strong class="mono">{{ formatAmount(sale.revenue) }}</strong>
            </div>
            <div class="row">
              <span>2. Минус полная landed cost</span>
              <strong class="mono">{{ formatAmount(sale.landed_cost) }}</strong>
            </div>
            <div class="row row--accent">
              <span>3. Валовая прибыль</span>
              <strong class="mono">{{ formatAmount(sale.gross_profit) }}</strong>
            </div>
            <div class="row">
              <span>4. Доля инвесторов</span>
              <strong class="mono">{{ formatAmount(sale.investor_profit) }}</strong>
            </div>
            <div class="row">
              <span>5. Доля бизнеса</span>
              <strong class="mono">{{ formatAmount(sale.business_profit) }}</strong>
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="section-head">
            <div>
              <p class="section-kicker">Sale line -> lot -> procurement</p>
              <h2 class="section-title">Строки продажи</h2>
            </div>
            <PackageSearch :size="18" :stroke-width="2" class="section-icon" />
          </div>
          <div class="stack">
            <article v-for="line in explanation.lines" :key="line.sale_line_id" class="trace-card">
              <div class="trace-card__head">
                <div>
                  <h3 class="trace-card__title">{{ line.product_name }}</h3>
                  <p class="trace-card__meta">Строка #{{ line.sale_line_id }} · {{ line.quantity }} шт. · lot #{{ line.lot.id }}</p>
                </div>
                <strong class="trace-card__amount tabular-nums">{{ formatAmount(line.gross_profit) }}</strong>
              </div>

              <div class="detail-grid">
                <div class="detail-box">
                  <span class="label">Выручка</span>
                  <strong class="mono">{{ formatAmount(line.revenue) }}</strong>
                </div>
                <div class="detail-box">
                  <span class="label">Закупочная себестоимость</span>
                  <strong class="mono">{{ formatAmount(line.purchase_cost) }}</strong>
                </div>
                <div class="detail-box">
                  <span class="label">Полная себестоимость</span>
                  <strong class="mono">{{ formatAmount(line.landed_cost) }}</strong>
                </div>
                <div class="detail-box">
                  <span class="label">Маржа</span>
                  <strong class="mono">{{ Number(line.margin_percent).toLocaleString('ru-RU', { maximumFractionDigits: 2 }) }}%</strong>
                </div>
              </div>

              <div class="trace-subsection">
                <div class="row">
                  <span>Lot получен</span>
                  <span class="mono">{{ formatDateTime(line.lot.received_at) }}</span>
                </div>
                <div class="row">
                  <span>Lot остаток</span>
                  <span class="mono">{{ line.lot.quantity_remaining }} / {{ line.lot.quantity_initial }}</span>
                </div>
              </div>

              <div v-if="line.procurement" class="trace-subsection">
                <div class="row">
                  <span>Источник закупки</span>
                  <span class="mono">#{{ line.procurement.id }} · {{ procurementTypeLabel(line.procurement.procurement_type) }}</span>
                </div>
                <div class="row">
                  <span>Статус</span>
                  <span class="mono">{{ procurementStatusLabel(line.procurement.status) }}</span>
                </div>
                <div class="row">
                  <span>Поставщик</span>
                  <span class="mono">{{ line.procurement.supplier_name || '—' }}</span>
                </div>
                <button class="link-btn" type="button" @click="openProcurement(line)">
                  Открыть закупку
                </button>
              </div>

              <div class="trace-subsection">
                <p class="subsection-title">Распределение прибыли</p>
                <div v-if="line.partner_split.length === 0" class="muted">Нет partner split для этой строки</div>
                <div v-else class="split-list">
                  <div v-for="split in line.partner_split" :key="`${line.sale_line_id}-${split.partner_id}-${split.role}`" class="split-chip">
                    <span>{{ split.partner_name }} · {{ partnerRoleLabel(split.role) }}</span>
                    <strong class="mono">{{ formatAmount(split.profit_amount) }}</strong>
                  </div>
                </div>
              </div>
            </article>
          </div>
        </section>

        <section class="panel">
          <div class="section-head">
            <div>
              <p class="section-kicker">Payments -> cash / receivable</p>
              <h2 class="section-title">Оплаты и долг</h2>
            </div>
            <Wallet :size="18" :stroke-width="2" class="section-icon" />
          </div>

          <div class="stack stack--tight">
            <div v-for="payment in explanation.payments" :key="payment.id" class="row-card">
              <div>
                <strong>{{ paymentLabel(payment.method) }}</strong>
                <p class="muted">{{ formatDateTime(payment.date) }} · {{ payment.currency.toUpperCase() }}</p>
              </div>
              <strong class="mono">{{ formatAmount(payment.amount, payment.currency) }}</strong>
            </div>
          </div>

          <div v-if="explanation.cash_entries.length > 0" class="trace-subsection">
            <p class="subsection-title">Кассовые записи</p>
            <div class="stack stack--tight">
              <div v-for="entry in explanation.cash_entries" :key="entry.id" class="row-card">
                <div>
                  <strong>{{ entry.account_name }}</strong>
                  <p class="muted">{{ paymentLabel(entry.payment_method) }} · {{ entry.direction }}</p>
                </div>
                <strong class="mono">{{ formatAmount(entry.amount) }}</strong>
              </div>
            </div>
          </div>

          <div v-if="explanation.receivable_entries.length > 0" class="trace-subsection">
            <p class="subsection-title">Receivable ledger</p>
            <div class="stack stack--tight">
              <div v-for="entry in explanation.receivable_entries" :key="entry.id" class="row-card">
                <div>
                  <strong>{{ entry.entry_type }}</strong>
                  <p class="muted">{{ entry.source_ref }}</p>
                </div>
                <strong class="mono">{{ formatAmount(entry.amount, entry.currency) }}</strong>
              </div>
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="section-head">
            <div>
              <p class="section-kicker">Ledger + journal consequences</p>
              <h2 class="section-title">Финансовые следы</h2>
            </div>
            <Landmark :size="18" :stroke-width="2" class="section-icon" />
          </div>

          <div v-if="explanation.ledger_entries.length > 0" class="trace-subsection">
            <p class="subsection-title">Партнёрский ledger</p>
            <div class="stack stack--tight">
              <div v-for="entry in explanation.ledger_entries" :key="entry.id" class="row-card">
                <div>
                  <strong>{{ entry.partner_name }} · {{ partnerRoleLabel(entry.partner_role) }}</strong>
                  <p class="muted">{{ entry.entry_type }} · {{ entry.source_ref }}</p>
                </div>
                <strong class="mono">{{ formatAmount(entry.amount, entry.currency) }}</strong>
              </div>
            </div>
          </div>

          <div class="trace-subsection">
            <p class="subsection-title">Journal entries</p>
            <div class="stack">
              <article v-for="journal in explanation.journal_entries" :key="journal.id" class="journal-card">
                <div class="journal-card__head">
                  <div>
                    <strong>#{{ journal.id }}</strong>
                    <p class="muted">{{ journal.description }}</p>
                  </div>
                  <span class="mono">{{ formatDateTime(journal.date) }}</span>
                </div>
                <div class="stack stack--tight">
                  <div v-for="line in journal.lines" :key="line.id" class="row-card row-card--journal">
                    <div>
                      <strong>{{ line.account_code }}</strong>
                      <p class="muted">{{ line.account_name }}</p>
                    </div>
                    <div class="journal-values mono">
                      <span>DR {{ formatAmount(line.debit) }}</span>
                      <span>CR {{ formatAmount(line.credit) }}</span>
                    </div>
                  </div>
                </div>
              </article>
            </div>
          </div>
        </section>

        <section v-if="sale.notes" class="panel">
          <div class="section-head">
            <div>
              <p class="section-kicker">Комментарий операции</p>
              <h2 class="section-title">Notes</h2>
            </div>
            <ScrollText :size="18" :stroke-width="2" class="section-icon" />
          </div>
          <p>{{ sale.notes }}</p>
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped>
.page {
  min-height: 100%;
  background:
    radial-gradient(circle at top right, color-mix(in srgb, var(--color-brand-50) 68%, transparent) 0%, transparent 30%),
    var(--color-bg-primary);
}

.page-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: grid;
  grid-template-columns: 40px 1fr 40px;
  align-items: center;
  min-height: var(--header-height);
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-bg-primary) 92%, white 8%);
  backdrop-filter: blur(10px);
}

.title {
  text-align: center;
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.icon-btn {
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-primary);
  border-radius: var(--radius-md);
}

.content {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  padding-bottom: calc(var(--bottom-nav-height) + 24px);
}

.panel,
.hero-panel,
.summary-tile,
.trace-card,
.row-card,
.journal-card {
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-bg-elevated) 94%, white 6%);
  box-shadow: var(--shadow-sm);
}

.panel,
.trace-card,
.journal-card {
  padding: var(--space-4);
}

.panel--error {
  color: var(--color-danger-500);
}

.hero-panel {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  padding: var(--space-5);
  background: linear-gradient(180deg, color-mix(in srgb, var(--color-brand-50) 60%, white) 0%, var(--color-bg-elevated) 100%);
}

.hero-copy {
  display: grid;
  gap: 6px;
}

.hero-kicker,
.section-kicker {
  font-size: var(--text-2xs);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-tertiary);
}

.hero-title {
  font-size: clamp(1.35rem, 2vw, 1.8rem);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.hero-amount {
  font-size: clamp(1.25rem, 2vw, 1.65rem);
  color: var(--color-text-primary);
}

.summary-grid,
.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}

.summary-tile,
.detail-box {
  padding: var(--space-4);
}

.label,
.muted {
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
}

.value {
  font-size: var(--text-lg);
  color: var(--color-text-primary);
}

.section-head,
.trace-card__head,
.journal-card__head,
.row,
.row-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.section-head {
  margin-bottom: var(--space-4);
}

.section-title,
.trace-card__title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.section-icon {
  color: var(--color-brand-600);
}

.rows,
.stack,
.split-list {
  display: grid;
  gap: var(--space-3);
}

.stack--tight {
  gap: var(--space-2);
}

.row {
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--color-border-subtle);
}

.row:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

.row:first-child {
  padding-top: 0;
}

.row--accent strong {
  color: var(--color-brand-700);
}

.mono,
.tabular-nums {
  font-variant-numeric: tabular-nums;
}

.trace-card__meta {
  margin-top: 4px;
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
}

.trace-card__amount {
  color: var(--color-text-primary);
}

.trace-subsection {
  margin-top: var(--space-4);
  display: grid;
  gap: var(--space-3);
}

.subsection-title {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.split-chip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3);
  border-radius: var(--radius-lg);
  background: var(--color-bg-secondary);
}

.link-btn {
  justify-self: start;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-full);
  background: var(--color-brand-50);
  color: var(--color-brand-700);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.row-card {
  padding: var(--space-3);
}

.row-card--journal {
  align-items: flex-start;
}

.journal-values {
  display: grid;
  gap: 4px;
  text-align: right;
}

@media (max-width: 640px) {
  .summary-grid,
  .detail-grid {
    grid-template-columns: 1fr;
  }

  .hero-panel {
    flex-direction: column;
  }

  .row,
  .row-card,
  .trace-card__head,
  .journal-card__head {
    align-items: flex-start;
    flex-direction: column;
  }

  .journal-values {
    text-align: left;
  }
}
</style>
