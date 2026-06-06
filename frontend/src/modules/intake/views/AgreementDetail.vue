<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  CalendarDays,
  HandCoins,
  Plus,
  RotateCcw,
  Send,
  Users,
  Wallet,
} from 'lucide-vue-next'
import BaseSelect from '@/components/base/BaseSelect.vue'
import MoneyCurrencyInput from '@/components/forms/MoneyCurrencyInput.vue'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import {
  addAgreementContribution,
  addAgreementWithdrawal,
  createAgreementAllocations,
  fetchAgreementAllocationPreview,
  fetchInvestmentAgreement,
  fetchCapitalPositions,
  fetchAgreementProfitSummary,
  fetchProcurementVentureSummary,
  type AgreementAllocationPreview,
  type AgreementProfitRow,
  type CapitalPositionRow,
  type InvestmentAgreementDetail,
  type ProcurementVentureSummary,
} from '@/api/partnerships'
import { fetchCashAccounts, type CashAccountRecord } from '@/api/finance'
import AgreementAdvancesCard from '@/modules/intake/components/agreement/AgreementAdvancesCard.vue'
import AgreementRecoveredCapitalCard from '@/modules/intake/components/agreement/AgreementRecoveredCapitalCard.vue'
import AdvanceSettleSheet from '@/modules/intake/components/agreement/AdvanceSettleSheet.vue'
import DividendPaySheet from '@/modules/intake/components/agreement/DividendPaySheet.vue'
import { formatPrice } from '@/utils/currency'
import { useToast } from '@/composables/useToast'
import { useFxRate } from '@/composables/useFxRate'
import { partnerRoleLabel, procurementStatusLabel } from '@/utils/domainLabels'
import { intlLocale } from '@/i18n/format'
import { getApiErrorMessage } from '@/utils/errors'

const route = useRoute()
const router = useRouter()
const toast = useToast()
const { t, locale } = useI18n()

const agreement = ref<InvestmentAgreementDetail | null>(null)
const loading = ref(false)
const error = ref('')
const positions = ref<CapitalPositionRow[]>([])
const hasInterparty = computed(() => positions.value.some((p) => Math.abs(Number(p.net) || 0) > 0.01))
const profitRows = ref<AgreementProfitRow[]>([])
const ventureSummaries = ref<ProcurementVentureSummary[]>([])
const operatingAccounts = ref<CashAccountRecord[]>([])
const settleOpen = ref(false)
const activePosition = ref<CapitalPositionRow | null>(null)
const dividendOpen = ref(false)
const contributionPartnerId = ref<number | null>(null)
const contributionAmount = ref('')
const contributionCurrency = ref<'USD' | 'UZS'>('USD')
const savingContribution = ref(false)
const withdrawalPartnerId = ref<number | null>(null)
const withdrawalAmount = ref('')
const withdrawalCurrency = ref<'USD' | 'UZS'>('USD')
const savingWithdrawal = ref(false)
const savingRecoveredCapital = ref(false)
const withdrawalError = ref('')
const allocationProcurementId = ref<number | null>(null)
const allocationPreview = ref<AgreementAllocationPreview | null>(null)
const allocating = ref(false)
const {
  rate: latestUsdRate,
  error: latestUsdRateError,
  load: loadLatestUsdRate,
} = useFxRate({ baseCurrency: 'USD', quoteCurrency: 'UZS' })

interface RecoveredCapitalRow {
  key: string
  procurementId: number
  partnerId: number
  partnerName: string
  role: string
  availableUzs: number
  recoveredUzs: number
  returnedUzs: number
}

const agreementId = computed(() => Number(route.params.id))
const activeProcurements = computed(() => (agreement.value?.procurements ?? []).filter((item) => item.status === 'OPEN' || item.status === 'PARTIALLY_RECEIVED'))
const balanceLabel = computed(() => {
  const parts = Object.entries(agreement.value?.balances ?? {})
    .filter(([, amount]) => Math.abs(Number.parseFloat(amount || '0')) > 0.000001)
    .map(([currency, amount]) => formatPrice(amount, currency))
  return parts.length ? parts.join(' · ') : '0'
})
const primaryCurrency = computed(() => agreement.value?.currency ?? 'UZS')
const plannedBudget = computed(() => Number(agreement.value?.planned_budget ?? 0) || 0)
const availablePrimaryAmount = computed(() => Number(agreement.value?.balances?.[primaryCurrency.value] ?? 0) || 0)
const contributedTotal = computed(() => agreement.value?.participant_totals.reduce((sum, row) => sum + Number(row.contributed_amount || 0), 0) ?? 0)
const allocatedTotal = computed(() => agreement.value?.participant_totals.reduce((sum, row) => sum + Number(row.allocated_amount || 0), 0) ?? 0)
const usedTotal = computed(() => Math.max(0, contributedTotal.value - availablePrimaryAmount.value))
const budgetBase = computed(() => Math.max(plannedBudget.value, contributedTotal.value, 1))
const availableProgress = computed(() => Math.min(100, (availablePrimaryAmount.value / budgetBase.value) * 100))
const usedProgress = computed(() => Math.min(100, (usedTotal.value / budgetBase.value) * 100))
const investorName = computed(() => agreement.value?.partners.find((partner) => partner.role === 'INVESTOR')?.partner_name ?? 'Инвестор')
const agreementSideOptions = computed(() => (agreement.value?.partners ?? []).map((partner) => ({
  value: partner.partner,
  label: agreementSideLabel(partner.role),
})))
const partyRows = computed(() => {
  const rows = agreement.value?.participant_totals ?? []
  const total = contributedTotal.value
  const planBase = plannedBudget.value
  return rows.map((row) => {
    const plannedAmount = Number(row.planned_capital_share || 0)
    const contributedAmount = Number(row.contributed_amount || 0)
    const plannedCapitalPercent = planBase > 0 ? Math.round((plannedAmount / planBase) * 100) : null
    const actualCapitalPercent = total > 0 ? Math.round((contributedAmount / total) * 100) : null
    return {
      ...row,
      displayName: row.role === 'OPERATOR' ? 'Бизнес' : row.partner_name,
      plannedAmount,
      contributedAmount,
      plannedCapitalPercent,
      actualCapitalPercent,
      plannedProfitPercent: Math.round((Number(row.planned_profit_share || 0) || 0) * 100),
      availableAmount: Number(row.available_amount || 0) || 0,
      allocatedAmount: Number(row.allocated_amount || 0) || 0,
      withdrawnAmount: Number(row.withdrawn_amount || 0) || 0,
    }
  })
})
const recoveredCapitalRows = computed<RecoveredCapitalRow[]>(() =>
  ventureSummaries.value.flatMap((summary) =>
    summary.positions
      .filter((row) => Number(row.capital_return_available_uzs || 0) > 0.01)
      .map((row) => ({
        key: `${summary.procurement_id}-${row.partner_id}`,
        procurementId: summary.procurement_id,
        partnerId: row.partner_id,
        partnerName: row.partner_name,
        role: row.role,
        availableUzs: Number(row.capital_return_available_uzs || 0),
        recoveredUzs: Number(row.capital_recovered_uzs || 0),
        returnedUzs: Number(row.capital_returned_uzs || 0),
      })),
  ),
)
const availableByPartnerCurrency = computed<Record<number, Record<string, number>>>(() => {
  const rows: Record<number, Record<string, number>> = {}
  const add = (partnerId: number, currency: string, amount: number) => {
    const bucket = rows[partnerId] ?? {}
    bucket[currency] = (bucket[currency] ?? 0) + amount
    rows[partnerId] = bucket
  }
  for (const contribution of agreement.value?.contributions ?? []) {
    add(contribution.partner, contribution.currency, Number(contribution.amount || 0))
  }
  for (const withdrawal of agreement.value?.withdrawals ?? []) {
    add(withdrawal.partner, withdrawal.currency, -Number(withdrawal.amount || 0))
  }
  for (const allocation of agreement.value?.allocations ?? []) {
    const amount = Number(allocation.amount || 0)
    add(
      allocation.partner,
      allocation.currency,
      allocation.direction === 'TO_PROCUREMENT' ? -amount : amount,
    )
  }
  return rows
})
const withdrawalAmountValue = computed(() => Number.parseFloat(withdrawalAmount.value || '0') || 0)
const withdrawalAvailableAmount = computed(() => {
  if (!withdrawalPartnerId.value) return 0
  return availableByPartnerCurrency.value[withdrawalPartnerId.value]?.[withdrawalCurrency.value] ?? 0
})
const withdrawalAvailabilityError = computed(() => {
  if (!withdrawalPartnerId.value || withdrawalAmountValue.value <= 0) return ''
  if (withdrawalAmountValue.value <= withdrawalAvailableAmount.value + 0.000001) return ''
  return `Нельзя вернуть ${formatPrice(withdrawalAmountValue.value, withdrawalCurrency.value)}: доступно только ${formatPrice(withdrawalAvailableAmount.value, withdrawalCurrency.value)}.`
})

function formatDate(value: string): string {
  return new Date(value).toLocaleString(intlLocale(locale.value), { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

function agreementSideLabel(role: string): string {
  if (role === 'INVESTOR') return 'Инвестор'
  if (role === 'OPERATOR') return 'Бизнес'
  return partnerRoleLabel(role)
}

function agreementStatusLabel(status: string): string {
  if (status === 'ACTIVE') return 'Активен'
  if (status === 'CLOSED') return 'Закрыт'
  if (status === 'DRAFT') return 'Черновик'
  return status
}

function dateOnly(value: string): string {
  return new Date(value).toLocaleDateString(intlLocale(locale.value), { day: 'numeric', month: 'short', year: 'numeric' })
}

function setContributionPartner(value: string | number | boolean | null): void {
  contributionPartnerId.value = typeof value === 'number' ? value : Number(value) || null
}

function setWithdrawalPartner(value: string | number | boolean | null): void {
  withdrawalPartnerId.value = typeof value === 'number' ? value : Number(value) || null
}

function fxRateForCurrency(currency: string): string {
  return currency === 'USD' ? latestUsdRate.value : '1'
}

function ensureFxRate(currency: string): boolean {
  if (currency !== 'USD' || latestUsdRate.value) return true
  toast.error(t('procurements.syncUsdRateFirst'))
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
    await loadAdvances()
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
    toast.error(getApiErrorMessage(err, t('procurements.contributionAddFailed')))
  } finally {
    savingContribution.value = false
  }
}

async function saveWithdrawal(): Promise<void> {
  if (!agreement.value || !withdrawalPartnerId.value || !withdrawalAmount.value) return
  withdrawalError.value = withdrawalAvailabilityError.value
  if (withdrawalError.value) {
    toast.error(withdrawalError.value)
    return
  }
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
    withdrawalError.value = ''
    toast.success(t('procurements.withdrawalAdded'))
    await load()
  } catch (err: unknown) {
    withdrawalError.value = getApiErrorMessage(err, t('procurements.withdrawalAddFailed'))
    toast.error(withdrawalError.value)
  } finally {
    savingWithdrawal.value = false
  }
}

async function returnRecoveredCapital(payload: {
  row: RecoveredCapitalRow
  amount: string
  currency: 'UZS' | 'USD'
  fxRate: string
  accountId: number
}): Promise<void> {
  if (!agreement.value) return
  savingRecoveredCapital.value = true
  try {
    await addAgreementWithdrawal(agreement.value.id, {
      partner_id: payload.row.partnerId,
      procurement_id: payload.row.procurementId,
      from_account_id: payload.accountId,
      amount: payload.amount,
      currency: payload.currency,
      fx_rate: payload.fxRate,
      reason: `Возврат восстановленного капитала по приходу #${payload.row.procurementId}`,
    })
    toast.success(t('procurements.withdrawalAdded'))
    await load()
  } catch (err: unknown) {
    toast.error(getApiErrorMessage(err, t('procurements.withdrawalAddFailed')))
  } finally {
    savingRecoveredCapital.value = false
  }
}

async function loadAdvances(): Promise<void> {
  try {
    const [pos, profit, accounts] = await Promise.all([
      fetchCapitalPositions(agreementId.value),
      fetchAgreementProfitSummary(agreementId.value),
      operatingAccounts.value.length ? Promise.resolve(operatingAccounts.value) : fetchCashAccounts(),
    ])
    positions.value = pos
    profitRows.value = profit
    operatingAccounts.value = accounts.filter((a) => a.kind !== 'agreement_capital')
    const procurementIds = agreement.value?.procurements.map((procurement) => procurement.id) ?? []
    ventureSummaries.value = procurementIds.length
      ? await Promise.all(procurementIds.map((id) => fetchProcurementVentureSummary(id)))
      : []
  } catch {
    // positions/distributions are supplementary — keep the page usable if they fail
  }
}

function openSettle(position: CapitalPositionRow): void {
  activePosition.value = position
  settleOpen.value = true
}

async function onAdvanceSettled(): Promise<void> {
  settleOpen.value = false
  await load()
}

async function onDividendPaid(): Promise<void> {
  dividendOpen.value = false
  await load()
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
})
</script>

<template>
  <main class="min-h-dvh bg-background pb-[calc(var(--bottom-nav-height)+1rem)]">
    <header class="sticky top-0 z-20 border-b border-border bg-background/95 backdrop-blur">
      <div class="mx-auto flex min-h-14 w-full max-w-6xl items-center gap-3 px-4">
        <Button variant="ghost" size="icon" type="button" :aria-label="t('common.back')" @click="router.back()">
          <ArrowLeft />
        </Button>
        <div class="min-w-0 flex-1">
          <p class="truncate text-lg font-semibold text-foreground">
            {{ t('procurements.agreementTitle', { id: route.params.id }) }}
          </p>
          <p v-if="agreement" class="truncate text-xs text-muted-foreground">
            {{ investorName }} · {{ dateOnly(agreement.opened_at) }}
          </p>
        </div>
        <Button
          variant="outline"
          size="icon"
          type="button"
          :aria-label="t('procurements.report')"
          @click="router.push({ name: 'reports-agreement-profitability', params: { id: route.params.id } })"
        >
          <BarChart3 />
        </Button>
      </div>
    </header>

    <section class="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-4">
      <div v-if="loading" class="grid gap-3">
        <Skeleton class="h-40 rounded-2xl" />
        <Skeleton class="h-32 rounded-2xl" />
        <Skeleton class="h-40 rounded-2xl" />
      </div>
      <Alert v-else-if="error" variant="destructive">
        <AlertDescription>{{ error }}</AlertDescription>
      </Alert>

      <template v-else-if="agreement">
        <Card class="overflow-hidden rounded-2xl bg-background">
          <CardHeader class="pb-0">
            <div class="flex flex-wrap items-center gap-2">
              <CardTitle class="text-lg">Инвестдоговор #{{ agreement.id }}</CardTitle>
              <Badge variant="secondary">{{ agreementStatusLabel(agreement.status) }}</Badge>
            </div>
            <CardDescription class="mt-1">{{ investorName }} · {{ dateOnly(agreement.opened_at) }}</CardDescription>
          </CardHeader>
          <CardContent class="flex flex-col gap-3 pt-4">
            <div class="min-w-0">
              <p class="text-xs text-muted-foreground">{{ t('procurements.freeBalance') }}</p>
              <p class="text-2xl font-semibold tabular-nums text-foreground">{{ balanceLabel }}</p>
            </div>
            <div class="flex h-1.5 overflow-hidden rounded-full bg-muted">
              <div class="bg-primary" :style="{ width: `${availableProgress}%` }" />
              <div class="bg-muted-foreground/40" :style="{ width: `${usedProgress}%` }" />
            </div>
            <div class="flex flex-wrap gap-x-4 gap-y-1 text-xs tabular-nums text-muted-foreground">
              <span>План <strong class="font-semibold text-foreground">{{ formatPrice(plannedBudget, primaryCurrency) }}</strong></span>
              <span>Внесено <strong class="font-semibold text-foreground">{{ formatPrice(contributedTotal, primaryCurrency) }}</strong></span>
              <span>В приходах <strong class="font-semibold text-foreground">{{ formatPrice(allocatedTotal, primaryCurrency) }}</strong></span>
            </div>
          </CardContent>
        </Card>

        <!-- Взаиморасчёты возникают только под Путём 2 и только при расхождении -->
        <AgreementAdvancesCard v-if="hasInterparty" :positions="positions" @settle="openSettle" />

        <AgreementRecoveredCapitalCard
          :rows="recoveredCapitalRows"
          :accounts="operatingAccounts"
          :usd-rate="latestUsdRate"
          :saving="savingRecoveredCapital"
          @return-capital="returnRecoveredCapital"
        />

        <!-- Распределение прибыли — только когда есть что распределять -->
        <div v-if="profitRows.length" class="flex flex-wrap items-center gap-2">
          <Button type="button" @click="dividendOpen = true">
            <HandCoins data-icon="inline-start" />
            Распределить прибыль
          </Button>
        </div>

        <div class="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
          <Card class="rounded-2xl bg-background">
            <CardHeader>
              <div class="flex items-start justify-between gap-3">
                <div>
                  <CardTitle class="text-base">{{ t('procurements.participants') }}</CardTitle>
                  <CardDescription class="mt-1">План договора и текущий факт по капиталу.</CardDescription>
                </div>
                <Users class="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
              </div>
            </CardHeader>
            <CardContent class="flex flex-col gap-4">
              <div class="grid grid-cols-[1fr_1fr_0.75fr_0.75fr] items-baseline gap-x-3 gap-y-2 text-sm">
                <span />
                <span class="text-right text-xs text-muted-foreground">план</span>
                <span class="text-right text-xs text-muted-foreground">капитал</span>
                <span class="text-right text-xs text-muted-foreground">прибыль</span>
                <template v-for="row in partyRows" :key="`plan-${row.partner_id}`">
                  <span class="min-w-0 truncate font-medium text-foreground">{{ row.displayName }}</span>
                  <span class="whitespace-nowrap text-right tabular-nums text-foreground">{{ formatPrice(row.plannedAmount, primaryCurrency) }}</span>
                  <span class="text-right tabular-nums text-foreground">{{ row.plannedCapitalPercent != null ? `${row.plannedCapitalPercent}%` : '—' }}</span>
                  <span class="text-right tabular-nums text-foreground">{{ row.plannedProfitPercent }}%</span>
                </template>
              </div>

              <Separator />

              <div class="grid grid-cols-[1fr_1fr_0.75fr_0.75fr] items-baseline gap-x-3 gap-y-2 text-sm">
                <span />
                <span class="text-right text-xs text-muted-foreground">внёс</span>
                <span class="text-right text-xs text-muted-foreground">капитал</span>
                <span class="text-right text-xs text-muted-foreground">доступно</span>
                <template v-for="row in partyRows" :key="`fact-${row.partner_id}`">
                  <span class="min-w-0 truncate font-medium text-foreground">{{ row.displayName }}</span>
                  <span class="whitespace-nowrap text-right tabular-nums text-foreground">{{ formatPrice(row.contributedAmount, primaryCurrency) }}</span>
                  <span class="text-right tabular-nums text-foreground">{{ row.actualCapitalPercent != null ? `${row.actualCapitalPercent}%` : '—' }}</span>
                  <span class="whitespace-nowrap text-right font-semibold tabular-nums text-foreground">{{ formatPrice(row.availableAmount, primaryCurrency) }}</span>
                </template>
              </div>
            </CardContent>
          </Card>

          <div class="grid gap-4">
            <Card class="rounded-2xl bg-background">
              <CardHeader>
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <CardTitle class="text-base">{{ t('procurements.contribution') }}</CardTitle>
                    <CardDescription class="mt-1">Пополнение реального денежного пула договора.</CardDescription>
                  </div>
                  <Wallet class="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
                </div>
              </CardHeader>
              <CardContent class="flex flex-col gap-3">
                <div class="grid gap-3 sm:grid-cols-[0.9fr_1.1fr]">
                  <BaseSelect
                    :model-value="contributionPartnerId"
                    :options="agreementSideOptions"
                    title="Кто пополняет договор"
                    @update:model-value="setContributionPartner"
                  />
                  <MoneyCurrencyInput
                    v-model="contributionAmount"
                    v-model:currency="contributionCurrency"
                    :placeholder="t('common.amount')"
                    aria-label="Сумма пополнения договора"
                  />
                </div>
                <Button type="button" :disabled="savingContribution" @click="saveContribution">
                  <Plus data-icon="inline-start" />
                  {{ t('procurements.addContribution') }}
                </Button>
              </CardContent>
            </Card>

            <Card v-if="contributedTotal > 0" class="rounded-2xl bg-background">
              <CardHeader>
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <CardTitle class="text-base">{{ t('procurements.withdrawalFromAgreement') }}</CardTitle>
                    <CardDescription class="mt-1">Возврат доступных денег участнику без перерасчёта старых приходов.</CardDescription>
                  </div>
                  <RotateCcw class="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
                </div>
              </CardHeader>
              <CardContent class="flex flex-col gap-3">
                <div class="grid gap-3 sm:grid-cols-[0.9fr_1.1fr]">
                  <BaseSelect
                    :model-value="withdrawalPartnerId"
                    :options="agreementSideOptions"
                    title="Кому вернуть деньги"
                    @update:model-value="setWithdrawalPartner"
                  />
                  <MoneyCurrencyInput
                    v-model="withdrawalAmount"
                    v-model:currency="withdrawalCurrency"
                    :placeholder="t('common.amount')"
                    aria-label="Сумма возврата из договора"
                  />
                </div>
                <p v-if="withdrawalAvailabilityError || withdrawalError" class="text-sm text-destructive">
                  {{ withdrawalAvailabilityError || withdrawalError }}
                </p>
                <Button
                  variant="outline"
                  type="button"
                  :disabled="savingWithdrawal || Boolean(withdrawalAvailabilityError)"
                  @click="saveWithdrawal"
                >
                  <RotateCcw data-icon="inline-start" />
                  {{ t('procurements.recordWithdrawal') }}
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>

        <div class="grid gap-4 lg:grid-cols-[1fr_0.9fr]">
          <Card class="rounded-2xl bg-background">
            <CardHeader>
              <div class="flex items-start justify-between gap-3">
                <div>
                  <CardTitle class="text-base">{{ t('procurements.linkedProcurements') }}</CardTitle>
                  <CardDescription class="mt-1">Приходы, которые используют капитал этого договора.</CardDescription>
                </div>
                <Button variant="outline" size="sm" type="button" class="shrink-0" @click="router.push({ name: 'procurement-create', query: { agreement_id: agreement.id } })">
                  <Plus data-icon="inline-start" />
                  Новый приход
                </Button>
              </div>
            </CardHeader>
            <CardContent class="flex flex-col gap-2">
              <button
                v-for="procurement in agreement.procurements"
                :key="procurement.id"
                class="flex items-center justify-between gap-3 rounded-xl border border-border bg-background px-3 py-2.5 text-left transition hover:bg-muted/50"
                type="button"
                @click="router.push({ name: 'procurement-detail', params: { id: procurement.id } })"
              >
                <span class="min-w-0">
                  <span class="block truncate text-sm font-medium text-foreground">#{{ procurement.id }} · {{ procurement.supplier_name || t('procurements.noSupplier') }}</span>
                  <span class="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
                    <CalendarDays class="size-3.5" aria-hidden="true" />
                    {{ procurement.opened_at ? dateOnly(procurement.opened_at) : '—' }}
                  </span>
                </span>
                <span class="flex shrink-0 items-center gap-2">
                  <Badge variant="secondary">{{ procurementStatusLabel(procurement.status) }}</Badge>
                  <ArrowRight class="size-4 text-muted-foreground" aria-hidden="true" />
                </span>
              </button>
              <p v-if="agreement.procurements.length === 0" class="rounded-xl bg-muted/60 p-3 text-sm text-muted-foreground">
                {{ t('procurements.noLinkedProcurements') }}
              </p>
            </CardContent>
          </Card>

          <Card v-if="activeProcurements.length" class="rounded-2xl bg-background">
            <CardHeader>
              <div class="flex items-start justify-between gap-3">
                <div>
                  <CardTitle class="text-base">{{ t('procurements.allocateCapital') }}</CardTitle>
                  <CardDescription class="mt-1">Предложение распределения денег в выбранный приход.</CardDescription>
                </div>
                <Send class="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
              </div>
            </CardHeader>
            <CardContent class="flex flex-col gap-3">
              <div class="grid gap-2 sm:grid-cols-[1fr_auto]">
                <select
                  v-model.number="allocationProcurementId"
                  class="h-9 min-w-0 rounded-lg border border-border bg-background px-3 text-sm text-foreground outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  <option v-for="procurement in activeProcurements" :key="procurement.id" :value="procurement.id">
                    {{ t('procurements.procurementNumber', { id: procurement.id }) }}
                  </option>
                </select>
                <Button variant="outline" type="button" @click="loadAllocationPreview">{{ t('procurements.calculate') }}</Button>
              </div>

              <div v-if="allocationPreview" class="flex flex-col gap-2 rounded-xl bg-muted/60 p-3">
                <div v-for="row in allocationPreview.suggestions" :key="`${row.partner_id}-${row.currency}`" class="flex items-baseline justify-between gap-3 text-sm">
                  <span class="min-w-0 truncate text-muted-foreground">{{ row.partner_name }}</span>
                  <span class="font-semibold tabular-nums text-foreground">{{ formatPrice(row.amount, row.currency) }}</span>
                </div>
                <Button type="button" :disabled="allocating" @click="allocateSuggested">
                  <Send data-icon="inline-start" />
                  {{ t('procurements.confirmAllocation') }}
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        <Card class="rounded-2xl bg-background">
          <CardHeader>
            <CardTitle class="text-base">{{ t('procurements.history') }}</CardTitle>
            <CardDescription>{{ agreement.history.length }} операций по договору</CardDescription>
          </CardHeader>
          <CardContent class="flex flex-col">
            <article v-for="entry in agreement.history.slice(0, 8)" :key="entry.id" class="flex items-start justify-between gap-3 border-t border-border py-3 first:border-t-0 first:pt-0 last:pb-0">
              <div class="min-w-0">
                <p class="truncate text-sm font-medium text-foreground">{{ entry.title }}</p>
                <p class="mt-0.5 text-xs text-muted-foreground">{{ formatDate(entry.date) }} · {{ entry.partner_name || t('procurements.system') }}</p>
              </div>
              <p class="shrink-0 text-sm font-semibold tabular-nums text-foreground">{{ formatPrice(entry.amount, entry.currency) }}</p>
            </article>
            <p v-if="agreement.history.length === 0" class="rounded-xl bg-muted/60 p-3 text-sm text-muted-foreground">
              Истории по договору пока нет.
            </p>
          </CardContent>
        </Card>
      </template>
    </section>

    <AdvanceSettleSheet
      :open="settleOpen"
      :agreement-id="agreementId"
      :position="activePosition"
      :accounts="operatingAccounts"
      @close="settleOpen = false"
      @settled="onAdvanceSettled"
    />

    <DividendPaySheet
      :open="dividendOpen"
      :rows="profitRows"
      :accounts="operatingAccounts"
      @close="dividendOpen = false"
      @paid="onDividendPaid"
    />
  </main>
</template>
