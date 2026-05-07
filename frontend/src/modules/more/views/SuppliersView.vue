<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, Plus, Search, Truck, AlertCircle } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { createSupplier, fetchSuppliers, recordSupplierPayment } from '@/api/suppliers'
import type { Supplier } from '@/types/models'
import { formatPrice } from '@/utils/currency'
import { useToast } from '@/composables/useToast'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import AppEmptyState from '@/components/feedback/AppEmptyState.vue'

const router = useRouter()
const toast = useToast()
const { t } = useI18n()

const suppliers = ref<Supplier[]>([])
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
const paymentAmount = ref('')
const isPaying = ref(false)

const totalPayables = computed(() =>
  suppliers.value.reduce((sum, supplier) => sum + parseFloat(supplier.outstanding_balance || '0'), 0),
)

async function loadSuppliers(): Promise<void> {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const response = await fetchSuppliers({
      search: search.value.trim() || undefined,
    })
    suppliers.value = response.results
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : t('suppliers.loadFailed')
  } finally {
    isLoading.value = false
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

function openPayment(supplier: Supplier): void {
  selectedSupplier.value = supplier
  paymentAmount.value = ''
  paymentOpen.value = true
}

async function submitPayment(): Promise<void> {
  if (!selectedSupplier.value) return
  const amount = Number(paymentAmount.value)
  if (!Number.isFinite(amount) || amount <= 0) return

  isPaying.value = true
  try {
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

onMounted(loadSuppliers)
</script>

<template>
  <div class="page">
    <header class="header">
      <button class="icon-btn" type="button" :aria-label="t('common.back')" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>
      <h1 class="title">{{ t('suppliers.title') }}</h1>
      <button class="icon-btn" type="button" :aria-label="t('common.add')" @click="openCreate">
        <Plus :size="18" :stroke-width="2" />
      </button>
    </header>

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
        <strong class="tabular-nums">{{ formatPrice(totalPayables) }}</strong>
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
              @click="openPayment(supplier)"
            >
              {{ t('suppliers.pay') }}
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
      <form class="sheet-form" @submit.prevent="submitPayment">
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
  </div>
</template>

<style scoped>
.page {
  min-height: 100%;
  background: var(--color-bg-primary);
}

.header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: grid;
  grid-template-columns: 40px 1fr 40px;
  align-items: center;
  gap: var(--space-3);
  min-height: var(--header-height);
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-bg-primary);
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
  padding: var(--space-4);
  padding-bottom: calc(var(--bottom-nav-height) + 90px);
  display: grid;
  gap: var(--space-3);
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
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning);
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
