<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ChevronDown } from 'lucide-vue-next'
import { fetchInvestorAgreementDetail } from '@/api/investors'
import type { AgreementProfitabilityDetail } from '@/api/finance'
import { formatPrice } from '@/utils/currency'

const route = useRoute()
const router = useRouter()

const report = ref<AgreementProfitabilityDetail | null>(null)
const loading = ref(false)
const error = ref('')
const expandedProcurementId = ref<number | null>(null)

const agreementId = computed(() => Number(route.params.id))
const summary = computed(() => report.value?.agreement ?? null)
const currentPartner = computed(() => report.value?.partners.find((row) => row.partner_id === report.value?.current_partner_id) ?? null)
const procurements = computed(() => report.value?.procurements ?? [])

function formatAmount(value: string | number, currency = 'UZS'): string {
  return formatPrice(value, currency)
}

function balanceLabel(balances: Record<string, string>): string {
  const parts = Object.entries(balances)
    .filter(([, amount]) => Math.abs(Number(amount || 0)) > 0.000001)
    .map(([currency, amount]) => formatAmount(amount, currency))
  return parts.length ? parts.join(' · ') : '0'
}

function toggleProcurement(id: number): void {
  expandedProcurementId.value = expandedProcurementId.value === id ? null : id
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

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    report.value = await fetchInvestorAgreementDetail(agreementId.value)
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : 'Не удалось загрузить договор'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <header class="topbar">
      <button class="icon-btn" type="button" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="18" />
      </button>
      <h1>Инвестдоговор #{{ route.params.id }}</h1>
      <span />
    </header>

    <main class="content">
      <section v-if="loading" class="state">Загрузка...</section>
      <section v-else-if="error" class="state state-error">{{ error }}</section>

      <template v-else-if="summary">
        <section class="hero">
          <span>Ваш результат</span>
          <strong>{{ formatAmount(currentPartner?.profit_pending_payout ?? '0') }}</strong>
          <small>к выплате · прибыль начислена {{ formatAmount(currentPartner?.profit_accrued ?? '0') }}</small>
        </section>

        <section class="metric-grid">
          <div><span>Внёс</span><strong>{{ formatAmount(currentPartner?.agreement_contributed ?? '0', currentPartner?.agreement_currency) }}</strong></div>
          <div><span>Ушло в товар</span><strong>{{ formatAmount(currentPartner?.agreement_allocated ?? '0', currentPartner?.agreement_currency) }}</strong></div>
          <div><span>Оплачено в пути</span><strong>{{ formatAmount(currentPartner?.pending_prepaid_cost_estimate_uzs ?? '0') }}</strong></div>
          <div><span>Остаток в договоре</span><strong>{{ formatAmount(currentPartner?.agreement_available ?? '0', currentPartner?.agreement_currency) }}</strong></div>
          <div><span>Общий баланс</span><strong>{{ balanceLabel(summary.balances) }}</strong></div>
          <div><span>На складе</span><strong>{{ formatAmount(summary.received_landed_cost) }}</strong></div>
          <div><span>Продано</span><strong>{{ formatAmount(summary.cogs) }}</strong></div>
          <div><span>Осталось в товаре</span><strong>{{ formatAmount(summary.remaining_landed_cost) }}</strong></div>
          <div><span>Факт. прибыль</span><strong>{{ formatAmount(summary.gross_profit) }}</strong></div>
          <div><span>Ожидаемая прибыль</span><strong>{{ formatAmount(summary.projected_gross_profit) }}</strong></div>
        </section>

        <section class="section">
          <h2>Связанные приходы</h2>
          <article v-for="procurement in procurements" :key="procurement.procurement_id" class="procurement-row">
            <button type="button" class="procurement-toggle" @click="toggleProcurement(procurement.procurement_id)">
              <div>
                <strong>#{{ procurement.procurement_id }} · {{ procurement.supplier_name || 'без поставщика' }}</strong>
                <span>{{ procurementStatusLabel(procurement.status) }} · прибыль {{ formatAmount(procurement.gross_profit) }}</span>
              </div>
              <ChevronDown class="chevron" :class="{ open: expandedProcurementId === procurement.procurement_id }" :size="16" />
            </button>
            <div v-if="expandedProcurementId === procurement.procurement_id" class="procurement-detail">
              <div><span>Продано</span><strong>{{ procurement.quantity_sold }}</strong></div>
              <div><span>Остаток</span><strong>{{ procurement.remaining_quantity }}</strong></div>
              <div><span>На складе</span><strong>{{ formatAmount(procurement.received_landed_cost ?? '0') }}</strong></div>
              <div><span>В пути</span><strong>{{ formatAmount(procurement.pending_prepaid_cost ?? '0') }}</strong></div>
              <div><span>Себестоимость остатка</span><strong>{{ formatAmount(procurement.remaining_landed_cost) }}</strong></div>
              <div><span>Прогноз прибыли</span><strong>{{ formatAmount(procurement.projected_gross_profit) }}</strong></div>
            </div>
          </article>
          <p v-if="procurements.length === 0" class="muted">Связанных приходов пока нет.</p>
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped>
.page { min-height:100%; background:var(--color-bg-primary); }
.topbar { position:sticky; top:0; z-index:var(--z-sticky); min-height:var(--header-height); display:grid; grid-template-columns:40px 1fr 40px; align-items:center; padding:0 var(--space-4); border-bottom:1px solid var(--color-border-subtle); background:var(--color-bg-primary); }
h1 { margin:0; text-align:center; font-size:var(--text-lg); font-weight:var(--font-semibold); }
.icon-btn { width:40px; height:40px; display:grid; place-items:center; color:var(--color-text-primary); }
.content { display:grid; gap:var(--space-3); padding:var(--space-4); padding-bottom:var(--space-8); }
.hero { display:grid; gap:4px; padding:var(--space-4); border-radius:var(--radius-lg); background:var(--color-brand-800); color:white; }
.hero span,.hero small { color:color-mix(in srgb, white 72%, transparent); font-size:var(--text-xs); }
.hero strong { font-size:var(--text-2xl); }
.metric-grid { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:var(--space-2); }
.metric-grid div,.section { border:1px solid var(--color-border-subtle); border-radius:var(--radius-md); background:var(--color-bg-elevated); }
.metric-grid div { display:grid; gap:3px; padding:var(--space-3); }
.metric-grid span,.procurement-row span,.muted { color:var(--color-text-secondary); font-size:var(--text-xs); }
.metric-grid strong,.procurement-row strong { color:var(--color-text-primary); font-size:var(--text-sm); }
.section { display:grid; gap:0; padding:var(--space-3); }
h2 { margin:0; padding-bottom:var(--space-2); font-size:var(--text-base); font-weight:var(--font-semibold); }
.procurement-row { border-top:1px solid var(--color-border-subtle); }
.procurement-toggle { width:100%; display:flex; align-items:center; justify-content:space-between; gap:var(--space-3); padding:var(--space-3) 0; text-align:left; }
.procurement-toggle div { min-width:0; display:grid; gap:3px; }
.chevron { color:var(--color-text-secondary); transition:transform .18s ease; }
.chevron.open { transform:rotate(180deg); }
.procurement-detail { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:var(--space-2); padding-bottom:var(--space-3); }
.procurement-detail div { display:grid; gap:2px; padding:var(--space-2); border-radius:var(--radius-md); background:var(--color-bg-primary); }
.state { min-height:180px; display:grid; place-items:center; color:var(--color-text-secondary); }
.state-error { color:var(--color-error); }
</style>
