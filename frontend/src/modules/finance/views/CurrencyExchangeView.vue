<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, RefreshCcw, ArrowRightLeft, AlertCircle } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'
import { useToast } from '@/composables/useToast'
import {
  createCurrencyExchange,
  createOwnerContribution,
  fetchCashAccounts,
  fetchLatestFxRate,
  type CashAccountRecord,
} from '@/api/finance'
import { formatPrice } from '@/utils/currency'

const router = useRouter()
const toast = useToast()

const accounts = ref<CashAccountRecord[]>([])
const isLoading = ref(true)
const isSaving = ref(false)
const formError = ref<string | null>(null)
const latestUsdUzsRate = ref('12100')
const topUpSheetOpen = ref(false)
const topUpAccountId = ref<number | null>(null)
const topUpAmount = ref('')
const topUpNotes = ref('')
const topUpError = ref<string | null>(null)
const isSavingTopUp = ref(false)

const fromAccountId = ref<number | null>(null)
const toAccountId = ref<number | null>(null)
const fromAmount = ref('')
const rate = ref('')
const notes = ref('')

const activeAccounts = computed(() => accounts.value.filter((account) => account.is_active !== false))
const fromAccount = computed(() => activeAccounts.value.find((account) => account.id === fromAccountId.value) ?? null)
const toAccount = computed(() => activeAccounts.value.find((account) => account.id === toAccountId.value) ?? null)

const fromOptions = computed(() => activeAccounts.value.map((account) => ({
  value: account.id,
  label: `${account.name} · ${formatPrice(account.balance, account.currency)}`,
})))

const toOptions = computed(() => {
  const fromCurrency = fromAccount.value?.currency ?? null
  return activeAccounts.value
    .filter((account) => account.id !== fromAccountId.value && account.currency !== fromCurrency)
    .map((account) => ({
      value: account.id,
      label: `${account.name} · ${formatPrice(account.balance, account.currency)}`,
    }))
})

const hasExchangePair = computed(() => {
  const currencies = new Set(activeAccounts.value.map((account) => account.currency))
  return currencies.size >= 2
})
const topUpAccount = computed(() => activeAccounts.value.find((account) => account.id === topUpAccountId.value) ?? null)

const fromAmountNumber = computed(() => {
  const value = Number.parseFloat(fromAmount.value)
  return Number.isFinite(value) && value > 0 ? value : 0
})

const rateNumber = computed(() => {
  const value = Number.parseFloat(rate.value)
  return Number.isFinite(value) && value > 0 ? value : 0
})

function trimTrailingZeros(value: string | number): string {
  const raw = typeof value === 'number' ? String(value) : value
  if (!raw) return '0'
  if (!raw.includes('.')) return raw
  return raw.replace(/(\.\d*?[1-9])0+$/u, '$1').replace(/\.0+$/u, '')
}

function pairRateFromStandardRate(fromCurrency: string, toCurrency: string, standardRateRaw: string): string {
  const standardRate = Number.parseFloat(standardRateRaw)
  if (!Number.isFinite(standardRate) || standardRate <= 0) return '0'
  if (fromCurrency === toCurrency) return '1'
  if (fromCurrency === 'USD' && toCurrency === 'UZS') return standardRate.toFixed(6)
  if (fromCurrency === 'UZS' && toCurrency === 'USD') return (1 / standardRate).toFixed(6)
  return '0'
}

const pairRateNumber = computed(() => {
  if (!fromAccount.value || !toAccount.value) return 0
  const value = Number.parseFloat(pairRateFromStandardRate(fromAccount.value.currency, toAccount.value.currency, rate.value))
  return Number.isFinite(value) && value > 0 ? value : 0
})

const previewToAmount = computed(() => fromAmountNumber.value * pairRateNumber.value)

const exchangeDirectionHint = computed(() => {
  if (!fromAccount.value || !toAccount.value) return '—'
  return `${fromAccount.value.currency} -> ${toAccount.value.currency}`
})

function suggestedRate(): string {
  return latestUsdUzsRate.value
}

function syncRate(): void {
  const suggested = suggestedRate()
  if (suggested) {
    rate.value = suggested
  }
}

function openTopUpSheet(accountId?: number | null): void {
  topUpError.value = null
  topUpAmount.value = ''
  topUpNotes.value = ''
  topUpAccountId.value = accountId ?? fromAccountId.value ?? activeAccounts.value[0]?.id ?? null
  topUpSheetOpen.value = true
}

function closeTopUpSheet(): void {
  topUpSheetOpen.value = false
}

function normalizeAccountPair(): void {
  if (!fromOptions.value.length) {
    fromAccountId.value = null
    toAccountId.value = null
    return
  }

  if (!fromOptions.value.some((option) => option.value === fromAccountId.value)) {
    fromAccountId.value = Number(fromOptions.value[0].value)
  }

  if (!toOptions.value.some((option) => option.value === toAccountId.value)) {
    toAccountId.value = toOptions.value.length ? Number(toOptions.value[0].value) : null
  }

  syncRate()
}

watch([fromAccountId, toAccountId], () => {
  if (toAccountId.value && !toOptions.value.some((option) => option.value === toAccountId.value)) {
    toAccountId.value = toOptions.value.length ? Number(toOptions.value[0].value) : null
    return
  }
  syncRate()
})

watch(latestUsdUzsRate, () => {
  syncRate()
})

async function loadLatestRate(): Promise<void> {
  try {
    const latest = await fetchLatestFxRate({
      base_currency: 'USD',
      quote_currency: 'UZS',
    })
    latestUsdUzsRate.value = String(latest.rate)
  } catch {
    latestUsdUzsRate.value = '12100'
  }
}

async function loadAccounts(): Promise<void> {
  accounts.value = await fetchCashAccounts()
  normalizeAccountPair()
}

async function submit(): Promise<void> {
  formError.value = null
  if (!fromAccount.value || !toAccount.value) {
    formError.value = 'Выберите счета для обмена'
    return
  }
  if (fromAccount.value.currency === toAccount.value.currency) {
    formError.value = 'Счета должны быть в разных валютах'
    return
  }
  if (fromAmountNumber.value <= 0) {
    formError.value = 'Укажите сумму списания'
    return
  }
  if (rateNumber.value <= 0 || pairRateNumber.value <= 0) {
    formError.value = 'Укажите корректный курс'
    return
  }

  isSaving.value = true
  try {
    await createCurrencyExchange({
      from_account_id: fromAccount.value.id,
      to_account_id: toAccount.value.id,
      from_amount: fromAmountNumber.value.toFixed(2),
      rate: pairRateNumber.value.toFixed(6),
      notes: notes.value.trim(),
    })
    toast.success('Обмен валют проведён')
    fromAmount.value = ''
    notes.value = ''
    await loadAccounts()
  } catch (error: unknown) {
    formError.value = error instanceof Error ? error.message : 'Не удалось провести обмен'
    toast.error(formError.value)
  } finally {
    isSaving.value = false
  }
}

async function submitTopUp(): Promise<void> {
  topUpError.value = null
  const amount = Number.parseFloat(topUpAmount.value)
  if (!topUpAccount.value) {
    topUpError.value = 'Выберите счёт пополнения'
    return
  }
  if (!Number.isFinite(amount) || amount <= 0) {
    topUpError.value = 'Укажите сумму пополнения'
    return
  }

  isSavingTopUp.value = true
  try {
    await createOwnerContribution({
      amount: amount.toFixed(2),
      currency: topUpAccount.value.currency,
      to_account_id: topUpAccount.value.id,
      notes: topUpNotes.value.trim(),
    })
    toast.success('Счёт пополнен')
    closeTopUpSheet()
    await loadAccounts()
  } catch (error: unknown) {
    topUpError.value = error instanceof Error ? error.message : 'Не удалось пополнить счёт'
    toast.error(topUpError.value)
  } finally {
    isSavingTopUp.value = false
  }
}

onMounted(async () => {
  isLoading.value = true
  try {
    await Promise.all([loadLatestRate(), loadAccounts()])
  } catch {
    formError.value = 'Не удалось загрузить счета'
  } finally {
    isLoading.value = false
  }
})
</script>

<template>
  <div class="exchange-page">
    <header class="page-header">
      <button class="back-btn" type="button" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>
      <h1 class="page-title">Обмен валют</h1>
      <div class="header-spacer" />
    </header>

    <main class="content">
      <section class="card intro-card">
        <span class="kicker">Правило</span>
        <strong>Неявной конвертации нет</strong>
        <p>Деньги живут по своим валютам. Обмен оформляется отдельной операцией между денежными счетами.</p>
      </section>

      <section v-if="isLoading" class="card muted">
        Загружаю денежные счета...
      </section>

      <section v-else-if="!hasExchangePair" class="card empty-state">
        <AlertCircle :size="20" :stroke-width="1.75" />
        <div>
          <strong>Недостаточно счетов для обмена</strong>
          <p>Нужен хотя бы один счёт в UZS и один счёт в USD.</p>
        </div>
      </section>

      <template v-if="hasExchangePair">
        <section class="card form-card">
          <div class="field-group">
            <label class="field-label">Списать со счёта</label>
            <BaseSelect
              v-model="fromAccountId"
              :options="fromOptions"
              title="Счёт списания"
              placeholder="Выберите счёт"
            />
          </div>

          <div class="swap-badge" aria-hidden="true">
            <ArrowRightLeft :size="16" :stroke-width="2" />
          </div>

          <div class="field-group">
            <label class="field-label">Зачислить на счёт</label>
            <BaseSelect
              v-model="toAccountId"
              :options="toOptions"
              title="Счёт зачисления"
              placeholder="Выберите счёт"
            />
          </div>

          <div class="field-row">
            <div class="field-group">
              <label class="field-label">Сумма списания</label>
              <input
                v-model="fromAmount"
                class="input-field"
                type="number"
                min="0"
                placeholder="0"
              />
            </div>

            <div class="field-group">
              <label class="field-label">Курс USD/UZS</label>
              <div class="rate-field">
                <input
                  v-model="rate"
                  class="input-field rate-input"
                  type="number"
                  min="0"
                  step="0.000001"
                  placeholder="0"
                />
                <button class="rate-reset" type="button" @click="syncRate">
                  <RefreshCcw :size="14" :stroke-width="2" />
                  Курс
                </button>
              </div>
            </div>
          </div>

          <div class="helper-card">
            <div class="helper-row">
              <span>Справочный USD/UZS</span>
              <strong class="tabular-nums">{{ trimTrailingZeros(latestUsdUzsRate) }}</strong>
            </div>
            <div class="helper-row">
              <span>Направление обмена</span>
              <strong class="tabular-nums">{{ exchangeDirectionHint }}</strong>
            </div>
            <div class="helper-row">
              <span>Будет зачислено</span>
              <strong class="tabular-nums">
                {{ toAccount ? formatPrice(previewToAmount, toAccount.currency) : '—' }}
              </strong>
            </div>
          </div>

          <div class="field-group">
            <label class="field-label">Комментарий</label>
            <input
              v-model="notes"
              class="input-field"
              type="text"
              placeholder="Например, обмен для оплаты расходов в UZS"
            />
          </div>

          <div v-if="formError" class="error-box">
            <AlertCircle :size="18" :stroke-width="1.75" />
            <span>{{ formError }}</span>
          </div>
        </section>

        <section class="card account-card">
          <div class="card-head">
            <h2 class="section-title">Денежные счета</h2>
            <button class="link-btn" type="button" @click="openTopUpSheet()">
              Пополнить счёт
            </button>
          </div>
          <div class="account-list">
            <div v-for="account in activeAccounts" :key="account.id" class="account-row">
              <div class="account-meta">
                <strong>{{ account.name }}</strong>
                <span>{{ account.currency }} · {{ account.kind }}</span>
              </div>
              <div class="account-actions">
                <strong class="tabular-nums">{{ formatPrice(account.balance, account.currency) }}</strong>
                <button class="mini-link" type="button" @click="openTopUpSheet(account.id)">
                  Пополнить
                </button>
              </div>
            </div>
          </div>
        </section>
      </template>

      <section v-else-if="activeAccounts.length" class="card account-card">
        <div class="card-head">
          <h2 class="section-title">Денежные счета</h2>
          <button class="link-btn" type="button" @click="openTopUpSheet()">
            Пополнить счёт
          </button>
        </div>
        <div class="account-list">
          <div v-for="account in activeAccounts" :key="account.id" class="account-row">
            <div class="account-meta">
              <strong>{{ account.name }}</strong>
              <span>{{ account.currency }} · {{ account.kind }}</span>
            </div>
            <div class="account-actions">
              <strong class="tabular-nums">{{ formatPrice(account.balance, account.currency) }}</strong>
              <button class="mini-link" type="button" @click="openTopUpSheet(account.id)">
                Пополнить
              </button>
            </div>
          </div>
        </div>
      </section>
    </main>

    <footer v-if="hasExchangePair" class="footer">
      <button class="submit-btn" type="button" :disabled="isSaving" @click="submit">
        {{ isSaving ? 'Провожу обмен…' : 'Провести обмен' }}
      </button>
    </footer>

    <AppBottomSheet :open="topUpSheetOpen" title="Пополнить денежный счёт" @close="closeTopUpSheet">
      <form class="sheet-form" @submit.prevent="submitTopUp">
        <div class="field-group">
          <label class="field-label">Счёт</label>
          <BaseSelect
            v-model="topUpAccountId"
            :options="fromOptions"
            title="Выбор счёта"
            placeholder="Выберите счёт"
          />
        </div>

        <div class="field-row">
          <div class="field-group">
            <label class="field-label">Сумма</label>
            <input v-model="topUpAmount" class="input-field" type="number" min="0" placeholder="0" />
          </div>
          <div class="field-group">
            <label class="field-label">Валюта</label>
            <div class="static-field">
              <strong>{{ topUpAccount?.currency ?? '—' }}</strong>
            </div>
          </div>
        </div>

        <div class="field-group">
          <label class="field-label">Комментарий</label>
          <input v-model="topUpNotes" class="input-field" type="text" placeholder="Например, завёл наличные для обмена" />
        </div>

        <div v-if="topUpError" class="error-box">
          <AlertCircle :size="18" :stroke-width="1.75" />
          <span>{{ topUpError }}</span>
        </div>

        <button class="submit-btn" type="submit" :disabled="isSavingTopUp">
          {{ isSavingTopUp ? 'Пополняю…' : 'Пополнить счёт' }}
        </button>
      </form>
    </AppBottomSheet>
  </div>
</template>

<style scoped>
.exchange-page { min-height: 100%; background: var(--color-bg-primary); }
.page-header { position: sticky; top: 0; z-index: var(--z-sticky); display: flex; align-items: center; gap: var(--space-3); height: var(--header-height); padding: 0 var(--space-4); border-bottom: 1px solid var(--color-border-subtle); background: var(--color-bg-primary); }
.page-title { flex: 1; font-size: var(--text-lg); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.back-btn, .header-spacer { width: 40px; height: 40px; display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radius-md); color: var(--color-text-primary); }
.content { display: grid; gap: var(--space-4); padding: var(--space-4); padding-bottom: calc(var(--bottom-nav-height) + var(--space-12)); }
.card { display: grid; gap: var(--space-3); padding: var(--space-4); border-radius: var(--radius-lg); border: 1px solid var(--color-border-subtle); background: var(--color-bg-elevated); }
.intro-card p, .empty-state p { color: var(--color-text-secondary); line-height: 1.45; }
.kicker { color: var(--color-text-tertiary); font-size: var(--text-xs); font-weight: var(--font-semibold); text-transform: uppercase; }
.muted { color: var(--color-text-secondary); }
.empty-state { grid-template-columns: auto 1fr; align-items: start; }
.form-card { gap: var(--space-3); }
.field-group { display: grid; gap: var(--space-2); }
.field-row { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-3); }
.field-label { color: var(--color-text-secondary); font-size: var(--text-sm); }
.input-field { width: 100%; min-height: 48px; padding: 0 var(--space-4); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); }
.swap-badge { width: 36px; height: 36px; display: inline-flex; align-items: center; justify-content: center; border-radius: 999px; border: 1px solid var(--color-border-subtle); color: var(--color-brand-600); background: var(--color-brand-50); justify-self: center; }
.rate-field { position: relative; }
.rate-input { padding-right: 82px; }
.rate-reset { position: absolute; top: 50%; right: 6px; transform: translateY(-50%); height: 34px; display: inline-flex; align-items: center; gap: 6px; padding: 0 10px; border-radius: calc(var(--radius-md) - 2px); border: 1px solid var(--color-border-default); background: var(--color-bg-elevated); color: var(--color-text-primary); font-size: var(--text-sm); font-weight: var(--font-medium); }
.helper-card { display: grid; gap: var(--space-2); padding: var(--space-3); border-radius: var(--radius-md); background: var(--color-brand-50); color: var(--color-brand-700); }
.helper-row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); }
.error-box { display: flex; gap: var(--space-2); padding: var(--space-3) var(--space-4); border-radius: var(--radius-md); background: var(--color-error-bg); color: var(--color-danger); }
.section-title { font-size: var(--text-base); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.card-head { display:flex; align-items:center; justify-content:space-between; gap: var(--space-3); }
.link-btn, .mini-link { color: var(--color-brand-600); font-size: var(--text-sm); font-weight: var(--font-semibold); }
.account-list { display: grid; gap: var(--space-2); }
.account-row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); padding: var(--space-3); border-radius: var(--radius-md); background: var(--color-bg-primary); border: 1px solid var(--color-border-subtle); }
.account-meta { display: grid; gap: 2px; }
.account-meta span { color: var(--color-text-secondary); font-size: var(--text-sm); }
.account-actions { display:grid; justify-items:end; gap: 4px; }
.static-field { min-height: 48px; display:flex; align-items:center; padding: 0 var(--space-4); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); }
.sheet-form { display:grid; gap: var(--space-3); padding-bottom: var(--space-4); }
.footer { position: sticky; bottom: 0; padding: var(--space-4); background: linear-gradient(to top, var(--color-bg-primary), transparent); }
.submit-btn { width: 100%; height: 48px; border-radius: var(--radius-lg); background: var(--color-brand-500); color: var(--color-text-inverse); font-weight: var(--font-semibold); }
@media (max-width: 520px) {
  .field-row { grid-template-columns: 1fr; }
  .account-row,
  .card-head { align-items:flex-start; flex-direction:column; }
  .account-actions { justify-items:start; }
}
</style>
