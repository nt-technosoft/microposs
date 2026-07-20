<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, AlertCircle, CalendarClock, CheckCircle2 } from 'lucide-vue-next'
import { fetchSupplierPayables, type SupplierPayable } from '@/api/suppliers'
import { fetchCashAccounts, type CashAccountRecord } from '@/api/finance'
import type { Supplier } from '@/types/models'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import AppEmptyState from '@/components/feedback/AppEmptyState.vue'
import SupplierPaymentForm from '@/modules/suppliers/components/SupplierPaymentForm.vue'
import PageChrome from '@/components/layout/PageChrome.vue'

type FilterMode = 'open' | 'burning' | 'overdue' | 'all'

const router = useRouter()
const { t } = useI18n()

const payables = ref<SupplierPayable[]>([])
const cashAccounts = ref<CashAccountRecord[]>([])
const isLoading = ref(false)
const errorMessage = ref('')
const filterMode = ref<FilterMode>('open')
const paymentOpen = ref(false)
const selectedPayable = ref<SupplierPayable | null>(null)
let loadAbortController: AbortController | null = null

const filterOptions = computed<Array<{ value: FilterMode; label: string }>>(() => [
  { value: 'open', label: t('suppliers.payablesOpenFilter') },
  { value: 'burning', label: t('suppliers.payablesBurningFilter') },
  { value: 'overdue', label: t('suppliers.payablesOverdueFilter') },
  { value: 'all', label: t('common.all') },
])

const remainingByCurrency = computed(() => {
  const totals = new Map<string, number>()
  for (const payable of payables.value) {
    const currency = payable.currency_of_obligation || 'UZS'
    totals.set(currency, (totals.get(currency) ?? 0) + Number(payable.remaining_amount || 0))
  }
  return Array.from(totals.entries()).map(([currency, amount]) => `${amount.toLocaleString('ru-RU')} ${currency}`)
})
const overdueCount = computed(() =>
  payables.value.filter((payable) => payable.deadline_date && new Date(payable.deadline_date) < new Date()).length,
)

function supplierForPayable(payable: SupplierPayable | null): Supplier | null {
  if (!payable) return null
  return {
    id: payable.supplier,
    name: payable.supplier_name,
    phone: '',
    email: '',
    outstanding_balance: payable.remaining_amount,
    is_active: true,
    created_at: '',
    updated_at: '',
  } as Supplier
}

function payableStatusLabel(status: string): string {
  const key = `domain.supplierPayableStatus.${status}`
  const label = t(key)
  return label === key ? status : label
}

function openPayment(payable: SupplierPayable): void {
  selectedPayable.value = payable
  paymentOpen.value = true
}

async function load(): Promise<void> {
  loadAbortController?.abort()
  const controller = new AbortController()
  loadAbortController = controller
  isLoading.value = true
  errorMessage.value = ''
  try {
    const params = filterMode.value === 'burning'
      ? { burning_in: 7 }
      : filterMode.value === 'overdue'
        ? { overdue: true }
        : filterMode.value === 'all'
          ? { status: 'OPEN,PARTIALLY_PAID,FULLY_PAID,CANCELLED' }
          : undefined
    const [payableResponse, accounts] = await Promise.all([
      fetchSupplierPayables(params, controller.signal),
      fetchCashAccounts(controller.signal),
    ])
    if (loadAbortController !== controller) return
    payables.value = payableResponse.results
    cashAccounts.value = accounts
  } catch (error: unknown) {
    const requestError = error as { code?: string; name?: string }
    if (requestError.code === 'ERR_CANCELED' || requestError.name === 'CanceledError') return
    errorMessage.value = error instanceof Error ? error.message : t('suppliers.payablesLoadFailed')
  } finally {
    if (loadAbortController === controller) {
      loadAbortController = null
      isLoading.value = false
    }
  }
}

async function handlePaid(): Promise<void> {
  paymentOpen.value = false
  selectedPayable.value = null
  await load()
}

onMounted(load)
onBeforeUnmount(() => {
  loadAbortController?.abort()
})
</script>

<template>
  <div class="page">
    <PageChrome :title="t('suppliers.payablesPageTitle')" :eyebrow="t('suppliers.title')">
      <template #primary>
        <button class="icon-btn" type="button" :aria-label="t('common.back')" @click="router.back()">
          <ArrowLeft :size="18" :stroke-width="2" />
        </button>
      </template>
    </PageChrome>

    <main class="content">
      <section class="hero">
        <div>
          <span>{{ t('suppliers.totalPayables') }}</span>
          <strong class="tabular-nums">{{ remainingByCurrency.join(' · ') || '0' }}</strong>
        </div>
        <div>
          <span>{{ t('suppliers.overdueShort') }}</span>
          <strong>{{ overdueCount }}</strong>
        </div>
      </section>

      <section class="filters" :aria-label="t('common.filters')">
        <button
          v-for="option in filterOptions"
          :key="option.value"
          type="button"
          class="filter-chip"
          :class="{ active: filterMode === option.value }"
          @click="filterMode = option.value; load()"
        >
          {{ option.label }}
        </button>
      </section>

      <div v-if="errorMessage" class="error-row" role="alert">
        <AlertCircle :size="16" :stroke-width="1.75" />
        <span>{{ errorMessage }}</span>
      </div>

      <div v-if="isLoading" class="skeleton-list" aria-busy="true">
        <div class="skeleton-row" />
        <div class="skeleton-row" />
        <div class="skeleton-row" />
      </div>

      <AppEmptyState
        v-else-if="payables.length === 0"
        :title="t('suppliers.payablesEmptyTitle')"
        :description="t('suppliers.payablesEmptyText')"
      >
        <template #illustration>
          <div class="empty-icon">
            <CheckCircle2 :size="36" :stroke-width="1.6" />
          </div>
        </template>
      </AppEmptyState>

      <section v-else class="payable-list">
        <article v-for="payable in payables" :key="payable.id" class="payable-card">
          <button type="button" class="payable-main" @click="openPayment(payable)">
            <div>
              <strong>{{ payable.supplier_name }}</strong>
              <small>
                {{ payable.procurement ? t('procurements.procurementNumber', { id: payable.procurement }) : t('suppliers.manualPayable') }}
              </small>
            </div>
            <div class="payable-amount">
              <b class="tabular-nums">{{ payable.remaining_amount }} {{ payable.currency_of_obligation }}</b>
              <span>{{ payableStatusLabel(payable.status) }}</span>
            </div>
          </button>
          <div class="payable-meta">
            <span>
              <CalendarClock :size="14" :stroke-width="1.75" />
              {{ payable.deadline_date || t('suppliers.noDeadline') }}
            </span>
            <button type="button" @click="openPayment(payable)">
              {{ t('suppliers.pay') }}
            </button>
          </div>
        </article>
      </section>
    </main>

    <AppBottomSheet
      :open="paymentOpen"
      :title="selectedPayable ? t('suppliers.paymentTitle', { name: selectedPayable.supplier_name }) : t('suppliers.paymentTitleFallback')"
      @close="paymentOpen = false"
    >
      <SupplierPaymentForm
        :supplier="supplierForPayable(selectedPayable)"
        :payable="selectedPayable"
        :accounts="cashAccounts"
        @paid="handlePaid"
      />
    </AppBottomSheet>
  </div>
</template>

<style scoped>
.page {
  min-height: 100%;
  background: var(--color-bg-primary);
}

.icon-btn {
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
}

.content {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  padding-bottom: calc(var(--bottom-nav-height) + 72px);
}

.hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: var(--space-3);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
  padding: var(--space-4);
}

.hero div {
  display: grid;
  gap: 4px;
}

.hero span {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  text-transform: uppercase;
}

.hero strong {
  color: var(--color-text-primary);
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
}

@media (min-width: 768px) {
  .content { max-width:1120px; margin:0 auto; padding:var(--space-6); padding-bottom:var(--space-8); }
  .payable-list { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:var(--space-3); }
}

@media (min-width: 1280px) {
  .page { background: transparent; }
  .content { max-width:none; margin:0; padding-inline:var(--space-8); }
}

.filters {
  display: flex;
  gap: var(--space-2);
  overflow-x: auto;
  padding-bottom: 2px;
}

.filter-chip {
  flex: 0 0 auto;
  min-height: 36px;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-full);
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.filter-chip.active {
  border-color: var(--color-brand-500);
  background: var(--color-brand-50);
  color: var(--color-brand-700);
  font-weight: var(--font-semibold);
}

.payable-list,
.skeleton-list {
  display: grid;
  gap: var(--space-2);
}

.payable-card {
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
  overflow: hidden;
}

.payable-main {
  width: 100%;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3);
  text-align: left;
}

.payable-main > div {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.payable-main strong,
.payable-main b {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.payable-main small,
.payable-amount span,
.payable-meta span {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.payable-amount {
  flex: 0 0 auto;
  justify-items: end;
  text-align: right;
}

.payable-meta {
  min-height: 42px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: 0 var(--space-3);
  border-top: 1px solid var(--color-border-subtle);
}

.payable-meta span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.payable-meta button {
  min-height: 30px;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-brand-300);
  border-radius: var(--radius-md);
  background: var(--color-brand-50);
  color: var(--color-brand-700);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.error-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  border: 1px solid var(--color-error);
  border-radius: var(--radius-md);
  background: var(--color-error-bg);
  color: var(--color-error);
  padding: var(--space-3);
  font-size: var(--text-sm);
}

.skeleton-row {
  height: 72px;
  border-radius: var(--radius-lg);
  background: linear-gradient(90deg, var(--color-bg-secondary), var(--color-bg-elevated), var(--color-bg-secondary));
  background-size: 200% 100%;
  animation: shimmer 1.1s linear infinite;
}

.empty-icon {
  width: 72px;
  height: 72px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  background: var(--color-success-bg);
  color: var(--color-success);
}

@keyframes shimmer {
  from { background-position: 0 0; }
  to { background-position: 200% 0; }
}
</style>
