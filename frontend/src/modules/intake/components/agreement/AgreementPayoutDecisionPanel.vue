<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { AlertTriangle, ArrowDownToLine, Repeat2, Send, WalletCards } from 'lucide-vue-next'
import BaseSelect from '@/components/base/BaseSelect.vue'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { formatPrice } from '@/utils/currency'
import type { CashAccountRecord } from '@/api/finance'
import type { PayoutDecisionPreview, PayoutDecisionType } from '@/api/partnerships'

export interface AgreementRecoveredCapitalDecisionRow {
  key: string
  procurementId: number
  partnerId: number
  partnerName: string
  role: string
  availableUzs: number
  recoveredUzs: number
  returnedUzs: number
  rolledUzs: number
}

const props = defineProps<{
  rows: AgreementRecoveredCapitalDecisionRow[]
  accounts: CashAccountRecord[]
  preview: PayoutDecisionPreview | null
  previewing?: boolean
  saving?: boolean
}>()

const emit = defineEmits<{
  preview: [payload: { decisionType: PayoutDecisionType; amountUzs: string; accountId: number }]
  execute: [payload: {
    decisionType: PayoutDecisionType
    amountUzs: string
    accountId: number
    allocations: Array<{ procurement_id: number; partner_id: number; amount_uzs: string }>
  }]
}>()

const decisionType = ref<PayoutDecisionType>('ROLL_OVER_CAPITAL')
const amountUzs = ref('')
const accountId = ref<number | null>(null)
const allocationAmounts = ref<Record<string, string>>({})

const totalAvailableUzs = computed(() => props.rows.reduce((sum, row) => sum + row.availableUzs, 0))
const totalRecoveredUzs = computed(() => props.rows.reduce((sum, row) => sum + row.recoveredUzs, 0))
const totalReturnedUzs = computed(() => props.rows.reduce((sum, row) => sum + row.returnedUzs, 0))
const totalRolledUzs = computed(() => props.rows.reduce((sum, row) => sum + row.rolledUzs, 0))
const activePreview = computed(() => props.preview?.decision_type === decisionType.value ? props.preview : null)
const accountTitle = computed(() =>
  decisionType.value === 'PAY_OUT' ? 'Операционная UZS-касса' : 'Операционная касса',
)
const eligibleAccounts = computed(() =>
  props.accounts.filter((account) => {
    if (!account.is_active) return false
    const currency = account.currency.toUpperCase()
    if (decisionType.value === 'PAY_OUT') return currency === 'UZS'
    return currency === 'UZS' || currency === 'USD'
  }),
)
const accountOptions = computed(() =>
  eligibleAccounts.value.map((account) => ({
    value: account.id,
    label: `${account.name} · ${formatPrice(account.balance, account.currency.toUpperCase())}`,
  })),
)
const allocationRows = computed(() => activePreview.value?.allocations ?? [])
const allocationTotal = computed(() =>
  allocationRows.value.reduce((sum, row) => sum + (Number(allocationAmounts.value[allocationKey(row.procurement_id, row.partner_id)] || 0) || 0), 0),
)
const requestedAmount = computed(() => Number(amountUzs.value || 0) || 0)
const allocationMismatch = computed(() => Math.abs(allocationTotal.value - requestedAmount.value) > 0.01)
const canPreview = computed(() => Boolean(props.rows.length && accountId.value && requestedAmount.value > 0))
const canExecute = computed(() => Boolean(
  activePreview.value?.allowed
  && accountId.value
  && allocationRows.value.length
  && !allocationMismatch.value
  && requestedAmount.value > 0,
))
const actionLabel = computed(() => decisionType.value === 'ROLL_OVER_CAPITAL' ? 'Оставить капитал в деле' : 'Выплатить капитал')

function allocationKey(procurementId: number, partnerId: number): string {
  return `${procurementId}:${partnerId}`
}

function setAccount(value: string | number | boolean | null): void {
  accountId.value = typeof value === 'number' ? value : Number(value) || null
}

function selectDecision(type: PayoutDecisionType): void {
  decisionType.value = type
}

function requestPreview(): void {
  if (!accountId.value || !canPreview.value) return
  emit('preview', {
    decisionType: decisionType.value,
    amountUzs: Number(amountUzs.value || 0).toFixed(2),
    accountId: accountId.value,
  })
}

function executeDecision(): void {
  if (!accountId.value || !canExecute.value) return
  emit('execute', {
    decisionType: decisionType.value,
    amountUzs: Number(amountUzs.value || 0).toFixed(2),
    accountId: accountId.value,
    allocations: allocationRows.value.map((row) => ({
      procurement_id: row.procurement_id,
      partner_id: row.partner_id,
      amount_uzs: Number(allocationAmounts.value[allocationKey(row.procurement_id, row.partner_id)] || 0).toFixed(2),
    })),
  })
}

watch(() => props.rows, (rows) => {
  amountUzs.value = rows.length ? totalAvailableUzs.value.toFixed(2) : ''
}, { immediate: true, deep: true })

watch(accountOptions, (options) => {
  if (!options.length) {
    accountId.value = null
    return
  }
  if (!accountId.value || !options.some((option) => option.value === accountId.value)) {
    const funded = eligibleAccounts.value.find((account) => Number(account.balance || 0) > 0)
    accountId.value = funded?.id ?? options[0].value
  }
}, { immediate: true })

watch(activePreview, (preview) => {
  const next: Record<string, string> = {}
  for (const row of preview?.allocations ?? []) {
    next[allocationKey(row.procurement_id, row.partner_id)] = row.amount_uzs
  }
  allocationAmounts.value = next
}, { immediate: true })
</script>

<template>
  <section class="rounded-lg border border-border bg-background">
    <div class="border-b border-border px-4 py-4">
      <div class="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div class="min-w-0">
          <h2 class="text-base font-semibold text-foreground">Решение по восстановленному капиталу</h2>
          <p class="mt-1 text-sm text-muted-foreground">
            Возврат и rollover проходят как одно group decision с policy gate и распределением по строкам.
          </p>
        </div>
        <div class="grid grid-cols-2 gap-2 text-right sm:grid-cols-4">
          <span>
            <span class="block text-[11px] text-muted-foreground">доступно</span>
            <strong class="block text-sm tabular-nums text-foreground">{{ formatPrice(totalAvailableUzs, 'UZS') }}</strong>
          </span>
          <span>
            <span class="block text-[11px] text-muted-foreground">восстановлено</span>
            <strong class="block text-sm tabular-nums text-foreground">{{ formatPrice(totalRecoveredUzs, 'UZS') }}</strong>
          </span>
          <span>
            <span class="block text-[11px] text-muted-foreground">выплачено</span>
            <strong class="block text-sm tabular-nums text-foreground">{{ formatPrice(totalReturnedUzs, 'UZS') }}</strong>
          </span>
          <span>
            <span class="block text-[11px] text-muted-foreground">оставлено</span>
            <strong class="block text-sm tabular-nums text-foreground">{{ formatPrice(totalRolledUzs, 'UZS') }}</strong>
          </span>
        </div>
      </div>
    </div>

    <div v-if="!rows.length" class="px-4 py-6 text-sm text-muted-foreground">
      Нет восстановленного капитала, доступного для решения.
    </div>

    <div v-else class="grid gap-4 p-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <div class="space-y-4">
        <div class="grid grid-cols-2 gap-2">
          <button
            type="button"
            class="flex min-h-20 items-start gap-3 rounded-lg border p-3 text-left transition"
            :class="decisionType === 'ROLL_OVER_CAPITAL' ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/50'"
            @click="selectDecision('ROLL_OVER_CAPITAL')"
          >
            <Repeat2 class="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
            <span class="min-w-0">
              <strong class="block text-sm text-foreground">Оставить в деле</strong>
              <span class="mt-1 block text-xs text-muted-foreground">Перенести cash в capital pool без роста external paid-in.</span>
            </span>
          </button>
          <button
            type="button"
            class="flex min-h-20 items-start gap-3 rounded-lg border p-3 text-left transition"
            :class="decisionType === 'PAY_OUT' ? 'border-primary bg-primary/5' : 'border-border hover:bg-muted/50'"
            @click="selectDecision('PAY_OUT')"
          >
            <ArrowDownToLine class="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
            <span class="min-w-0">
              <strong class="block text-sm text-foreground">Выплатить</strong>
              <span class="mt-1 block text-xs text-muted-foreground">Зафиксировать возврат recovered capital инвесторам.</span>
            </span>
          </button>
        </div>

        <div class="grid gap-3 sm:grid-cols-[1fr_1fr]">
          <label class="grid gap-1.5">
            <span class="text-xs font-medium text-muted-foreground">Сумма group decision, UZS</span>
            <Input v-model="amountUzs" type="number" min="0.01" step="0.01" inputmode="decimal" />
          </label>
          <BaseSelect
            :model-value="accountId"
            :options="accountOptions"
            :title="accountTitle"
            @update:model-value="setAccount"
          />
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <Button type="button" variant="outline" :disabled="previewing || !canPreview" @click="requestPreview">
            <WalletCards data-icon="inline-start" />
            {{ previewing ? 'Проверка...' : 'Проверить policy' }}
          </Button>
          <Button type="button" :disabled="saving || !canExecute" @click="executeDecision">
            <Send data-icon="inline-start" />
            {{ saving ? 'Сохранение...' : actionLabel }}
          </Button>
        </div>

        <Alert v-if="activePreview?.blocking_reasons.length" variant="destructive">
          <AlertTriangle class="size-4" aria-hidden="true" />
          <AlertDescription>
            {{ activePreview.blocking_reasons[0] }}
          </AlertDescription>
        </Alert>

        <p v-else-if="!accountOptions.length" class="text-sm text-destructive">
          Нет активной UZS-кассы для решения.
        </p>
      </div>

      <div class="min-w-0 space-y-4">
        <div class="divide-y divide-border border-y border-border">
          <div v-for="row in rows" :key="row.key" class="grid gap-2 py-3 sm:grid-cols-[1fr_auto]">
            <div class="min-w-0">
              <p class="truncate text-sm font-medium text-foreground">#{{ row.procurementId }} · {{ row.partnerName }}</p>
              <p class="mt-0.5 text-xs text-muted-foreground">
                восстановлено {{ formatPrice(row.recoveredUzs, 'UZS') }} · выплачено {{ formatPrice(row.returnedUzs, 'UZS') }} · оставлено {{ formatPrice(row.rolledUzs, 'UZS') }}
              </p>
            </div>
            <strong class="text-sm tabular-nums text-foreground">{{ formatPrice(row.availableUzs, 'UZS') }}</strong>
          </div>
        </div>

        <div v-if="activePreview" class="space-y-3">
          <div class="flex flex-wrap items-center gap-2">
            <Badge :variant="activePreview.allowed ? 'secondary' : 'destructive'">
              {{ activePreview.allowed ? 'policy ok' : 'blocked' }}
            </Badge>
            <Badge variant="outline">{{ activePreview.trigger_mode }}</Badge>
            <Badge :variant="activePreview.interval_ready ? 'secondary' : 'outline'">interval</Badge>
            <Badge :variant="activePreview.threshold_ready ? 'secondary' : 'outline'">threshold</Badge>
          </div>

          <div class="grid gap-2">
            <div
              v-for="row in allocationRows"
              :key="allocationKey(row.procurement_id, row.partner_id)"
              class="grid items-center gap-2 rounded-lg border border-border px-3 py-2 sm:grid-cols-[minmax(0,1fr)_8rem]"
            >
              <div class="min-w-0">
                <p class="truncate text-sm font-medium text-foreground">{{ row.partner_name || `Partner #${row.partner_id}` }}</p>
                <p class="text-xs text-muted-foreground">приход #{{ row.procurement_id }} · доступно {{ formatPrice(row.available_uzs || 0, 'UZS') }}</p>
              </div>
              <Input
                v-model="allocationAmounts[allocationKey(row.procurement_id, row.partner_id)]"
                type="number"
                min="0"
                step="0.01"
                inputmode="decimal"
                class="text-right tabular-nums"
              />
            </div>
          </div>

          <p :class="allocationMismatch ? 'text-destructive' : 'text-muted-foreground'" class="text-xs tabular-nums">
            Распределено {{ formatPrice(allocationTotal, 'UZS') }} из {{ formatPrice(requestedAmount, 'UZS') }}.
          </p>
        </div>
      </div>
    </div>
  </section>
</template>
