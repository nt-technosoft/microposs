<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, Plus, Search, Truck, AlertCircle } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  createSupplier,
  fetchSuppliers,
  fetchSupplierPayables,
  fetchSupplierProducts,
  recordSupplierPayment,
  type SupplierPayable,
  type SupplierProductHistoryItem,
} from '@/api/suppliers'
import { fetchCashAccounts, type CashAccountRecord } from '@/api/finance'
import type { Supplier } from '@/types/models'
import { formatPrice } from '@/utils/currency'
import { useToast } from '@/composables/useToast'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import AppEmptyState from '@/components/feedback/AppEmptyState.vue'
import SupplierPaymentForm from '@/modules/suppliers/components/SupplierPaymentForm.vue'
import PageChrome from '@/components/layout/PageChrome.vue'

const router = useRouter()
const toast = useToast()
const { t } = useI18n()

const suppliers = ref<Supplier[]>([])
const payables = ref<SupplierPayable[]>([])
const urgentPayables = ref<SupplierPayable[]>([])
const cashAccounts = ref<CashAccountRecord[]>([])
const search = ref('')
const isLoading = ref(false)
const errorMessage = ref('')

const createOpen = ref(false)
const createName = ref('')
const createPhone = ref('')
const createEmail = ref('')
const isCreating = ref(false)

const paymentOpen = ref(false)
const selectedSupplier = ref<Supplier | null>(null)
const selectedPayable = ref<SupplierPayable | null>(null)
const paymentAmount = ref('')
const isPaying = ref(false)
const productsOpen = ref(false)
const productsSupplier = ref<Supplier | null>(null)
const supplierProducts = ref<SupplierProductHistoryItem[]>([])
const isLoadingSupplierProducts = ref(false)

const totalPayables = computed(() =>
  payables.value.reduce((sum, payable) => sum + parseFloat(payable.remaining_amount || '0'), 0),
)

async function loadSuppliers(): Promise<void> {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const response = await fetchSuppliers({
      search: search.value.trim() || undefined,
    })
    suppliers.value = response.results
    const [payableResponse, overdueResponse, burningResponse] = await Promise.all([
      fetchSupplierPayables(),
      fetchSupplierPayables({ overdue: true }),
      fetchSupplierPayables({ burning_in: 7 }),
    ])
    payables.value = payableResponse.results
    const urgentById = new Map<number, SupplierPayable>()
    for (const payable of [...overdueResponse.results, ...burningResponse.results]) {
      urgentById.set(payable.id, payable)
    }
    urgentPayables.value = [...urgentById.values()]
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : t('suppliers.loadFailed')
  } finally {
    isLoading.value = false
  }
}

async function openSupplierProducts(supplier: Supplier): Promise<void> {
  productsSupplier.value = supplier
  supplierProducts.value = []
  productsOpen.value = true
  isLoadingSupplierProducts.value = true
  try {
    supplierProducts.value = await fetchSupplierProducts(supplier.id)
  } catch (error: unknown) {
    toast.error(error instanceof Error ? error.message : t('suppliers.productsLoadFailed'))
  } finally {
    isLoadingSupplierProducts.value = false
  }
}

async function loadCashAccounts(): Promise<void> {
  try {
    cashAccounts.value = await fetchCashAccounts()
  } catch {
    cashAccounts.value = []
  }
}

function openCreate(): void {
  createName.value = ''
  createPhone.value = ''
  createEmail.value = ''
  createOpen.value = true
}

async function submitCreate(): Promise<void> {
  if (!createName.value.trim()) return

  isCreating.value = true
  try {
    await createSupplier({
      name: createName.value.trim(),
      phone: createPhone.value.trim() || undefined,
      email: createEmail.value.trim() || undefined,
    })
    toast.success(t('suppliers.createdShort'))
    createOpen.value = false
    await loadSuppliers()
  } catch (error: unknown) {
    toast.error(error instanceof Error ? error.message : t('suppliers.createFailed'))
  } finally {
    isCreating.value = false
  }
}

function openPayment(supplier: Supplier, payable?: SupplierPayable): void {
  selectedSupplier.value = supplier
  selectedPayable.value = payable ?? payables.value.find((item) => item.supplier === supplier.id) ?? null
  paymentAmount.value = selectedPayable.value?.remaining_amount ?? ''
  paymentOpen.value = true
}

function supplierForPayable(payable: SupplierPayable): Supplier {
  return suppliers.value.find((supplier) => supplier.id === payable.supplier) ?? {
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

async function submitPayment(): Promise<void> {
  if (!selectedSupplier.value) return

  isPaying.value = true
  try {
    const amount = Number(paymentAmount.value)
    if (!Number.isFinite(amount) || amount <= 0) return
    await recordSupplierPayment(selectedSupplier.value.id, {
      amount,
      payment_method: 'cash',
    })
    toast.success(t('suppliers.paymentRecorded'))
    paymentOpen.value = false
    await loadSuppliers()
  } catch (error: unknown) {
    toast.error(error instanceof Error ? error.message : t('suppliers.paymentFailed'))
  } finally {
    isPaying.value = false
  }
}

async function handlePayablePaid(): Promise<void> {
  paymentOpen.value = false
  await loadSuppliers()
}

onMounted(async () => {
  await Promise.all([loadSuppliers(), loadCashAccounts()])
})
</script>

<template>
  <div class="page">
    <PageChrome :title="t('suppliers.title')" :eyebrow="t('settings.management')">
      <template #primary>
        <div class="header-actions">
          <button class="icon-btn" type="button" :aria-label="t('common.back')" @click="router.back()"><ArrowLeft :size="18" :stroke-width="2" /></button>
          <button class="icon-btn" type="button" :aria-label="t('common.add')" @click="openCreate"><Plus :size="18" :stroke-width="2" /></button>
        </div>
      </template>
    </PageChrome>

    <main class="content">
      <section class="filters">
        <div class="search-wrap">
          <Search :size="16" :stroke-width="1.75" class="search-icon" />
          <input
            v-model="search"
            class="search-input"
            type="search"
            :placeholder="t('suppliers.searchPlaceholder')"
            @input="loadSuppliers"
          />
        </div>
      </section>

      <section class="summary">
        <span>{{ t('suppliers.totalPayables') }}</span>
        <div class="summary-side">
          <strong class="tabular-nums">{{ formatPrice(totalPayables) }}</strong>
          <button type="button" @click="router.push({ name: 'supplier-payables' })">
            {{ t('suppliers.openPayablesPage') }}
          </button>
        </div>
      </section>

      <section v-if="urgentPayables.length > 0" class="burning-list">
        <div class="payables-head">
          <span>{{ t('suppliers.burningPayables') }}</span>
          <strong>{{ urgentPayables.length }}</strong>
        </div>
        <button
          v-for="payable in urgentPayables.slice(0, 3)"
          :key="payable.id"
          class="payable-row payable-row--urgent"
          type="button"
          @click="openPayment(supplierForPayable(payable), payable)"
        >
          <span>
            <strong>{{ payable.supplier_name }}</strong>
            <small>{{ payable.deadline_date || t('suppliers.noDeadline') }}</small>
          </span>
          <b class="tabular-nums">{{ payable.remaining_amount }} {{ payable.currency_of_obligation }}</b>
        </button>
      </section>

      <section v-if="payables.length > 0" class="payables-list">
        <div class="payables-head">
          <span>{{ t('suppliers.openPayables') }}</span>
          <strong>{{ payables.length }}</strong>
        </div>
        <button
          v-for="payable in payables.slice(0, 5)"
          :key="payable.id"
          class="payable-row"
          type="button"
          @click="openPayment(supplierForPayable(payable), payable)"
        >
          <span>
            <strong>{{ payable.supplier_name }}</strong>
            <small>{{ payable.deadline_date || t('suppliers.noDeadline') }}</small>
          </span>
          <b class="tabular-nums">{{ payable.remaining_amount }} {{ payable.currency_of_obligation }}</b>
        </button>
      </section>

      <div v-if="errorMessage" class="error-banner" role="alert">
        <AlertCircle :size="16" :stroke-width="1.75" />
        <span>{{ errorMessage }}</span>
      </div>

      <div v-if="isLoading" class="loading-list" aria-busy="true">
        <div class="skeleton-row" />
        <div class="skeleton-row" />
        <div class="skeleton-row" />
      </div>

      <AppEmptyState
        v-else-if="suppliers.length === 0"
        :title="t('suppliers.emptyTitle')"
        :description="t('suppliers.emptyDescription')"
        :action-label="t('suppliers.addSupplier')"
        @action="openCreate"
      >
        <template #illustration>
          <div class="empty-illustration">
            <Truck :size="40" :stroke-width="1.5" />
          </div>
        </template>
      </AppEmptyState>

      <section v-else class="list">
        <article v-for="supplier in suppliers" :key="supplier.id" class="card">
          <div class="card-main">
            <div class="avatar">{{ supplier.name.charAt(0).toUpperCase() }}</div>
            <div class="meta">
              <strong class="name">{{ supplier.name }}</strong>
              <span class="phone">{{ supplier.phone || t('suppliers.phoneMissing') }}</span>
            </div>
          </div>
          <div class="card-side">
            <span class="debt tabular-nums" :class="{ danger: Number(supplier.outstanding_balance) > 0 }">
              {{ formatPrice(supplier.outstanding_balance) }}
            </span>
            <button
              v-if="Number(supplier.outstanding_balance) > 0"
              class="pay-btn"
              type="button"
              @click.stop="openPayment(supplier)"
            >
              {{ t('suppliers.pay') }}
            </button>
            <button
              class="products-btn"
              type="button"
              @click="openSupplierProducts(supplier)"
            >
              {{ t('suppliers.productsShort') }}
            </button>
          </div>
        </article>
      </section>
    </main>

    <button class="fab" type="button" :aria-label="t('suppliers.addSupplier')" @click="openCreate">
      <Plus :size="24" :stroke-width="2.2" />
    </button>

    <AppBottomSheet :open="createOpen" :title="t('suppliers.newSupplier')" @close="createOpen = false">
      <form class="sheet-form" @submit.prevent="submitCreate">
        <BaseInput v-model="createName" :label="`${t('suppliers.name')} *`" :placeholder="t('suppliers.nameExample')" />
        <BaseInput v-model="createPhone" :label="t('suppliers.phone')" placeholder="+998 90 000 00 00" />
        <BaseInput v-model="createEmail" :label="t('suppliers.email')" placeholder="example@mail.com" />
        <BaseButton
          type="submit"
          variant="primary"
          size="lg"
          :full-width="true"
          :loading="isCreating"
          :disabled="isCreating || !createName.trim()"
        >
          {{ t('common.create') }}
        </BaseButton>
      </form>
    </AppBottomSheet>

    <AppBottomSheet
      :open="paymentOpen"
      :title="selectedSupplier ? t('suppliers.paymentTitle', { name: selectedSupplier.name }) : t('suppliers.paymentTitleFallback')"
      @close="paymentOpen = false"
    >
      <SupplierPaymentForm
        v-if="selectedPayable"
        :supplier="selectedSupplier"
        :payable="selectedPayable"
        :accounts="cashAccounts"
        @paid="handlePayablePaid"
      />
      <form v-else class="sheet-form" @submit.prevent="submitPayment">
        <BaseInput
          v-model="paymentAmount"
          :label="`${t('suppliers.paymentAmount')} *`"
          type="number"
          placeholder="0"
        />
        <BaseButton
          type="submit"
          variant="primary"
          size="lg"
          :full-width="true"
          :loading="isPaying"
          :disabled="isPaying || !paymentAmount"
        >
          {{ t('suppliers.recordPayment') }}
        </BaseButton>
      </form>
    </AppBottomSheet>

    <AppBottomSheet
      :open="productsOpen"
      :title="productsSupplier ? t('suppliers.productsTitle', { name: productsSupplier.name }) : t('suppliers.productsTitleFallback')"
      @close="productsOpen = false"
    >
      <div class="supplier-products">
        <div v-if="isLoadingSupplierProducts" class="skeleton-row" />
        <AppEmptyState
          v-else-if="supplierProducts.length === 0"
          :title="t('suppliers.productsEmptyTitle')"
          :description="t('suppliers.productsEmptyText')"
        />
        <template v-else>
          <article
            v-for="item in supplierProducts"
            :key="item.product_variant_id"
            class="supplier-product-row"
          >
            <div>
              <strong>{{ item.product_name }}</strong>
              <small>{{ item.variant_sku || t('common.notSpecified') }}</small>
            </div>
            <div class="supplier-product-side">
              <b>{{ item.last_unit_price }} {{ item.last_currency }}</b>
              <small>{{ t('suppliers.receivedQty', { count: item.total_received_quantity }) }}</small>
            </div>
          </article>
        </template>
      </div>
    </AppBottomSheet>
  </div>
</template>

<style scoped>
.page {
  min-height: 100%;
  background: var(--color-bg-primary);
}

.header-actions { display:flex; align-items:center; gap:var(--space-2); }

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
  padding: var(--space-4);
  padding-bottom: calc(var(--bottom-nav-height) + 90px);
  display: grid;
  gap: var(--space-3);
}

@media (min-width: 768px) {
  .content { max-width:1120px; margin:0 auto; padding:var(--space-6); padding-bottom:var(--space-8); }
  .list { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:var(--space-3); }
}

@media (min-width: 1280px) {
  .page { background: transparent; }
  .content { max-width:none; margin:0; padding-inline:var(--space-8); }
}

.filters {
  display: grid;
  gap: var(--space-2);
}

.search-wrap {
  position: relative;
}

.search-icon {
  position: absolute;
  left: 12px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--color-text-tertiary);
}

.search-input {
  width: 100%;
  min-height: 44px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-elevated);
  padding: 0 var(--space-3) 0 38px;
  color: var(--color-text-primary);
}

.summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-text-primary);
}

.summary-side {
  display: grid;
  justify-items: end;
  gap: 4px;
}

.summary-side button {
  min-height: 28px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-sm);
  border: 1px solid color-mix(in srgb, var(--color-warning) 45%, transparent);
  color: var(--color-warning);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.list {
  display: grid;
  gap: var(--space-2);
}

.card {
  display: flex;
  justify-content: space-between;
  gap: var(--space-3);
  border: 1px solid var(--color-border-subtle);
  background: var(--color-bg-elevated);
  border-radius: var(--radius-md);
  padding: var(--space-3);
}

.payables-list,
.burning-list {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-3);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
}

.burning-list {
  border-color: color-mix(in srgb, var(--color-warning) 45%, var(--color-border-subtle));
  background: color-mix(in srgb, var(--color-warning-bg) 56%, var(--color-bg-elevated));
}

.payables-head,
.payable-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.payables-head {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  text-transform: uppercase;
}

.payable-row {
  min-height: 52px;
  padding: var(--space-2) 0;
  border-top: 1px solid var(--color-border-subtle);
  text-align: left;
}

.payable-row span {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.payable-row strong {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
}

.payable-row small {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.payable-row b {
  flex: 0 0 auto;
  color: var(--color-warning);
  font-size: var(--text-sm);
}

.payable-row--urgent b {
  color: var(--color-error);
}

.card-main {
  display: flex;
  gap: var(--space-3);
  align-items: center;
  min-width: 0;
}

.avatar {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-full);
  background: var(--color-info-bg);
  color: var(--color-info);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: var(--font-bold);
}

.meta {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.name {
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.phone {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.card-side {
  display: grid;
  justify-items: end;
  gap: var(--space-1);
}

.debt {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.debt.danger {
  color: var(--color-warning);
  font-weight: var(--font-semibold);
}

.pay-btn,
.products-btn {
  min-height: 30px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-brand-300);
  color: var(--color-brand-600);
  background: var(--color-brand-50);
  padding: 0 var(--space-2);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.products-btn {
  border-color: var(--color-border-default);
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
}

.supplier-products {
  display: grid;
  gap: var(--space-2);
}

.supplier-product-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  min-height: 58px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-subtle);
  background: var(--color-bg-elevated);
  padding: var(--space-3);
}

.supplier-product-row > div {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.supplier-product-row strong,
.supplier-product-row b {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.supplier-product-row small {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.supplier-product-side {
  justify-items: end;
  text-align: right;
  flex: 0 0 auto;
}

.fab {
  position: fixed;
  right: var(--space-4);
  bottom: calc(var(--bottom-nav-height) + var(--space-4) + env(safe-area-inset-bottom, 0px));
  width: 56px;
  height: 56px;
  border-radius: var(--radius-full);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  box-shadow: var(--shadow-float);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

@media (min-width: 768px) {
  .fab { display:none; }
}

.sheet-form {
  display: grid;
  gap: var(--space-3);
}

.error-banner {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-error);
  background: var(--color-error-bg);
  color: var(--color-error);
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
}

.loading-list {
  display: grid;
  gap: var(--space-2);
}

.skeleton-row {
  height: 64px;
  border-radius: var(--radius-md);
  background: linear-gradient(
    90deg,
    var(--color-bg-secondary) 0%,
    var(--color-bg-elevated) 50%,
    var(--color-bg-secondary) 100%
  );
  background-size: 200% 100%;
  animation: shimmer 1.1s linear infinite;
}

.empty-illustration {
  width: 72px;
  height: 72px;
  border-radius: var(--radius-full);
  background: var(--color-info-bg);
  color: var(--color-info);
  display: flex;
  align-items: center;
  justify-content: center;
}

@keyframes shimmer {
  from { background-position: 0 0; }
  to { background-position: 200% 0; }
}
</style>
