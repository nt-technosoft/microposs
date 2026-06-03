<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowDownToLine, ArrowUpFromLine, ArrowRightLeft, RefreshCcw, ChevronRight } from 'lucide-vue-next'
import AppSkeletonCard from '@/components/feedback/AppSkeletonCard.vue'
import AppEmptyState from '@/components/feedback/AppEmptyState.vue'
import {
  fetchCashAccounts,
  fetchLatestFxRate,
  refreshOfficialFxRate,
  type CashAccountRecord,
  type ExchangeRateItem,
} from '@/api/finance'
import { formatPrice } from '@/utils/currency'
import CashDepositSheet from './CashDepositSheet.vue'
import CashWithdrawSheet from './CashWithdrawSheet.vue'
import CashTransferSheet from './CashTransferSheet.vue'

const router = useRouter()

const accounts = ref<CashAccountRecord[]>([])
const isLoading = ref(true)
const error = ref<string | null>(null)
const tab = ref<'operating' | 'capital'>('operating')
const fxRate = ref<ExchangeRateItem | null>(null)
const isFxLoading = ref(false)
const fxError = ref<string | null>(null)

let abortController: AbortController | null = null

const CAPITAL_KIND = 'agreement_capital'
const operatingAccounts = computed(() => accounts.value.filter((a) => a.kind !== CAPITAL_KIND))
const capitalAccounts = computed(() => accounts.value.filter((a) => a.kind === CAPITAL_KIND))

async function load() {
  abortController?.abort()
  abortController = new AbortController()
  isLoading.value = true
  error.value = null
  try {
    const [accountRows] = await Promise.all([
      fetchCashAccounts(abortController.signal),
      loadFxRate(),
    ])
    accounts.value = accountRows
  } catch (e: unknown) {
    if ((e as { name?: string })?.name === 'CanceledError') return
    error.value = 'Не удалось загрузить кассы'
  } finally {
    isLoading.value = false
  }
}

async function loadFxRate() {
  isFxLoading.value = true
  fxError.value = null
  try {
    fxRate.value = await fetchLatestFxRate({ base_currency: 'USD', quote_currency: 'UZS' })
  } catch {
    fxError.value = 'Курс USD/UZS не найден'
  } finally {
    isFxLoading.value = false
  }
}

async function refreshFxRate() {
  isFxLoading.value = true
  fxError.value = null
  try {
    const result = await refreshOfficialFxRate({
      base_currency: 'USD',
      quote_currency: 'UZS',
      overwrite_manual: false,
    })
    fxRate.value = result.rate
  } catch {
    fxError.value = 'Не удалось обновить курс ЦБ'
  } finally {
    isFxLoading.value = false
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

function openAgreement(account: CashAccountRecord) {
  if (!account.agreement_id) return
  router.push({ name: 'agreement-detail', params: { id: String(account.agreement_id) } })
}

function kindLabel(kind: string): string {
  const map: Record<string, string> = {
    cash: 'Наличные',
    card_terminal: 'Карт-терминал',
    bank: 'Банк',
    agreement_capital: 'Капитал инвест-договора',
  }
  return map[kind] ?? kind
}

function sourceLabel(source?: string): string {
  if (source === 'CBU') return 'ЦБ Узбекистана'
  if (source === 'MANUAL') return 'ручной курс'
  return source || 'источник не указан'
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

    <section class="fx-strip" aria-label="Курс валют">
      <div>
        <span class="fx-label">Курс для отображения</span>
        <strong v-if="fxRate" class="fx-value">1 USD = {{ formatPrice(fxRate.rate, 'UZS') }}</strong>
        <strong v-else class="fx-value muted">USD/UZS</strong>
        <span class="fx-meta">
          <template v-if="fxRate">{{ sourceLabel(fxRate.source) }} · {{ fxRate.rate_date }}</template>
          <template v-else>{{ fxError || 'Загрузка курса' }}</template>
        </span>
      </div>
      <button class="fx-refresh" :disabled="isFxLoading" type="button" @click="refreshFxRate">
        <RefreshCcw :size="16" :stroke-width="1.75" :class="{ spinning: isFxLoading }" />
        Обновить
      </button>
    </section>

    <!-- Tabs: operating cash vs agreement capital pools -->
    <div class="tabs">
      <button class="tab" :class="{ active: tab === 'operating' }" @click="tab = 'operating'">
        Операционные
        <span v-if="operatingAccounts.length" class="tab-count">{{ operatingAccounts.length }}</span>
      </button>
      <button class="tab" :class="{ active: tab === 'capital' }" @click="tab = 'capital'">
        Капитал договоров
        <span v-if="capitalAccounts.length" class="tab-count">{{ capitalAccounts.length }}</span>
      </button>
    </div>

    <div v-if="isLoading" class="card-list">
      <AppSkeletonCard v-for="n in 3" :key="n" />
    </div>

    <p v-else-if="error" class="error-text">{{ error }}</p>

    <!-- Operating accounts: full actions -->
    <template v-else-if="tab === 'operating'">
      <AppEmptyState v-if="operatingAccounts.length === 0" title="Нет касс" description="Создайте кассу в настройках" />
      <div v-else class="card-list">
        <div v-for="account in operatingAccounts" :key="account.id" class="account-card">
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
    </template>

    <!-- Capital pools: read-only, link to the agreement (no operations here) -->
    <template v-else>
      <AppEmptyState v-if="capitalAccounts.length === 0" title="Нет пулов капитала" description="Появляются при создании инвест-договоров" />
      <template v-else>
        <p class="tab-hint">Капитал договоров пополняется и расходуется внутри самого инвест-договора. Здесь — только просмотр.</p>
        <div class="card-list">
          <button
            v-for="account in capitalAccounts"
            :key="account.id"
            class="account-card capital-card"
            :class="{ 'is-link': account.agreement_id }"
            type="button"
            :disabled="!account.agreement_id"
            @click="openAgreement(account)"
          >
            <div class="card-main">
              <div class="card-info">
                <span class="account-name">{{ account.name }}</span>
                <span class="account-kind">{{ kindLabel(account.kind) }}</span>
              </div>
              <div class="capital-right">
                <span class="account-balance" :class="{ 'balance-zero': parseFloat(account.balance) === 0 }">
                  {{ formatPrice(account.balance, account.currency) }}
                </span>
                <ChevronRight v-if="account.agreement_id" :size="18" :stroke-width="2" class="chevron" />
              </div>
            </div>
            <div v-if="account.agreement_id" class="capital-link-row">Открыть договор</div>
          </button>
        </div>
      </template>
    </template>

    <CashDepositSheet :open="depositOpen" :account="activeAccount" @close="depositOpen = false" @deposited="handleSuccess" />
    <CashWithdrawSheet :open="withdrawOpen" :account="activeAccount" @close="withdrawOpen = false" @withdrawn="handleSuccess" />
    <CashTransferSheet :open="transferOpen" :accounts="operatingAccounts" :from-account-id="transferFromAccountId" @close="transferOpen = false" @transferred="handleSuccess" />
  </div>
</template>

<style scoped>
.cash-view { padding: var(--space-4); max-width: 600px; margin: 0 auto; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--space-4); }
.page-title { font-size: var(--text-xl); font-weight: var(--font-bold); }
.icon-btn { display: flex; align-items: center; justify-content: center; width: 36px; height: 36px; border-radius: var(--radius-md); color: var(--color-text-secondary); transition: background var(--duration-fast) var(--ease-out); }
.icon-btn:hover { background: var(--color-bg-subtle); }
.spinning { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.fx-strip { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); padding: var(--space-3) var(--space-4); margin-bottom: var(--space-4); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-lg); background: var(--color-bg-elevated); }
.fx-label { display: block; margin-bottom: 2px; font-size: var(--text-xs); color: var(--color-text-tertiary); }
.fx-value { display: block; font-size: var(--text-base); font-weight: var(--font-bold); color: var(--color-text-primary); }
.fx-value.muted { color: var(--color-text-secondary); }
.fx-meta { display: block; margin-top: 2px; font-size: var(--text-xs); color: var(--color-text-tertiary); }
.fx-refresh { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-1); min-height: 36px; padding: 0 var(--space-3); border-radius: var(--radius-md); border: 1px solid var(--color-border-subtle); font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--color-brand-700, #047857); background: var(--color-bg-elevated); white-space: nowrap; }
.fx-refresh:disabled { opacity: .65; }

.tabs { display: flex; gap: var(--space-1); padding: var(--space-1); background: var(--color-bg-subtle, #f1f1f1); border-radius: var(--radius-lg); margin-bottom: var(--space-4); }
.tab { flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2); padding: var(--space-2) var(--space-3); border-radius: var(--radius-md); font-size: var(--text-sm); font-weight: var(--font-medium); color: var(--color-text-secondary); transition: background var(--duration-fast) var(--ease-out), color var(--duration-fast) var(--ease-out); }
.tab.active { background: var(--color-bg-elevated); color: var(--color-text-primary); font-weight: var(--font-semibold); box-shadow: var(--shadow-sm); }
.tab-count { min-width: 18px; padding: 0 5px; border-radius: var(--radius-full); background: var(--color-bg-subtle); font-size: var(--text-xs); font-weight: var(--font-semibold); }
.tab.active .tab-count { background: var(--color-brand-100, rgba(16,185,129,.14)); color: var(--color-brand-700, #047857); }

.tab-hint { font-size: var(--text-xs); color: var(--color-text-tertiary); margin-bottom: var(--space-3); line-height: 1.45; }

.card-list { display: flex; flex-direction: column; gap: var(--space-3); }
.account-card { background: var(--color-bg-elevated); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-lg); overflow: hidden; }
.card-main { display: flex; align-items: center; justify-content: space-between; padding: var(--space-4); }
.card-info { display: flex; flex-direction: column; gap: var(--space-1); text-align: left; }
.account-name { font-weight: var(--font-semibold); font-size: var(--text-base); }
.account-kind { font-size: var(--text-xs); color: var(--color-text-tertiary); }
.account-balance { font-size: var(--text-lg); font-weight: var(--font-bold); color: var(--color-brand-600); }
.balance-zero { color: var(--color-text-tertiary); }

.card-actions { display: grid; grid-template-columns: repeat(3, 1fr); border-top: 1px solid var(--color-border-subtle); }
.action-btn { display: flex; flex-direction: column; align-items: center; gap: var(--space-1); padding: var(--space-3) var(--space-2); font-size: var(--text-xs); font-weight: var(--font-medium); color: var(--color-text-secondary); transition: background var(--duration-fast) var(--ease-out), color var(--duration-fast) var(--ease-out); border-right: 1px solid var(--color-border-subtle); }
.action-btn:last-child { border-right: none; }
.action-btn:active { transform: scale(0.96); }
.action-btn.deposit:hover { color: var(--color-success-600); background: var(--color-success-50, rgba(16, 185, 129, 0.06)); }
.action-btn.withdraw:hover { color: var(--color-danger-500); background: var(--color-danger-50, rgba(239, 68, 68, 0.06)); }
.action-btn.transfer:hover { color: var(--color-brand-500); background: var(--color-brand-50, rgba(16, 185, 129, 0.06)); }

/* Capital pool cards — read-only, optionally a link to the agreement */
.capital-card { display: block; width: 100%; }
.capital-card.is-link { cursor: pointer; }
.capital-card.is-link:hover { border-color: var(--color-brand-300, #6ee7b7); }
.capital-card:disabled { cursor: default; }
.capital-right { display: flex; align-items: center; gap: var(--space-2); }
.chevron { color: var(--color-text-tertiary); }
.capital-link-row { border-top: 1px solid var(--color-border-subtle); padding: var(--space-3) var(--space-4); font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-brand-600); text-align: left; }

.error-text { color: var(--color-danger-500); text-align: center; padding: var(--space-6); }
</style>
