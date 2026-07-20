<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, RefreshCcw, ArrowRightLeft, AlertCircle } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'
import { useToast } from '@/composables/useToast'
import {
  createCurrencyExchange,
  createOwnerContribution,
  fetchCashAccounts,
  type CashAccountRecord,
} from '@/api/finance'
import { formatPrice } from '@/utils/currency'
import { useFxRate } from '@/composables/useFxRate'
import PageChrome from '@/components/layout/PageChrome.vue'

const router = useRouter()
const toast = useToast()
const { t } = useI18n()

const accounts = ref<CashAccountRecord[]>([])
const isLoading = ref(true)
const isSaving = ref(false)
const formError = ref<string | null>(null)
const {
  rate: latestUsdUzsRate,
  rateDate: latestUsdUzsRateDate,
  source: latestUsdUzsRateSource,
  error: latestUsdUzsRateError,
  load: loadLatestUsdUzsRate,
} = useFxRate({ baseCurrency: 'USD', quoteCurrency: 'UZS' })
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

function rateSourceLabel(source: string): string {
  if (source === 'CBU') return 'ЦБ Узбекистана'
  if (source === 'MANUAL') return 'ручной курс'
  return source || 'источник не указан'
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
    await loadLatestUsdUzsRate()
  } catch {
    formError.value = latestUsdUzsRateError.value || t('finance.loadRateFailed')
  }
}

async function loadAccounts(): Promise<void> {
  accounts.value = await fetchCashAccounts()
  normalizeAccountPair()
}

async function submit(): Promise<void> {
  formError.value = null
  if (!fromAccount.value || !toAccount.value) {
    formError.value = t('finance.chooseExchangeAccounts')
    return
  }
  if (fromAccount.value.currency === toAccount.value.currency) {
    formError.value = t('finance.differentCurrencyAccounts')
    return
  }
  if (fromAmountNumber.value <= 0) {
    formError.value = t('finance.debitAmountRequired')
    return
  }
  if (rateNumber.value <= 0 || pairRateNumber.value <= 0) {
    formError.value = t('finance.rateInvalid')
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
    toast.success(t('finance.exchangeDone'))
    fromAmount.value = ''
    notes.value = ''
    await loadAccounts()
  } catch (error: unknown) {
    formError.value = error instanceof Error ? error.message : t('finance.exchangeFailed')
    toast.error(formError.value)
  } finally {
    isSaving.value = false
  }
}

async function submitTopUp(): Promise<void> {
  topUpError.value = null
  const amount = Number.parseFloat(topUpAmount.value)
  if (!topUpAccount.value) {
    topUpError.value = t('finance.chooseTopUpAccount')
    return
  }
  if (!Number.isFinite(amount) || amount <= 0) {
    topUpError.value = t('finance.topUpAmountRequired')
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
    toast.success(t('finance.accountToppedUp'))
    closeTopUpSheet()
    await loadAccounts()
  } catch (error: unknown) {
    topUpError.value = error instanceof Error ? error.message : t('finance.topUpFailed')
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
    formError.value = t('finance.loadAccountsFailed')
  } finally {
    isLoading.value = false
  }
})
</script>

<template>
  <div class="exchange-page">
    <PageChrome :title="t('finance.exchange')" :eyebrow="t('nav.finance')">
      <template #primary>
        <button class="back-btn" type="button" :aria-label="t('common.back')" @click="router.back()">
          <ArrowLeft :size="18" :stroke-width="2" />
        </button>
      </template>
    </PageChrome>

    <main class="content">
      <section class="card intro-card">
        <span class="kicker">{{ t('finance.exchangeRule') }}</span>
        <strong>{{ t('finance.noImplicitConversion') }}</strong>
        <p>{{ t('finance.exchangeRuleText') }}</p>
      </section>

      <section v-if="isLoading" class="card muted">
        {{ t('finance.loadingCashAccounts') }}
      </section>

      <section v-else-if="!hasExchangePair" class="card empty-state">
        <AlertCircle :size="20" :stroke-width="1.75" />
        <div>
          <strong>{{ t('finance.notEnoughAccounts') }}</strong>
          <p>{{ t('finance.needUsdUzsAccounts') }}</p>
        </div>
      </section>

      <template v-if="hasExchangePair">
        <section class="card form-card">
          <div class="field-group">
            <label class="field-label">{{ t('finance.withdrawFromAccount') }}</label>
            <BaseSelect
              v-model="fromAccountId"
              :options="fromOptions"
              :title="t('finance.debitAccount')"
              :placeholder="t('finance.chooseAccount')"
            />
          </div>

          <div class="swap-badge" aria-hidden="true">
            <ArrowRightLeft :size="16" :stroke-width="2" />
          </div>

          <div class="field-group">
            <label class="field-label">{{ t('finance.creditToAccount') }}</label>
            <BaseSelect
              v-model="toAccountId"
              :options="toOptions"
              :title="t('finance.creditAccount')"
              :placeholder="t('finance.chooseAccount')"
            />
          </div>

          <div class="field-row">
            <div class="field-group">
              <label class="field-label">{{ t('finance.debitAmount') }}</label>
              <input
                v-model="fromAmount"
                class="input-field"
                type="number"
                min="0"
                placeholder="0"
              />
            </div>

            <div class="field-group">
              <label class="field-label">{{ t('finance.usdUzsRate') }}</label>
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
                  {{ t('finance.useRate') }}
                </button>
              </div>
            </div>
          </div>

          <div class="helper-card">
            <div class="helper-row">
              <span>{{ t('finance.referenceUsdUzs') }}</span>
              <strong class="tabular-nums">
                {{ latestUsdUzsRate ? trimTrailingZeros(latestUsdUzsRate) : t('finance.noRate') }}
              </strong>
            </div>
            <p v-if="latestUsdUzsRate" class="helper-note">
              Справочный курс: 1 USD = {{ trimTrailingZeros(latestUsdUzsRate) }} UZS ·
              {{ rateSourceLabel(latestUsdUzsRateSource) }} · {{ latestUsdUzsRateDate || 'дата не указана' }}.
              Курс в поле выше — фактический курс этой операции.
            </p>
            <p v-if="latestUsdUzsRateError" class="helper-error">{{ latestUsdUzsRateError }}</p>
            <div class="helper-row">
              <span>{{ t('finance.exchangeDirection') }}</span>
              <strong class="tabular-nums">{{ exchangeDirectionHint }}</strong>
            </div>
            <div class="helper-row">
              <span>{{ t('finance.willBeCredited') }}</span>
              <strong class="tabular-nums">
                {{ toAccount ? formatPrice(previewToAmount, toAccount.currency) : '—' }}
              </strong>
            </div>
          </div>

          <div class="field-group">
            <label class="field-label">{{ t('common.comment') }}</label>
            <input
              v-model="notes"
              class="input-field"
              type="text"
              :placeholder="t('finance.commentPlaceholder')"
            />
          </div>

          <div v-if="formError" class="error-box">
            <AlertCircle :size="18" :stroke-width="1.75" />
            <span>{{ formError }}</span>
          </div>
        </section>

        <section class="card account-card">
          <div class="card-head">
            <h2 class="section-title">{{ t('finance.cashAccounts') }}</h2>
            <button class="link-btn" type="button" @click="openTopUpSheet()">
              {{ t('finance.topUpAccount') }}
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
                  {{ t('finance.topUpAccount') }}
                </button>
              </div>
            </div>
          </div>
        </section>
      </template>

      <section v-else-if="activeAccounts.length" class="card account-card">
        <div class="card-head">
          <h2 class="section-title">{{ t('finance.cashAccounts') }}</h2>
          <button class="link-btn" type="button" @click="openTopUpSheet()">
            {{ t('finance.topUpAccount') }}
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
                {{ t('finance.topUpAccount') }}
              </button>
            </div>
          </div>
        </div>
      </section>
    </main>

    <footer v-if="hasExchangePair" class="footer">
      <button class="submit-btn" type="button" :disabled="isSaving" @click="submit">
        {{ isSaving ? t('finance.exchangeSubmitting') : t('finance.exchangeSubmit') }}
      </button>
    </footer>

    <AppBottomSheet :open="topUpSheetOpen" :title="t('finance.topUpAccountTitle')" @close="closeTopUpSheet">
      <form class="sheet-form" @submit.prevent="submitTopUp">
        <div class="field-group">
          <label class="field-label">{{ t('finance.account') }}</label>
          <BaseSelect
            v-model="topUpAccountId"
            :options="fromOptions"
            :title="t('finance.accountChoice')"
            :placeholder="t('finance.chooseAccount')"
          />
        </div>

        <div class="field-row">
          <div class="field-group">
            <label class="field-label">{{ t('common.amount') }}</label>
            <input v-model="topUpAmount" class="input-field" type="number" min="0" placeholder="0" />
          </div>
          <div class="field-group">
            <label class="field-label">{{ t('finance.currency') }}</label>
            <div class="static-field">
              <strong>{{ topUpAccount?.currency ?? '—' }}</strong>
            </div>
          </div>
        </div>

        <div class="field-group">
          <label class="field-label">{{ t('common.comment') }}</label>
          <input v-model="topUpNotes" class="input-field" type="text" :placeholder="t('finance.topUpCommentPlaceholder')" />
        </div>

        <div v-if="topUpError" class="error-box">
          <AlertCircle :size="18" :stroke-width="1.75" />
          <span>{{ topUpError }}</span>
        </div>

        <button class="submit-btn" type="submit" :disabled="isSavingTopUp">
          {{ isSavingTopUp ? t('finance.topUpSubmitting') : t('finance.topUpAccount') }}
        </button>
      </form>
    </AppBottomSheet>
  </div>
</template>

<style scoped>
.exchange-page { min-height: 100%; background: var(--color-bg-primary); }
.back-btn { width:40px; height:40px; display:inline-flex; align-items:center; justify-content:center; border-radius:var(--radius-md); color:var(--color-text-primary); }
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
.helper-note { margin: 0; font-size: var(--font-size-xs); line-height: 1.45; color: var(--color-text-secondary); }
.helper-error { margin: 0; font-size: var(--font-size-xs); line-height: 1.4; color: var(--color-danger); }
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
@media (min-width: 768px) {
  .content { max-width:1120px; margin:0 auto; grid-template-columns:minmax(0, 1.15fr) minmax(300px, .85fr); padding:var(--space-6); padding-bottom:var(--space-6); }
  .intro-card,.content > .muted,.content > .empty-state { grid-column:1 / -1; }
  .form-card { grid-column:1; grid-row:2 / span 2; }
  .account-card { grid-column:2; }
  .footer { position:static; max-width:1120px; margin:0 auto; padding:0 var(--space-6) var(--space-8); background:none; }
  .submit-btn { width:auto; min-width:220px; margin-left:auto; padding:0 var(--space-6); }
}
@media (min-width: 1280px) {
  .exchange-page { background: transparent; }
  .content { max-width:none; margin:0; padding-inline:var(--space-8); }
  .footer { max-width:none; margin:0; padding-inline:var(--space-8); }
}
@media (max-width: 520px) {
  .field-row { grid-template-columns: 1fr; }
  .account-row,
  .card-head { align-items:flex-start; flex-direction:column; }
  .account-actions { justify-items:start; }
}
</style>
