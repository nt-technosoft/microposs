<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ArrowDownToLine, ArrowUpFromLine, ArrowRightLeft, RefreshCcw } from 'lucide-vue-next'
import AppSkeletonCard from '@/components/feedback/AppSkeletonCard.vue'
import AppEmptyState from '@/components/feedback/AppEmptyState.vue'
import { fetchCashAccounts, type CashAccountRecord } from '@/api/finance'
import { formatPrice } from '@/utils/currency'
import CashDepositSheet from './CashDepositSheet.vue'
import CashWithdrawSheet from './CashWithdrawSheet.vue'
import CashTransferSheet from './CashTransferSheet.vue'

const accounts = ref<CashAccountRecord[]>([])
const isLoading = ref(true)
const error = ref<string | null>(null)

let abortController: AbortController | null = null

async function load() {
  abortController?.abort()
  abortController = new AbortController()
  isLoading.value = true
  error.value = null
  try {
    accounts.value = await fetchCashAccounts(abortController.signal)
  } catch (e: unknown) {
    if ((e as { name?: string })?.name === 'CanceledError') return
    error.value = 'Не удалось загрузить кассы'
  } finally {
    isLoading.value = false
  }
}

onMounted(load)
onBeforeUnmount(() => abortController?.abort())

const depositOpen = ref(false)
const withdrawOpen = ref(false)
const transferOpen = ref(false)
const activeAccount = ref<CashAccountRecord | null>(null)
const transferFromAccountId = ref<number | null>(null)

function openDeposit(account: CashAccountRecord) {
  activeAccount.value = account
  depositOpen.value = true
}

function openWithdraw(account: CashAccountRecord) {
  activeAccount.value = account
  withdrawOpen.value = true
}

function openTransfer(account: CashAccountRecord) {
  transferFromAccountId.value = account.id
  transferOpen.value = true
}

async function handleSuccess() {
  depositOpen.value = false
  withdrawOpen.value = false
  transferOpen.value = false
  await load()
}

function kindLabel(kind: string): string {
  const map: Record<string, string> = {
    cash: 'Наличные',
    card_terminal: 'Карт-терминал',
    bank: 'Банк',
  }
  return map[kind] ?? kind
}
</script>

<template>
  <div class="cash-view">
    <header class="page-header">
      <h1 class="page-title">Кассы</h1>
      <button class="icon-btn" :disabled="isLoading" aria-label="Обновить" @click="load">
        <RefreshCcw :size="20" :stroke-width="1.75" :class="{ spinning: isLoading }" />
      </button>
    </header>

    <div v-if="isLoading" class="card-list">
      <AppSkeletonCard v-for="n in 3" :key="n" />
    </div>

    <p v-else-if="error" class="error-text">{{ error }}</p>

    <AppEmptyState
      v-else-if="accounts.length === 0"
      title="Нет касс"
      description="Создайте кассу в настройках"
    />

    <div v-else class="card-list">
      <div v-for="account in accounts" :key="account.id" class="account-card">
        <div class="card-main">
          <div class="card-info">
            <span class="account-name">{{ account.name }}</span>
            <span class="account-kind">{{ kindLabel(account.kind) }}</span>
          </div>
          <div class="account-balance" :class="{ 'balance-zero': parseFloat(account.balance) === 0 }">
            {{ formatPrice(account.balance, account.currency) }}
          </div>
        </div>

        <div class="card-actions">
          <button class="action-btn deposit" @click="openDeposit(account)">
            <ArrowDownToLine :size="16" :stroke-width="1.75" />
            Пополнить
          </button>
          <button class="action-btn withdraw" @click="openWithdraw(account)">
            <ArrowUpFromLine :size="16" :stroke-width="1.75" />
            Снять
          </button>
          <button class="action-btn transfer" @click="openTransfer(account)">
            <ArrowRightLeft :size="16" :stroke-width="1.75" />
            Перевести
          </button>
        </div>
      </div>
    </div>

    <CashDepositSheet
      :open="depositOpen"
      :account="activeAccount"
      @close="depositOpen = false"
      @deposited="handleSuccess"
    />

    <CashWithdrawSheet
      :open="withdrawOpen"
      :account="activeAccount"
      @close="withdrawOpen = false"
      @withdrawn="handleSuccess"
    />

    <CashTransferSheet
      :open="transferOpen"
      :accounts="accounts"
      :from-account-id="transferFromAccountId"
      @close="transferOpen = false"
      @transferred="handleSuccess"
    />
  </div>
</template>

<style scoped>
.cash-view {
  padding: var(--space-4);
  max-width: 600px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-5);
}

.page-title {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  transition: background var(--duration-fast) var(--ease-out);
}

.icon-btn:hover {
  background: var(--color-bg-subtle);
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.card-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.account-card {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.card-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4);
}

.card-info {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.account-name {
  font-weight: var(--font-semibold);
  font-size: var(--text-base);
}

.account-kind {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.account-balance {
  font-size: var(--text-lg);
  font-weight: var(--font-bold);
  color: var(--color-brand-600);
}

.balance-zero {
  color: var(--color-text-tertiary);
}

.card-actions {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border-top: 1px solid var(--color-border-subtle);
}

.action-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-3) var(--space-2);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
  transition: background var(--duration-fast) var(--ease-out), color var(--duration-fast) var(--ease-out);
  border-right: 1px solid var(--color-border-subtle);
}

.action-btn:last-child {
  border-right: none;
}

.action-btn:active {
  transform: scale(0.96);
}

.action-btn.deposit:hover {
  color: var(--color-success-600);
  background: var(--color-success-50, rgba(16, 185, 129, 0.06));
}

.action-btn.withdraw:hover {
  color: var(--color-danger-500);
  background: var(--color-danger-50, rgba(239, 68, 68, 0.06));
}

.action-btn.transfer:hover {
  color: var(--color-brand-500);
  background: var(--color-brand-50, rgba(99, 102, 241, 0.06));
}

.error-text {
  color: var(--color-danger-500);
  text-align: center;
  padding: var(--space-6);
}
</style>
