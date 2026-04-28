<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ChevronDown, ExternalLink, PackageSearch, Users } from 'lucide-vue-next'
import { fetchAgreementProfitabilityDetail, type AgreementProfitabilityDetail } from '@/api/finance'
import { formatPrice } from '@/utils/currency'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const error = ref('')
const report = ref<AgreementProfitabilityDetail | null>(null)
const expandedProcurementId = ref<number | null>(null)
const selectedReportCurrency = ref<'UZS' | 'USD' | ''>('')

const agreementId = computed(() => Number(route.params.id))
const summary = computed(() => report.value?.agreement ?? null)
const partners = computed(() => report.value?.partners ?? [])
const procurements = computed(() => report.value?.procurements ?? [])
const activeReportCurrency = computed(() => report.value?.report_currency?.currency ?? 'UZS')

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

function formatDate(value: string | null): string {
  if (!value) return '—'
  return new Date(value).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short', year: 'numeric' })
}

function balanceLabel(balances: Record<string, string>): string {
  const parts = Object.entries(balances)
    .filter(([, amount]) => Math.abs(Number(amount || 0)) > 0.000001)
    .map(([currency, amount]) => formatAmount(amount, currency))
  return parts.length ? parts.join(' · ') : '0'
}

function roleLabel(role: string): string {
  return role === 'INVESTOR' ? 'Инвестор' : 'Бизнес'
}

function displayPartnerName(name: string, role: string): string {
  return role === 'OPERATOR' ? 'Бизнес' : name
}

function formatRatio(value: string | number): string {
  const parsed = Number(value)
  if (!Number.isFinite(parsed)) return '0.00%'
  return `${(parsed * 100).toFixed(2)}%`
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

function toggleProcurement(id: number): void {
  expandedProcurementId.value = expandedProcurementId.value === id ? null : id
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    report.value = await fetchAgreementProfitabilityDetail(
      agreementId.value,
      selectedReportCurrency.value ? { report_currency: selectedReportCurrency.value } : undefined,
    )
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Не удалось загрузить отчёт договора'
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
    <header class="topbar">
      <button class="icon-btn" type="button" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="18" />
      </button>
      <h1>Отчёт договора</h1>
      <button class="icon-btn" type="button" aria-label="Договор" @click="router.push({ name: 'agreement-detail', params: { id: route.params.id } })">
        <ExternalLink :size="17" />
      </button>
    </header>

    <main class="content">
      <section v-if="loading" class="state">Загрузка...</section>
      <section v-else-if="error" class="state state-error">{{ error }}</section>

      <template v-else-if="summary">
        <section class="hero">
          <span>Инвестдоговор #{{ summary.agreement_id }} · {{ formatDate(summary.opened_at) }}</span>
          <div class="currency-switch" role="group" aria-label="Валюта отчёта договора">
            <button type="button" :class="{ active: activeReportCurrency === 'UZS' }" @click="setReportCurrency('UZS')">UZS</button>
            <button type="button" :class="{ active: activeReportCurrency === 'USD' }" @click="setReportCurrency('USD')">USD</button>
          </div>
          <strong>{{ formatReportAmount(summary, 'gross_profit', summary.gross_profit) }}</strong>
          <small>фактическая прибыль · прогноз {{ formatReportAmount(summary, 'projected_gross_profit', summary.projected_gross_profit) }}</small>
        </section>

        <section class="metric-grid">
          <div><span>Остаток договора</span><strong>{{ balanceLabel(summary.balances) }}</strong></div>
          <div><span>Выручка</span><strong>{{ formatReportAmount(summary, 'revenue', summary.revenue) }}</strong></div>
          <div><span>Себестоимость продаж</span><strong>{{ formatReportAmount(summary, 'cogs', summary.cogs) }}</strong></div>
          <div><span>Товар в наличии</span><strong>{{ formatReportAmount(summary, 'remaining_landed_cost', summary.remaining_landed_cost) }}</strong></div>
          <div><span>Уже принято</span><strong>{{ formatReportAmount(summary, 'received_landed_cost', summary.received_landed_cost) }}</strong></div>
          <div><span>Оплачено в пути</span><strong>{{ formatReportAmount(summary, 'pending_prepaid_cost', summary.pending_prepaid_cost) }}</strong></div>
          <div><span>Продано / остаток</span><strong>{{ summary.quantity_sold }} / {{ summary.remaining_quantity }}</strong></div>
          <div><span>Приходов</span><strong>{{ summary.procurements_count }}</strong></div>
        </section>

        <section class="section">
          <div class="section-head">
            <h2>Участники</h2>
            <Users :size="18" />
          </div>
          <article v-for="partner in partners" :key="partner.partner_id" class="row">
            <div>
              <strong>{{ partner.partner_name }}</strong>
              <span>
                {{ roleLabel(partner.role) }} · внес {{ formatAmount(partner.agreement_contributed, partner.agreement_currency) }}
                · в товар {{ formatAmount(partner.agreement_allocated, partner.agreement_currency) }}
              </span>
            </div>
            <div class="row-side">
              <strong>{{ formatReportAmount(partner, 'profit_pending_payout', partner.profit_pending_payout) }}</strong>
              <span>к выплате · остаток {{ formatAmount(partner.agreement_available, partner.agreement_currency) }}</span>
            </div>
          </article>
        </section>

        <section class="section">
          <div class="section-head">
            <h2>Связанные приходы</h2>
            <PackageSearch :size="18" />
          </div>
          <article v-for="procurement in procurements" :key="procurement.procurement_id" class="procurement-row">
            <button class="procurement-toggle" type="button" @click="toggleProcurement(procurement.procurement_id)">
              <div>
                <strong>#{{ procurement.procurement_id }} · {{ procurement.supplier_name || 'без поставщика' }}</strong>
                <span>{{ procurementStatusLabel(procurement.status) }} · на складе {{ formatReportAmount(procurement, 'received_landed_cost', procurement.received_landed_cost ?? '0') }} · в пути {{ formatReportAmount(procurement, 'pending_prepaid_cost', procurement.pending_prepaid_cost ?? '0') }}</span>
              </div>
              <div class="row-side">
                <strong>{{ formatReportAmount(procurement, 'gross_profit', procurement.gross_profit) }}</strong>
                <span>продано {{ formatReportAmount(procurement, 'cogs', procurement.cogs) }}</span>
              </div>
              <ChevronDown class="chevron" :class="{ open: expandedProcurementId === procurement.procurement_id }" :size="16" />
            </button>
            <div v-if="expandedProcurementId === procurement.procurement_id" class="procurement-detail">
              <div><span>Партии</span><strong>{{ procurement.receive_batches_count ?? 0 }}</strong></div>
              <div><span>В пути строк</span><strong>{{ procurement.pending_paid_items_count ?? 0 }}</strong></div>
              <div><span>Черновики</span><strong>{{ procurement.draft_items_count ?? 0 }}</strong></div>
              <div><span>Остаток</span><strong>{{ formatReportAmount(procurement, 'remaining_landed_cost', procurement.remaining_landed_cost) }}</strong></div>
              <div v-for="batch in procurement.receive_batches ?? []" :key="`batch-${procurement.procurement_id}-${batch.id}`" class="batch-share-row">
                <span>Партия #{{ batch.id }} · {{ batch.items_count }} поз.</span>
                <strong>{{ batch.display?.amounts?.total_inventory ? formatAmount(batch.display.amounts.total_inventory, batch.display.currency) : formatAmount(batch.total_inventory_uzs) }}</strong>
                <small v-for="allocation in batch.capital_allocations" :key="`batch-${batch.id}-${allocation.partner_id}`">
                  {{ displayPartnerName(allocation.partner_name, allocation.role) }}:
                  кап. {{ formatRatio(allocation.capital_share) }} · приб. {{ formatRatio(allocation.profit_share) }}
                </small>
              </div>
              <button type="button" class="open-report-btn" @click="router.push({ name: 'reports-procurement-profitability', params: { id: procurement.procurement_id } })">
                Открыть аудит прихода
              </button>
            </div>
          </article>
          <p v-if="procurements.length === 0" class="muted">Связанных приходов пока нет.</p>
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped>
.page { min-height:100%; background: var(--color-bg-primary); }
.topbar { position:sticky; top:0; z-index:var(--z-sticky); min-height:var(--header-height); display:grid; grid-template-columns:40px 1fr 40px; align-items:center; padding:0 var(--space-4); border-bottom:1px solid var(--color-border-subtle); background:var(--color-bg-primary); }
h1 { margin:0; text-align:center; font-size:var(--text-lg); font-weight:var(--font-semibold); }
.icon-btn { width:40px; height:40px; display:grid; place-items:center; color:var(--color-text-primary); }
.content { display:grid; gap:var(--space-3); padding:var(--space-4); padding-bottom:calc(var(--bottom-nav-height) + var(--space-5)); }
.hero { display:grid; gap:4px; padding:var(--space-4); border-radius:var(--radius-lg); background:var(--color-brand-800); color:white; }
.hero span,.hero small { color:color-mix(in srgb, white 72%, transparent); font-size:var(--text-xs); }
.hero strong { font-size:var(--text-2xl); }
.currency-switch { display:inline-grid; grid-template-columns:repeat(2, minmax(48px, 1fr)); gap:2px; justify-self:start; padding:3px; border-radius:999px; background:color-mix(in srgb, white 16%, transparent); border:1px solid color-mix(in srgb, white 14%, transparent); }
.currency-switch button { min-height:28px; padding:0 var(--space-2); border-radius:999px; color:color-mix(in srgb, white 78%, transparent); font-size:var(--text-xs); font-weight:var(--font-semibold); }
.currency-switch button.active { background:white; color:var(--color-brand-800); }
.metric-grid { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:var(--space-2); }
.metric-grid div,.section { border:1px solid var(--color-border-subtle); border-radius:var(--radius-md); background:var(--color-bg-elevated); }
.metric-grid div { display:grid; gap:3px; padding:var(--space-3); }
.metric-grid span,.row span,.muted { color:var(--color-text-secondary); font-size:var(--text-xs); }
.metric-grid strong,.row strong { color:var(--color-text-primary); font-size:var(--text-sm); }
.section { display:grid; gap:0; padding:var(--space-3); }
.section-head { display:flex; align-items:center; justify-content:space-between; gap:var(--space-2); padding-bottom:var(--space-2); }
h2 { margin:0; font-size:var(--text-base); font-weight:var(--font-semibold); }
.row { display:flex; align-items:flex-start; justify-content:space-between; gap:var(--space-3); padding:var(--space-3) 0; border-top:1px solid var(--color-border-subtle); text-align:left; }
.row > div { min-width:0; display:grid; gap:3px; }
.row-side { justify-items:end; text-align:right; }
.procurement-row { border-top:1px solid var(--color-border-subtle); }
.procurement-toggle { width:100%; display:grid; grid-template-columns:minmax(0, 1fr) auto 18px; align-items:center; gap:var(--space-3); padding:var(--space-3) 0; text-align:left; }
.procurement-toggle > div:first-child { min-width:0; display:grid; gap:3px; }
.chevron { color:var(--color-text-secondary); transition:transform .18s ease; }
.chevron.open { transform:rotate(180deg); }
.procurement-detail { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:var(--space-2); padding-bottom:var(--space-3); }
.procurement-detail div { display:grid; gap:2px; padding:var(--space-2); border-radius:var(--radius-md); background:var(--color-bg-primary); }
.procurement-detail span { color:var(--color-text-secondary); font-size:var(--text-xs); }
.procurement-detail strong { color:var(--color-text-primary); font-size:var(--text-sm); }
.procurement-detail .batch-share-row { grid-column:1 / -1; }
.batch-share-row small { color:var(--color-text-secondary); font-size:var(--text-xs); line-height:1.35; }
.open-report-btn { grid-column:1 / -1; min-height:36px; border-radius:var(--radius-md); background:var(--color-bg-primary); border:1px solid var(--color-border-subtle); color:var(--color-brand-700); font-size:var(--text-sm); font-weight:var(--font-semibold); }
.state { min-height:180px; display:grid; place-items:center; color:var(--color-text-secondary); }
.state-error { color:var(--color-error); }
@media (max-width: 520px) {
  .procurement-toggle { grid-template-columns:minmax(0, 1fr) 18px; align-items:start; }
  .procurement-toggle .row-side { grid-column:1; justify-items:start; text-align:left; }
  .chevron { grid-column:2; grid-row:1 / span 2; }
}
</style>
