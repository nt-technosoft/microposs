<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, Plus, Search, Wallet, AlertCircle } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { createCustomer, fetchCustomers, recordPayment } from '@/api/customers'
import type { Customer } from '@/types/models'
import { formatPrice } from '@/utils/currency'
import { useToast } from '@/composables/useToast'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import AppEmptyState from '@/components/feedback/AppEmptyState.vue'
import PageChrome from '@/components/layout/PageChrome.vue'

const router = useRouter()
const toast = useToast()
const { t } = useI18n()

const customers = ref<Customer[]>([])
const search = ref('')
const debtOnly = ref(false)
const isLoading = ref(false)
const errorMessage = ref('')

const createOpen = ref(false)
const createName = ref('')
const createPhone = ref('')
const isCreating = ref(false)

const paymentOpen = ref(false)
const selectedCustomer = ref<Customer | null>(null)
const paymentAmount = ref('')
const isPaying = ref(false)

const totalDebt = computed(() =>
  customers.value.reduce((sum, customer) => sum + parseFloat(customer.outstanding_balance || '0'), 0),
)

async function loadCustomers(): Promise<void> {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const response = await fetchCustomers({
      search: search.value.trim() || undefined,
      has_debt: debtOnly.value || undefined,
    })
    customers.value = response.results
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : t('customers.loadFailed')
  } finally {
    isLoading.value = false
  }
}

function openCreate(): void {
  createName.value = ''
  createPhone.value = ''
  createOpen.value = true
}

async function submitCreate(): Promise<void> {
  if (!createName.value.trim()) return

  isCreating.value = true
  try {
    await createCustomer({
      name: createName.value.trim(),
      phone: createPhone.value.trim() || undefined,
    })
    toast.success(t('customers.createdShort'))
    createOpen.value = false
    await loadCustomers()
  } catch (error: unknown) {
    toast.error(error instanceof Error ? error.message : t('customers.createFailed'))
  } finally {
    isCreating.value = false
  }
}

function openPayment(customer: Customer): void {
  selectedCustomer.value = customer
  paymentAmount.value = ''
  paymentOpen.value = true
}

async function submitPayment(): Promise<void> {
  if (!selectedCustomer.value) return
  const amount = Number(paymentAmount.value)
  if (!Number.isFinite(amount) || amount <= 0) return

  isPaying.value = true
  try {
    await recordPayment(selectedCustomer.value.id, {
      amount,
      payment_method: 'cash',
    })
    toast.success(t('customers.paymentRecorded'))
    paymentOpen.value = false
    await loadCustomers()
  } catch (error: unknown) {
    toast.error(error instanceof Error ? error.message : t('customers.paymentFailed'))
  } finally {
    isPaying.value = false
  }
}

onMounted(loadCustomers)
</script>

<template>
  <div class="page">
    <PageChrome :title="t('customers.title')" :eyebrow="t('settings.management')">
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
            :placeholder="t('customers.searchPlaceholder')"
            @input="loadCustomers"
          />
        </div>
        <label class="checkbox-row">
          <input v-model="debtOnly" type="checkbox" @change="loadCustomers" />
          <span>{{ t('customers.debtOnly') }}</span>
        </label>
      </section>

      <section class="summary">
        <span>{{ t('customers.totalDebt') }}</span>
        <strong class="tabular-nums">{{ formatPrice(totalDebt) }}</strong>
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
        v-else-if="customers.length === 0"
        :title="t('customers.emptyTitle')"
        :description="t('customers.emptyDescription')"
        :action-label="t('customers.addCustomer')"
        @action="openCreate"
      />

      <section v-else class="list">
        <article v-for="customer in customers" :key="customer.id" class="card">
          <div class="card-main">
            <div class="avatar">{{ customer.name.charAt(0).toUpperCase() }}</div>
            <div class="meta">
              <strong class="name">{{ customer.name }}</strong>
              <span class="phone">{{ customer.phone || t('customers.phoneMissing') }}</span>
            </div>
          </div>
          <div class="card-side">
            <span class="debt tabular-nums" :class="{ danger: Number(customer.outstanding_balance) > 0 }">
              {{ formatPrice(customer.outstanding_balance) }}
            </span>
            <button
              v-if="Number(customer.outstanding_balance) > 0"
              class="pay-btn"
              type="button"
              @click="openPayment(customer)"
            >
              {{ t('customers.repay') }}
            </button>
          </div>
        </article>
      </section>
    </main>

    <button class="fab" type="button" :aria-label="t('customers.addCustomer')" @click="openCreate">
      <Plus :size="24" :stroke-width="2.2" />
    </button>

    <AppBottomSheet :open="createOpen" :title="t('customers.newCustomer')" @close="createOpen = false">
      <form class="sheet-form" @submit.prevent="submitCreate">
        <BaseInput v-model="createName" :label="`${t('customers.name')} *`" :placeholder="t('customers.nameExample')" />
        <BaseInput v-model="createPhone" :label="t('customers.phone')" placeholder="+998 90 000 00 00" />
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
      :title="selectedCustomer ? t('customers.paymentTitle', { name: selectedCustomer.name }) : t('customers.paymentTitleFallback')"
      @close="paymentOpen = false"
    >
      <form class="sheet-form" @submit.prevent="submitPayment">
        <BaseInput
          v-model="paymentAmount"
          :label="`${t('customers.paymentAmount')} *`"
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
          {{ t('customers.recordPayment') }}
        </BaseButton>
      </form>
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

.checkbox-row {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--color-brand-50);
  border: 1px solid var(--color-brand-100);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-text-primary);
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
  background: var(--color-brand-50);
  color: var(--color-brand-600);
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
  color: var(--color-error);
  font-weight: var(--font-semibold);
}

.pay-btn {
  min-height: 30px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-brand-300);
  color: var(--color-brand-600);
  background: var(--color-brand-50);
  padding: 0 var(--space-2);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
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

@keyframes shimmer {
  from { background-position: 0 0; }
  to { background-position: 200% 0; }
}
</style>
