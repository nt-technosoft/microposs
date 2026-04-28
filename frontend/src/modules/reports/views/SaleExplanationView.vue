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

function paymentTrace(payment: { amount: string; currency: string; fx_rate: string; functional_amount_uzs?: string }): string {
  const currency = String(payment.currency || 'UZS').toUpperCase()
  if (currency === 'UZS') return formatAmount(payment.amount, 'UZS')
  const functional = payment.functional_amount_uzs || String((Number(payment.amount) || 0) * (Number(payment.fx_rate) || 0))
  return `${formatAmount(payment.amount, currency)} × ${Number(payment.fx_rate || 0).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} = ${formatAmount(functional, 'UZS')}`
}

function lineOperationTrace(line: SaleExplanationLine): string {
  const currency = String(line.operation_currency || 'UZS').toUpperCase()
  if (currency === 'UZS') return `${formatAmount(line.unit_price, 'UZS')} / шт.`
  return `${formatAmount(line.operation_unit_price || line.unit_price, currency)} / шт. · ${formatAmount(line.unit_price, 'UZS')}`
}

function sourceRefLabel(rawRef: string | null | undefined): string {
  if (!rawRef) return ''
  const [type, id] = rawRef.split(':')
  const labels: Record<string, string> = {
    sale: 'Продажа',
    sale_line: 'Строка продажи',
    sale_payment: 'Оплата продажи',
    customer_payment: 'Платёж клиента',
    return: 'Возврат',
    dividend_payment: 'Выплата прибыли',
    procurement: 'Приход',
  }
  return id ? `${labels[type] ?? type} #${id}` : (labels[type] ?? rawRef)
}

function journalDescriptionLabel(value: string | null | undefined): string {
  const text = String(value || '').trim()
  if (!text) return 'Финансовая проводка'
  const saleCogs = text.match(/^Sale #(\d+) COGS$/i)
  if (saleCogs) return `Себестоимость продажи #${saleCogs[1]}`
  const saleCostOfGoods = text.match(/^Sale #(\d+) cost of goods$/i)
  if (saleCostOfGoods) return `Себестоимость товара по продаже #${saleCostOfGoods[1]}`
  const saleInventoryReduction = text.match(/^Sale #(\d+) inventory reduction$/i)
  if (saleInventoryReduction) return `Списание товара по продаже #${saleInventoryReduction[1]}`
  const sale = text.match(/^Sale #(\d+)$/i)
  if (sale) return `Выручка продажи #${sale[1]}`
  const salePayment = text.match(/^Sale payment #(\d+)$/i)
  if (salePayment) return `Оплата продажи #${salePayment[1]}`
  const saleCredit = text.match(/^Sale credit #(\d+)$/i)
  if (saleCredit) return `Продажа в долг #${saleCredit[1]}`
  const correctedPayment = text.match(/^Corrected sale payment #(\d+)$/i)
  if (correctedPayment) return `Исправленная оплата продажи #${correctedPayment[1]}`
  if (text.toLowerCase().startsWith('reversal')) return 'Сторно проводки'
  return text
}

function accountNameLabel(value: string | null | undefined): string {
  const text = String(value || '').trim()
  const normalized = text.toUpperCase()
  const labels: Record<string, string> = {
    'KASSA SOM': 'Касса UZS',
    'KASSA UZS': 'Касса UZS',
    'KASSA USD': 'Касса USD',
  }
  return labels[normalized] ?? text
}

function journalLineDescriptionLabel(line: { description?: string; debit: string; credit: string }): string {
  const text = journalDescriptionLabel(line.description)
  const debit = Number(line.debit || 0)
  const credit = Number(line.credit || 0)
  if (debit > 0 && credit <= 0) return `${text} · дебет`
  if (credit > 0 && debit <= 0) return `${text} · кредит`
  return text
}

function cashDirectionLabel(direction: string | null | undefined): string {
  if (String(direction).toUpperCase() === 'IN') return 'Приход денег'
  if (String(direction).toUpperCase() === 'OUT') return 'Расход денег'
  return direction || 'Движение денег'
}

function receivableEntryLabel(entryType: string): string {
  const labels: Record<string, string> = {
    DEBT_ACCRUED: 'Долг начислен',
    REPAYMENT: 'Погашение',
    ADJUSTMENT: 'Корректировка',
    WRITE_OFF: 'Списание',
  }
  return labels[entryType] ?? entryType
}

function partnerLedgerEntryLabel(entryType: string): string {
  const labels: Record<string, string> = {
    CAPITAL_IN: 'Внос капитала',
    CAPITAL_OUT: 'Вывод капитала',
    PROFIT_ACCRUED: 'Начислена прибыль',
    PROFIT_REVERSED: 'Сторно прибыли',
    DIVIDEND_PAID: 'Выплачена прибыль',
    LOSS_INCURRED: 'Зафиксирован убыток',
  }
  return labels[entryType] ?? entryType
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
  if (status === 'PARTIALLY_RECEIVED') return 'Частично оприходована'
  if (status === 'RECEIVED') return 'Завершена'
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
      <h1 class="title">Аудит продажи</h1>
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
            <p class="hero-title">Разбор прибыли и себестоимости</p>
            <p class="muted">
              {{ formatDateTime(sale.created_at) }} · {{ sale.location_name }} · {{ sale.customer_name || 'Без клиента' }}
            </p>
            <p class="muted">{{ paymentMethodsLabel(sale.payment_methods) }}</p>
          </div>
          <div class="hero-side">
            <span class="label">Валовая прибыль</span>
            <strong class="hero-amount tabular-nums">{{ formatAmount(sale.gross_profit) }}</strong>
          </div>
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
              <span>2. Минус полная себестоимость</span>
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
              <p class="section-kicker">Товар → партия → приход</p>
              <h2 class="section-title">Товары и партии</h2>
            </div>
            <PackageSearch :size="18" :stroke-width="2" class="section-icon" />
          </div>
          <div class="stack">
            <article v-for="line in explanation.lines" :key="line.sale_line_id" class="trace-card">
              <div class="trace-card__head">
                <div>
                  <h3 class="trace-card__title">{{ line.product_name }}</h3>
                  <p class="trace-card__meta">Продано {{ line.quantity }} шт. · {{ lineOperationTrace(line) }} · Партия #{{ line.lot.id }}</p>
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
                  <span>Партия получена</span>
                  <span class="mono">{{ formatDateTime(line.lot.received_at) }}</span>
                </div>
                <div class="row">
                  <span>Остаток партии</span>
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
                <div v-if="line.partner_split.length === 0" class="muted">Для этой строки нет распределения по партнёрам</div>
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
              <p class="section-kicker">Оплаты, касса, долг</p>
              <h2 class="section-title">Деньги и долг</h2>
            </div>
            <Wallet :size="18" :stroke-width="2" class="section-icon" />
          </div>

          <div class="stack stack--tight">
            <div v-for="payment in explanation.payments" :key="payment.id" class="row-card">
              <div>
                <strong>{{ paymentLabel(payment.method) }}</strong>
                <p class="muted">{{ formatDateTime(payment.date) }}</p>
              </div>
              <strong class="mono">{{ paymentTrace(payment) }}</strong>
            </div>
          </div>

          <div v-if="explanation.cash_entries.length > 0" class="trace-subsection">
            <p class="subsection-title">Движение по счетам</p>
            <div class="stack stack--tight">
              <div v-for="entry in explanation.cash_entries" :key="entry.id" class="row-card">
                <div>
                  <strong>{{ accountNameLabel(entry.account_name) }}</strong>
                  <p class="muted">{{ paymentLabel(entry.payment_method) }} · {{ cashDirectionLabel(entry.direction) }}</p>
                </div>
                <strong class="mono">{{ formatAmount(entry.amount, entry.currency || 'UZS') }}</strong>
              </div>
            </div>
          </div>

          <div v-if="explanation.receivable_entries.length > 0" class="trace-subsection">
            <p class="subsection-title">Долг покупателя</p>
            <div class="stack stack--tight">
              <div v-for="entry in explanation.receivable_entries" :key="entry.id" class="row-card">
                <div>
                  <strong>{{ receivableEntryLabel(entry.entry_type) }}</strong>
                  <p class="muted">{{ sourceRefLabel(entry.source_ref) }}</p>
                </div>
                <strong class="mono">{{ formatAmount(entry.amount, entry.currency) }}</strong>
              </div>
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="section-head">
            <div>
              <p class="section-kicker">Партнёры и проводки</p>
              <h2 class="section-title">Финансовые записи</h2>
            </div>
            <Landmark :size="18" :stroke-width="2" class="section-icon" />
          </div>

          <div v-if="explanation.ledger_entries.length > 0" class="trace-subsection">
            <p class="subsection-title">Партнёрский учёт</p>
            <div class="stack stack--tight">
              <div v-for="entry in explanation.ledger_entries" :key="entry.id" class="row-card">
                <div>
                  <strong>{{ entry.partner_name }} · {{ partnerRoleLabel(entry.partner_role) }}</strong>
                  <p class="muted">{{ partnerLedgerEntryLabel(entry.entry_type) }} · {{ sourceRefLabel(entry.source_ref) }}</p>
                </div>
                <strong class="mono">{{ formatAmount(entry.amount, entry.currency) }}</strong>
              </div>
            </div>
          </div>

          <div class="trace-subsection">
            <p class="subsection-title">Проводки</p>
            <div class="stack">
              <article v-for="journal in explanation.journal_entries" :key="journal.id" class="journal-card">
                <div class="journal-card__head">
                  <div>
                    <strong>{{ journalDescriptionLabel(journal.description) }}</strong>
                    <p class="muted">Проводка #{{ journal.id }}</p>
                  </div>
                  <span class="mono">{{ formatDateTime(journal.date) }}</span>
                </div>
                <div class="stack stack--tight">
                  <div v-for="line in journal.lines" :key="line.id" class="row-card row-card--journal">
                    <div>
                      <strong>{{ accountNameLabel(line.account_name) }}</strong>
                      <p class="muted">Счёт {{ line.account_code }} · {{ journalLineDescriptionLabel(line) }}</p>
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
              <h2 class="section-title">Комментарий</h2>
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
  max-width: 100%;
  overflow-x: hidden;
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
  max-width: 100%;
  overflow-x: hidden;
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
  min-width: 0;
  overflow: hidden;
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
  min-width: 0;
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
  overflow-wrap: anywhere;
}

.hero-amount {
  font-size: clamp(1.25rem, 2vw, 1.65rem);
  color: var(--color-text-primary);
}

.hero-side {
  display: grid;
  gap: 4px;
  justify-items: end;
  text-align: right;
  flex-shrink: 0;
  min-width: 0;
}

.summary-grid,
.detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}

.summary-tile,
.detail-box {
  display: grid;
  gap: 6px;
  padding: var(--space-4);
  min-width: 0;
  overflow: hidden;
}

.detail-box {
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: color-mix(in srgb, var(--color-bg-primary) 86%, white);
}

.label,
.muted {
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
}

.value {
  font-size: var(--text-lg);
  color: var(--color-text-primary);
  overflow-wrap: break-word;
  word-break: normal;
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

.trace-card__head > div,
.journal-card__head > div,
.row-card > div,
.row > span:first-child {
  min-width: 0;
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
  overflow-wrap: break-word;
  word-break: normal;
}

.trace-card__meta {
  margin-top: 4px;
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
  overflow-wrap: anywhere;
}

.trace-card__amount {
  color: var(--color-text-primary);
  overflow-wrap: break-word;
  word-break: normal;
}

.trace-subsection {
  margin-top: var(--space-4);
  display: grid;
  gap: var(--space-3);
  padding: var(--space-3);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-bg-primary) 88%, white);
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
  min-width: 0;
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
  min-width: 0;
  overflow: hidden;
}

.row-card > div strong,
.row-card > div p,
.journal-card__head strong,
.journal-card__head p {
  overflow-wrap: anywhere;
}

.row-card--journal {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: start;
}

.journal-values {
  display: grid;
  gap: 4px;
  text-align: right;
  min-width: max-content;
  padding-left: var(--space-2);
}

@media (max-width: 640px) {
  .content {
    padding: var(--space-3);
    padding-bottom: calc(var(--bottom-nav-height) + 24px);
  }

  .summary-grid,
  .detail-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-2);
  }

  .hero-panel {
    display: grid;
    align-items: start;
    gap: var(--space-3);
    padding: var(--space-4);
  }

  .trace-card__head,
  .journal-card__head {
    align-items: flex-start;
    flex-direction: column;
  }

  .hero-side {
    justify-items: start;
    text-align: left;
  }

  .row,
  .row-card {
    align-items: center;
    flex-direction: row;
  }

  .row-card > div,
  .row > span:first-child {
    min-width: 0;
  }

  .journal-values {
    text-align: right;
  }

  .row-card--journal {
    grid-template-columns: 1fr;
  }

  .row-card--journal .journal-values {
    text-align: left;
    min-width: 0;
    padding-left: 0;
  }
}

@media (max-width: 380px) {
  .summary-grid,
  .detail-grid {
    grid-template-columns: 1fr;
  }

  .row-card {
    align-items: flex-start;
    flex-direction: column;
  }

  .journal-values {
    text-align: left;
  }
}
</style>
