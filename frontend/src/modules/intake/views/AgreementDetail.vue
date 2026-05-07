<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, BarChart3, Plus, RotateCcw, Send, Wallet } from 'lucide-vue-next'
import {
  addAgreementContribution,
  addAgreementWithdrawal,
  createAgreementAllocations,
  fetchAgreementAllocationPreview,
  fetchInvestmentAgreement,
  type AgreementAllocationPreview,
  type InvestmentAgreementDetail,
} from '@/api/partnerships'
import { formatPrice } from '@/utils/currency'
import { useToast } from '@/composables/useToast'
import { useFxRate } from '@/composables/useFxRate'
import { partnerRoleLabel, procurementStatusLabel } from '@/utils/domainLabels'
import { intlLocale } from '@/i18n/format'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const { t, locale } = useI18n()

const agreement = ref<InvestmentAgreementDetail | null>(null)
const loading = ref(false)
const error = ref('')
const contributionPartnerId = ref<number | null>(null)
const contributionAmount = ref('')
const contributionCurrency = ref('USD')
const savingContribution = ref(false)
const withdrawalPartnerId = ref<number | null>(null)
const withdrawalAmount = ref('')
const withdrawalCurrency = ref('USD')
const savingWithdrawal = ref(false)
const allocationProcurementId = ref<number | null>(null)
const allocationPreview = ref<AgreementAllocationPreview | null>(null)
const allocating = ref(false)
const {
  rate: latestUsdRate,
  error: latestUsdRateError,
  load: loadLatestUsdRate,
} = useFxRate({ baseCurrency: 'USD', quoteCurrency: 'UZS' })

const agreementId = computed(() => Number(route.params.id))
const activeProcurements = computed(() => (agreement.value?.procurements ?? []).filter((item) => item.status === 'OPEN' || item.status === 'PARTIALLY_RECEIVED'))
const balanceLabel = computed(() => {
  const parts = Object.entries(agreement.value?.balances ?? {})
    .filter(([, amount]) => Math.abs(Number.parseFloat(amount || '0')) > 0.000001)
    .map(([currency, amount]) => formatPrice(amount, currency))
  return parts.length ? parts.join(' · ') : '0'
})
const contributedTotal = computed(() => agreement.value?.participant_totals.reduce((sum, row) => sum + Number(row.contributed_amount || 0), 0) ?? 0)
const allocatedTotal = computed(() => agreement.value?.participant_totals.reduce((sum, row) => sum + Number(row.allocated_amount || 0), 0) ?? 0)

function formatDate(value: string): string {
  return new Date(value).toLocaleString(intlLocale(locale.value), { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

function fxRateForCurrency(currency: string): string {
  return currency === 'USD' ? latestUsdRate.value : '1'
}

function ensureFxRate(currency: string): boolean {
  if (currency !== 'USD' || latestUsdRate.value) return true
  toast.error(latestUsdRateError.value || t('procurements.syncUsdRateFirst'))
  return false
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    agreement.value = await fetchInvestmentAgreement(agreementId.value)
    contributionPartnerId.value = agreement.value.partners[0]?.partner ?? null
    withdrawalPartnerId.value = agreement.value.partners[0]?.partner ?? null
    allocationProcurementId.value = activeProcurements.value[0]?.id ?? null
  } catch (err: unknown) {
    error.value = err instanceof Error ? err.message : t('procurements.agreementLoadFailed')
  } finally {
    loading.value = false
  }
}

async function saveContribution(): Promise<void> {
  if (!agreement.value || !contributionPartnerId.value || !contributionAmount.value) return
  if (!ensureFxRate(contributionCurrency.value)) return
  savingContribution.value = true
  try {
    await addAgreementContribution(agreement.value.id, {
      partner_id: contributionPartnerId.value,
      amount: contributionAmount.value,
      currency: contributionCurrency.value,
      fx_rate: fxRateForCurrency(contributionCurrency.value),
    })
    contributionAmount.value = ''
    toast.success(t('procurements.contributionAdded'))
    await load()
  } catch (err: unknown) {
    toast.error(err instanceof Error ? err.message : t('procurements.contributionAddFailed'))
  } finally {
    savingContribution.value = false
  }
}

async function saveWithdrawal(): Promise<void> {
  if (!agreement.value || !withdrawalPartnerId.value || !withdrawalAmount.value) return
  if (!ensureFxRate(withdrawalCurrency.value)) return
  savingWithdrawal.value = true
  try {
    await addAgreementWithdrawal(agreement.value.id, {
      partner_id: withdrawalPartnerId.value,
      amount: withdrawalAmount.value,
      currency: withdrawalCurrency.value,
      fx_rate: fxRateForCurrency(withdrawalCurrency.value),
      reason: t('procurements.withdrawalReason'),
    })
    withdrawalAmount.value = ''
    toast.success(t('procurements.withdrawalAdded'))
    await load()
  } catch (err: unknown) {
    toast.error(err instanceof Error ? err.message : t('procurements.withdrawalAddFailed'))
  } finally {
    savingWithdrawal.value = false
  }
}

async function loadAllocationPreview(): Promise<void> {
  if (!agreement.value || !allocationProcurementId.value) return
  allocationPreview.value = await fetchAgreementAllocationPreview(agreement.value.id, allocationProcurementId.value)
}

async function allocateSuggested(): Promise<void> {
  if (!agreement.value || !allocationPreview.value) return
  const rows = allocationPreview.value.suggestions
    .filter((row) => Number(row.amount) > 0)
    .map((row) => ({
      partner_id: row.partner_id,
      amount: row.amount,
      currency: row.currency,
      fx_rate: fxRateForCurrency(row.currency),
    }))
  if (!rows.length) return
  if (rows.some((row) => !ensureFxRate(row.currency))) return
  allocating.value = true
  try {
    await createAgreementAllocations(agreement.value.id, {
      procurement_id: allocationPreview.value.procurement_id,
      allocations: rows,
    })
    toast.success(t('procurements.capitalAllocated'))
    allocationPreview.value = null
    await load()
  } catch (err: unknown) {
    toast.error(err instanceof Error ? err.message : t('procurements.capitalAllocateFailed'))
  } finally {
    allocating.value = false
  }
}

onMounted(async () => {
  await Promise.allSettled([load(), loadLatestUsdRate()])
  if (latestUsdRateError.value) {
    toast.error(latestUsdRateError.value)
  }
})
</script>

<template>
  <div class="page">
    <header class="topbar">
      <button class="icon-btn" type="button" :aria-label="t('common.back')" @click="router.back()">
        <ArrowLeft :size="18" />
      </button>
      <h1>{{ t('procurements.agreementTitle', { id: route.params.id }) }}</h1>
      <button class="icon-btn" type="button" :aria-label="t('procurements.report')" @click="router.push({ name: 'reports-agreement-profitability', params: { id: route.params.id } })">
        <BarChart3 :size="18" />
      </button>
    </header>

    <main class="content">
      <div v-if="loading" class="state">{{ t('procurements.loading') }}</div>
      <div v-else-if="error" class="state state-error">{{ error }}</div>

      <template v-else-if="agreement">
        <section class="hero">
          <div>
            <span>{{ t('procurements.freeBalance') }}</span>
            <strong>{{ balanceLabel }}</strong>
          </div>
          <div class="hero-grid">
            <div><span>{{ t('procurements.contributed') }}</span><strong>{{ formatPrice(contributedTotal, agreement.currency) }}</strong></div>
            <div><span>{{ t('procurements.allocatedToProcurements') }}</span><strong>{{ formatPrice(allocatedTotal, agreement.currency) }}</strong></div>
            <div><span>{{ t('procurements.procurementsTotal') }}</span><strong>{{ agreement.procurements.length }}</strong></div>
          </div>
        </section>

        <section class="panel">
          <div class="section-head">
            <h2>{{ t('procurements.participants') }}</h2>
          </div>
          <div v-for="row in agreement.participant_totals" :key="row.partner_id" class="partner-row">
            <div>
              <strong>{{ row.partner_name }}</strong>
              <span>{{ partnerRoleLabel(row.role) }} · {{ t('procurements.profitShareShort', { share: (Number(row.planned_profit_share) * 100).toFixed(2) }) }}</span>
            </div>
            <div>
              <strong>{{ formatPrice(row.available_amount, agreement.currency) }}</strong>
              <span>{{ t('procurements.available') }}</span>
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="section-head">
            <h2>{{ t('procurements.contribution') }}</h2>
            <Wallet :size="17" />
          </div>
          <div class="inline-form">
            <select v-model.number="contributionPartnerId">
              <option v-for="partner in agreement.partners" :key="partner.partner" :value="partner.partner">{{ partner.partner_name }}</option>
            </select>
            <input v-model="contributionAmount" inputmode="decimal" :placeholder="t('common.amount')" />
            <select v-model="contributionCurrency">
              <option value="USD">USD</option>
              <option value="UZS">UZS</option>
            </select>
          </div>
          <button class="action" type="button" :disabled="savingContribution" @click="saveContribution">
            <Plus :size="17" /> {{ t('procurements.addContribution') }}
          </button>
        </section>

        <section class="panel">
          <div class="section-head">
            <h2>{{ t('procurements.withdrawalFromAgreement') }}</h2>
            <RotateCcw :size="17" />
          </div>
          <div class="inline-form">
            <select v-model.number="withdrawalPartnerId">
              <option v-for="partner in agreement.partners" :key="partner.partner" :value="partner.partner">{{ partner.partner_name }}</option>
            </select>
            <input v-model="withdrawalAmount" inputmode="decimal" :placeholder="t('common.amount')" />
            <select v-model="withdrawalCurrency">
              <option value="USD">USD</option>
              <option value="UZS">UZS</option>
            </select>
          </div>
          <button class="action secondary" type="button" :disabled="savingWithdrawal" @click="saveWithdrawal">
            <RotateCcw :size="17" /> {{ t('procurements.recordWithdrawal') }}
          </button>
        </section>

        <section class="panel">
          <div class="section-head">
            <h2>{{ t('procurements.linkedProcurements') }}</h2>
            <button type="button" @click="router.push({ name: 'procurement-create', query: { agreement_id: agreement.id } })">{{ t('procurements.new') }}</button>
          </div>
          <button
            v-for="procurement in agreement.procurements"
            :key="procurement.id"
            class="proc-row"
            type="button"
            @click="router.push({ name: 'procurement-detail', params: { id: procurement.id } })"
          >
            <span>#{{ procurement.id }} · {{ procurement.supplier_name || t('procurements.noSupplier') }}</span>
            <strong>{{ procurementStatusLabel(procurement.status) }}</strong>
          </button>
          <p v-if="agreement.procurements.length === 0" class="muted">{{ t('procurements.noLinkedProcurements') }}</p>
        </section>

        <section v-if="activeProcurements.length" class="panel">
          <div class="section-head">
            <h2>{{ t('procurements.allocateCapital') }}</h2>
            <Send :size="17" />
          </div>
          <div class="inline-form two">
            <select v-model.number="allocationProcurementId">
              <option v-for="procurement in activeProcurements" :key="procurement.id" :value="procurement.id">{{ t('procurements.procurementNumber', { id: procurement.id }) }}</option>
            </select>
            <button type="button" @click="loadAllocationPreview">{{ t('procurements.calculate') }}</button>
          </div>
          <div v-if="allocationPreview" class="allocation-box">
            <div v-for="row in allocationPreview.suggestions" :key="`${row.partner_id}-${row.currency}`" class="allocation-row">
              <span>{{ row.partner_name }}</span>
              <strong>{{ formatPrice(row.amount, row.currency) }}</strong>
            </div>
            <button class="action" type="button" :disabled="allocating" @click="allocateSuggested">{{ t('procurements.confirmAllocation') }}</button>
          </div>
        </section>

        <section class="panel">
          <div class="section-head">
            <h2>{{ t('procurements.history') }}</h2>
            <span>{{ agreement.history.length }}</span>
          </div>
          <article v-for="entry in agreement.history.slice(0, 8)" :key="entry.id" class="history-row">
            <div>
              <strong>{{ entry.title }}</strong>
              <span>{{ formatDate(entry.date) }} · {{ entry.partner_name || t('procurements.system') }}</span>
            </div>
            <strong>{{ formatPrice(entry.amount, entry.currency) }}</strong>
          </article>
        </section>
      </template>
    </main>
  </div>
</template>

<style scoped>
.page { min-height: 100%; background: var(--color-bg-primary); }
.topbar { position: sticky; top: 0; z-index: var(--z-sticky); display: grid; grid-template-columns: 40px 1fr 40px; align-items: center; gap: var(--space-2); min-height: var(--header-height); padding: 0 var(--space-4); border-bottom: 1px solid var(--color-border-subtle); background: var(--color-bg-primary); }
h1 { margin: 0; text-align: center; font-size: var(--text-lg); font-weight: var(--font-semibold); }
.icon-btn { width: 40px; height: 40px; display: grid; place-items: center; border: 0; background: transparent; color: var(--color-text-primary); }
.content { display: grid; gap: var(--space-3); padding: var(--space-4); padding-bottom: calc(var(--bottom-nav-height) + var(--space-4)); }
.hero { display: grid; gap: var(--space-3); padding: var(--space-4); border-radius: var(--radius-lg); background: var(--color-brand-800); color: white; }
.hero span { color: color-mix(in srgb, white 72%, transparent); font-size: var(--text-xs); }
.hero strong { display: block; margin-top: 3px; font-size: var(--text-xl); }
.hero-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--space-2); }
.hero-grid strong { font-size: var(--text-sm); }
.panel { display: grid; gap: var(--space-3); padding: var(--space-4); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-lg); background: var(--color-bg-primary); }
.section-head { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); }
h2 { margin: 0; font-size: var(--text-base); font-weight: var(--font-semibold); }
.section-head button { border: 0; background: transparent; color: var(--color-brand-600); font-weight: var(--font-semibold); }
.partner-row, .proc-row, .history-row, .allocation-row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); padding: var(--space-3) 0; border-top: 1px solid var(--color-border-subtle); }
.partner-row:first-of-type, .history-row:first-of-type { border-top: 0; }
.partner-row div, .history-row div { display: grid; gap: 3px; min-width: 0; }
.partner-row strong, .proc-row strong, .history-row strong, .allocation-row strong { color: var(--color-text-primary); font-size: var(--text-sm); }
.partner-row span, .history-row span, .muted { color: var(--color-text-secondary); font-size: var(--text-xs); }
.proc-row { width: 100%; border-left: 0; border-right: 0; border-bottom: 0; background: transparent; text-align: left; }
.proc-row span { color: var(--color-text-primary); }
.inline-form { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, .8fr) 82px; gap: var(--space-2); }
.inline-form.two { grid-template-columns: minmax(0, 1fr) auto; }
input, select { min-height: 42px; min-width: 0; border: 1px solid var(--color-border-default); border-radius: var(--radius-md); padding: 0 var(--space-3); background: var(--color-bg-primary); color: var(--color-text-primary); font: inherit; }
.action { min-height: 42px; display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2); border: 0; border-radius: var(--radius-md); background: var(--color-brand-600); color: white; font-weight: var(--font-semibold); }
.action.secondary { background: var(--color-bg-elevated); color: var(--color-text-primary); border: 1px solid var(--color-border-default); }
.action:disabled { opacity: .55; }
.allocation-box { display: grid; gap: var(--space-2); padding-top: var(--space-2); }
.state { min-height: 180px; display: grid; place-items: center; color: var(--color-text-secondary); }
.state-error { color: var(--color-error); }
@media (max-width: 420px) {
  .inline-form { grid-template-columns: 1fr; }
}
</style>
