<script setup lang="ts">
import { ref, computed, toRef } from 'vue'
import { CheckCircle2, AlertCircle, PlusCircle, Square, CheckSquare } from 'lucide-vue-next'
import PaymentMakeSheet from './PaymentMakeSheet.vue'
import PaymentScheduleEditor from './PaymentScheduleEditor.vue'
import ConsignmentObligationsBlock from './ConsignmentObligationsBlock.vue'
import PartnershipCapitalPaymentSheet from './PartnershipCapitalPaymentSheet.vue'
import CashDepositSheet from '@/modules/finance/views/CashDepositSheet.vue'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { fetchCashAccounts, type CashAccountRecord } from '@/api/finance'
import { useActiveLines } from '@/modules/intake/composables/useActiveLines'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

const props = defineProps<{
  procurement: ProcurementWorkspacePayload
  paymentError?: string | null
  lastPaymentCashAccountId?: number | null
}>()
const emit = defineEmits<{
  dispatch: [actionKey: string, payload: Record<string, unknown>]
  'retry-payment': []
}>()

const { allTotalsByCurrency, obligationItems, obligationExpenses } = useActiveLines(toRef(props, 'procurement'))

const paySheetOpen = ref(false)
const paySheetType = ref<'cost' | 'payable' | 'schedule-entry'>('cost')
const paySheetDefaultAmount = ref<string | undefined>(undefined)
const paySheetPayableId = ref<number | undefined>(undefined)
const paySheetScheduleEntryId = ref<number | undefined>(undefined)
const paySheetItemIds = ref<number[] | undefined>(undefined)
const paySheetExpenseIds = ref<number[] | undefined>(undefined)
const paySheetCurrency = ref<string | undefined>(undefined)
const scheduleEditorOpen = ref(false)
const capitalPaymentSheetOpen = ref(false)

const selectionMode = ref(false)
const selectedItemIds = ref<Set<number>>(new Set())
const selectedExpenseIds = ref<Set<number>>(new Set())

const depositSheetOpen = ref(false)
const depositAccount = ref<CashAccountRecord | null>(null)

const showTopUpHint = computed(() => {
  const err = props.paymentError
  if (!err) return false
  const lower = err.toLowerCase()
  return lower.includes('недостаточно') || lower.includes('insufficient') || lower.includes('balance')
})

async function openTopUp(): Promise<void> {
  if (!props.lastPaymentCashAccountId) return
  try {
    const accounts = await fetchCashAccounts()
    depositAccount.value = accounts.find((a) => a.id === props.lastPaymentCashAccountId) ?? null
  } catch {
    depositAccount.value = null
  }
  depositSheetOpen.value = true
}

function onDeposited(): void {
  depositSheetOpen.value = false
  emit('retry-payment')
}

const settlement = computed(() => props.procurement.documents.settlement)
const paymentStatus = computed(() => props.procurement.documents.payment_status)
const payables = computed(() => props.procurement.documents.payables)
const payments = computed(() => props.procurement.documents.payments)

const settlementType = computed(() => settlement.value?.type ?? null)
const isPartnership = computed(() => props.procurement.documents.source.funding_source === 'PARTNERSHIP')
const isPrepaid = computed(() => settlementType.value === 'PREPAID')
const isDeferred = computed(() => settlementType.value === 'DEFERRED')
const isInstallment = computed(() => settlementType.value === 'INSTALLMENT')
const isPartial = computed(() => settlementType.value === 'PARTIAL')
const isOnSale = computed(() => settlementType.value === 'ON_SALE')

// Multi-currency obligation/paid/remaining (mixed-currency procurement support).
const obligationByCurrency = computed<Record<string, string>>(() => paymentStatus.value?.obligation_by_currency ?? {})
const paidByCurrency = computed<Record<string, string>>(() => paymentStatus.value?.paid_by_currency ?? {})
const remainingByCurrency = computed<Record<string, string>>(() => paymentStatus.value?.remaining_by_currency ?? {})

const partnershipAllocatedByCurrency = computed<Record<string, number>>(() => {
  const inv = props.procurement.documents.investment
  const totals: Record<string, number> = {}
  if (!inv) return totals
  for (const allocation of inv.allocations) {
    const currency = (allocation.currency || 'UZS').toUpperCase()
    const amount = parseFloat(allocation.amount) || 0
    totals[currency] = (totals[currency] ?? 0) + (allocation.direction === 'TO_PROCUREMENT' ? amount : -amount)
  }
  return totals
})
const partnershipRemainingByCurrency = computed<Record<string, string>>(() => {
  const result: Record<string, string> = {}
  for (const [currency, amount] of Object.entries(obligationByCurrency.value)) {
    const remaining = Math.max(0, (parseFloat(amount) || 0) - (partnershipAllocatedByCurrency.value[currency] ?? 0))
    result[currency] = remaining.toFixed(2)
  }
  return result
})
const displayPaidByCurrency = computed<Record<string, string>>(() =>
  isPartnership.value
    ? Object.fromEntries(Object.entries(partnershipAllocatedByCurrency.value).map(([currency, amount]) => [currency, amount.toFixed(2)]))
    : paidByCurrency.value,
)
const displayRemainingByCurrency = computed<Record<string, string>>(() =>
  isPartnership.value ? partnershipRemainingByCurrency.value : remainingByCurrency.value,
)

const isPartnershipCovered = computed(() => {
  if (!isPartnership.value) return false
  const entries = Object.entries(obligationByCurrency.value).filter(([, amount]) => (parseFloat(amount) || 0) > 0)
  if (!entries.length) return false
  return entries.every(([currency, amount]) =>
    (partnershipAllocatedByCurrency.value[currency] ?? 0) + 0.01 >= (parseFloat(amount) || 0),
  )
})

const isFilled = computed(() => paymentStatus.value?.state === 'paid_full' || isPartnershipCovered.value)

const remainingAmount = computed(() => {
  const ps = paymentStatus.value
  if (!ps || !ps.delta) return '0'
  const delta = parseFloat(ps.delta)
  return String(Math.max(0, -(delta)))
})

function fmtMoneyMap(map: Record<string, string>): string {
  const parts = Object.entries(map)
    .filter(([, v]) => (parseFloat(v) || 0) !== 0)
    .map(([c, v]) => `${Math.round(parseFloat(v) || 0).toLocaleString('ru-RU')} ${c}`)
  return parts.length ? parts.join(' · ') : '0'
}

const firstOpenPayable = computed(() => payables.value.find((p) => p.status !== 'PAID') ?? null)

const selectionTotal = computed((): Record<string, number> => {
  const totals: Record<string, number> = {}
  for (const it of props.procurement.documents.items) {
    if (!selectedItemIds.value.has(it.id)) continue
    const cur = it.currency || 'UZS'
    const val = (parseFloat(it.quantity) || 0) * (parseFloat(it.unit_purchase_price) || 0)
    totals[cur] = (totals[cur] ?? 0) + val
  }
  for (const ex of props.procurement.documents.expenses) {
    if (!selectedExpenseIds.value.has(ex.id)) continue
    const cur = ex.currency || 'UZS'
    totals[cur] = (totals[cur] ?? 0) + (parseFloat(ex.amount) || 0)
  }
  return totals
})

const selectionCurrencies = computed(() => Object.keys(selectionTotal.value))
const selectionMixed = computed(() => selectionCurrencies.value.length > 1)
const allTotalsMixed = computed(() => Object.keys(allTotalsByCurrency.value).length > 1)
const selectionAmount = computed((): string => {
  if (selectionMixed.value || !selectionCurrencies.value.length) return ''
  const cur = selectionCurrencies.value[0]
  return String(selectionTotal.value[cur] ?? 0)
})
const singleRemainingCurrency = computed(() => {
  const currencies = Object.entries(remainingByCurrency.value)
    .filter(([, value]) => (parseFloat(value) || 0) > 0)
    .map(([currency]) => currency)
  if (!currencies.length) {
    const totalCurrencies = Object.keys(allTotalsByCurrency.value)
    return totalCurrencies.length === 1 ? totalCurrencies[0] : undefined
  }
  return currencies.length === 1 ? currencies[0] : undefined
})
const singleRemainingAmount = computed(() => {
  const currency = singleRemainingCurrency.value
  if (!currency) return remainingAmount.value
  const remaining = parseFloat(remainingByCurrency.value[currency] ?? '')
  if (Number.isFinite(remaining) && remaining > 0) return String(remaining)
  return String(allTotalsByCurrency.value[currency] ?? 0)
})

const daysUntilDeadline = computed(() => {
  const d = settlement.value?.deadline_date
  if (!d) return null
  const diff = Math.ceil((new Date(d).getTime() - Date.now()) / 86400000)
  return diff
})

function fmt(val: string): string {
  return Math.round(parseFloat(val) || 0).toLocaleString('ru-RU')
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
}

function openPayFull(): void {
  paySheetType.value = 'cost'
  paySheetDefaultAmount.value = singleRemainingAmount.value
  paySheetPayableId.value = undefined
  paySheetScheduleEntryId.value = undefined
  paySheetItemIds.value = undefined
  paySheetExpenseIds.value = undefined
  paySheetCurrency.value = singleRemainingCurrency.value
  paySheetOpen.value = true
}

function openPaySelective(): void {
  selectionMode.value = true
  selectedItemIds.value = new Set(obligationItems.value.map((it) => it.id))
  selectedExpenseIds.value = new Set(obligationExpenses.value.map((ex) => ex.id))
}

function cancelSelection(): void {
  selectionMode.value = false
}

function openPaySelected(): void {
  paySheetType.value = 'cost'
  paySheetDefaultAmount.value = selectionAmount.value || undefined
  paySheetPayableId.value = undefined
  paySheetScheduleEntryId.value = undefined
  paySheetItemIds.value = selectedItemIds.value.size ? [...selectedItemIds.value] : undefined
  paySheetExpenseIds.value = selectedExpenseIds.value.size ? [...selectedExpenseIds.value] : undefined
  paySheetCurrency.value = selectionCurrencies.value[0]
  selectionMode.value = false
  paySheetOpen.value = true
}

function toggleItem(id: number): void {
  const s = new Set(selectedItemIds.value)
  s.has(id) ? s.delete(id) : s.add(id)
  selectedItemIds.value = s
}

function toggleExpense(id: number): void {
  const s = new Set(selectedExpenseIds.value)
  s.has(id) ? s.delete(id) : s.add(id)
  selectedExpenseIds.value = s
}

function openPayPayable(): void {
  const p = firstOpenPayable.value
  paySheetType.value = 'payable'
  paySheetDefaultAmount.value = p?.remaining_amount
  paySheetPayableId.value = p?.id
  paySheetScheduleEntryId.value = undefined
  paySheetCurrency.value = p?.currency
  paySheetOpen.value = true
}

function openPayScheduleEntry(entryId: number, amount: string): void {
  const p = firstOpenPayable.value
  paySheetType.value = 'schedule-entry'
  paySheetDefaultAmount.value = amount
  paySheetPayableId.value = p?.id
  paySheetScheduleEntryId.value = entryId
  paySheetCurrency.value = p?.currency
  paySheetOpen.value = true
}

function onPaymentDispatch(actionKey: string, payload: Record<string, unknown>): void {
  emit('dispatch', actionKey, payload)
}
</script>

<template>
  <Card class="gap-0 rounded-[14px] border-neutral-200 bg-surface py-0 shadow-none">
    <CardHeader class="flex flex-row items-center justify-between gap-3 px-4 py-3.5">
      <CardTitle class="text-base">Оплата</CardTitle>
      <CheckCircle2 v-if="isFilled" class="size-[18px] text-positive" />
      <AlertCircle v-else class="size-[18px] text-warning" />
    </CardHeader>

    <CardContent class="flex flex-col gap-3 px-4 pb-4">
      <!-- Obligation summary -->
      <div v-if="paymentStatus" class="flex flex-col gap-1.5 rounded-[10px] bg-neutral-50 px-3.5 py-3">
        <div class="flex items-center justify-between gap-2">
          <span class="text-sm text-neutral-500">Обязательство</span>
          <span class="text-sm font-semibold tabular-nums text-foreground">{{ fmtMoneyMap(obligationByCurrency) }}</span>
        </div>
        <div class="flex items-center justify-between gap-2">
          <span class="text-sm text-neutral-500">{{ isPartnership ? 'Выделено' : 'Оплачено' }}</span>
          <span class="text-sm font-semibold tabular-nums text-foreground">{{ fmtMoneyMap(displayPaidByCurrency) }}</span>
        </div>
        <div v-if="!isFilled" class="flex items-center justify-between gap-2">
          <span class="text-sm text-neutral-500">Остаток</span>
          <span class="text-sm font-semibold tabular-nums text-warning">{{ fmtMoneyMap(displayRemainingByCurrency) }}</span>
        </div>
      </div>

      <!-- Insufficient balance inline hint -->
      <div v-if="showTopUpHint" class="flex flex-wrap items-center gap-2 rounded-[10px] bg-neutral-50 px-3.5 py-2.5 text-xs text-foreground">
        <AlertCircle class="size-3.5 shrink-0 text-warning" />
        <span class="min-w-0 flex-1">{{ paymentError }}</span>
        <Button variant="outline" size="sm" class="ml-auto h-8 gap-1 text-xs" @click="openTopUp">
          <PlusCircle class="size-3.5" />
          Пополнить кассу
        </Button>
      </div>

      <!-- PARTNERSHIP: pay selected costs from the agreement capital pool -->
      <template v-if="isPartnership && !isFilled">
        <Button class="h-12 w-full text-base" @click="capitalPaymentSheetOpen = true">
          Оплатить из партнёрского капитала
        </Button>
      </template>
      <div v-else-if="isPartnership && isFilled" class="text-sm font-medium text-positive">
        Оплачено из партнёрского капитала
      </div>

      <!-- ON_SALE: consignment obligations -->
      <template v-else-if="isOnSale">
        <ConsignmentObligationsBlock :procurement="procurement" @pay="openPayPayable" />
      </template>

      <!-- INSTALLMENT -->
      <template v-else-if="isInstallment">
        <template v-if="!settlement?.schedule?.length">
          <p class="text-sm font-medium text-warning">Нет графика рассрочки.</p>
          <Button variant="outline" class="h-12 w-full text-base" @click="scheduleEditorOpen = true">Сгенерировать график</Button>
        </template>
        <template v-else>
          <div class="flex flex-col gap-2">
            <div
              v-for="entry in settlement.schedule"
              :key="entry.id"
              class="flex items-center justify-between gap-2 rounded-[10px] border border-neutral-200 px-3.5 py-2.5"
            >
              <div class="flex min-w-0 flex-1 items-center gap-2">
                <span class="text-xs font-semibold text-neutral-400">{{ entry.sequence_number }}.</span>
                <span class="text-sm text-neutral-500">{{ fmtDate(entry.due_date) }}</span>
                <span class="text-sm font-semibold tabular-nums text-foreground">{{ fmt(entry.amount) }} {{ entry.currency }}</span>
              </div>
              <Button
                v-if="entry.status !== 'PAID'"
                variant="outline"
                size="sm"
                class="h-8 shrink-0 rounded-full text-xs"
                @click="openPayScheduleEntry(entry.id, entry.amount)"
              >Оплатить</Button>
              <CheckCircle2 v-else class="size-4 shrink-0 text-positive" />
            </div>
          </div>
        </template>
      </template>

      <!-- DEFERRED -->
      <template v-else-if="isDeferred">
        <div v-if="settlement?.deadline_date" class="flex items-center justify-between gap-2">
          <span class="text-sm text-neutral-500">Дедлайн</span>
          <span class="text-sm font-medium text-foreground">
            {{ fmtDate(settlement.deadline_date) }}
            <span v-if="daysUntilDeadline !== null" class="text-xs font-normal text-neutral-500">(через {{ daysUntilDeadline }} дн.)</span>
          </span>
        </div>
        <div v-if="payments.length" class="flex flex-col gap-1">
          <div
            v-for="p in payments"
            :key="p.id"
            class="flex items-center justify-between gap-2 rounded-md bg-neutral-50 px-3 py-2"
          >
            <span class="text-xs text-neutral-500">{{ fmtDate(p.paid_at) }}</span>
            <span class="text-sm font-semibold tabular-nums text-foreground">{{ fmt(p.amount) }} {{ p.currency }}</span>
          </div>
        </div>
        <Button variant="outline" class="h-12 w-full text-base" @click="openPayPayable">Совершить платёж</Button>
      </template>

      <!-- PARTIAL -->
      <template v-else-if="isPartial">
        <div v-if="settlement" class="flex flex-col gap-1.5">
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm text-neutral-500">Предоплата</span>
            <span class="text-sm font-semibold tabular-nums text-foreground">{{ fmt(settlement.paid_amount) }} {{ settlement.currency_of_obligation }}</span>
          </div>
          <div v-if="settlement.deadline_date" class="flex items-center justify-between gap-2">
            <span class="text-sm text-neutral-500">Срок долга</span>
            <span class="text-sm font-medium text-foreground">{{ fmtDate(settlement.deadline_date) }}</span>
          </div>
        </div>
        <div v-if="payments.length" class="flex flex-col gap-1">
          <div
            v-for="p in payments"
            :key="p.id"
            class="flex items-center justify-between gap-2 rounded-md bg-neutral-50 px-3 py-2"
          >
            <span class="text-xs text-neutral-500">{{ fmtDate(p.paid_at) }}</span>
            <span class="text-sm font-semibold tabular-nums text-foreground">{{ fmt(p.amount) }} {{ p.currency }}</span>
          </div>
        </div>
        <Button variant="outline" class="h-12 w-full text-base" @click="openPayFull">
          Оплатить предоплату {{ settlement ? fmt(settlement.total_amount_due) : '' }}
        </Button>
      </template>

      <!-- PREPAID (default) -->
      <template v-else-if="isPrepaid || !settlementType">
        <div v-if="payments.length" class="flex flex-col gap-1">
          <div
            v-for="p in payments"
            :key="p.id"
            class="flex items-center justify-between gap-2 rounded-md bg-neutral-50 px-3 py-2"
          >
            <span class="text-xs text-neutral-500">{{ fmtDate(p.paid_at) }}</span>
            <span class="text-sm font-semibold tabular-nums text-foreground">{{ fmt(p.amount) }} {{ p.currency }}</span>
          </div>
        </div>
        <template v-if="!isFilled">
          <!-- Selection mode -->
          <template v-if="selectionMode">
            <div class="flex flex-col gap-2">
              <p class="text-xs font-medium uppercase tracking-wide text-neutral-400">Выберите товары для оплаты</p>
              <button
                v-for="it in procurement.documents.items"
                :key="it.id"
                type="button"
                class="flex items-center gap-2 rounded-[10px] border border-neutral-200 px-3 py-2.5 text-left transition-colors hover:bg-neutral-50"
                @click="toggleItem(it.id)"
              >
                <component :is="selectedItemIds.has(it.id) ? CheckSquare : Square" :class="cn('size-[18px] shrink-0', selectedItemIds.has(it.id) ? 'text-primary' : 'text-neutral-400')" />
                <span class="min-w-0 flex-1 truncate text-sm text-foreground">{{ it.product_variant_name }}</span>
                <span class="shrink-0 text-sm font-semibold tabular-nums text-neutral-500">{{ ((parseFloat(it.quantity)||0)*(parseFloat(it.unit_purchase_price)||0)).toLocaleString('ru-RU', { maximumFractionDigits: 2 }) }} {{ it.currency }}</span>
              </button>
              <template v-if="procurement.documents.expenses.length">
                <p class="text-xs font-medium uppercase tracking-wide text-neutral-400">Расходы</p>
                <button
                  v-for="ex in procurement.documents.expenses"
                  :key="ex.id"
                  type="button"
                  class="flex items-center gap-2 rounded-[10px] border border-neutral-200 px-3 py-2.5 text-left transition-colors hover:bg-neutral-50"
                  @click="toggleExpense(ex.id)"
                >
                  <component :is="selectedExpenseIds.has(ex.id) ? CheckSquare : Square" :class="cn('size-[18px] shrink-0', selectedExpenseIds.has(ex.id) ? 'text-primary' : 'text-neutral-400')" />
                  <span class="min-w-0 flex-1 truncate text-sm text-foreground">{{ ex.expense_type }}</span>
                  <span class="shrink-0 text-sm font-semibold tabular-nums text-neutral-500">{{ (parseFloat(ex.amount)||0).toLocaleString('ru-RU', { maximumFractionDigits: 2 }) }} {{ ex.currency }}</span>
                </button>
              </template>
              <p v-if="selectionMixed" class="text-sm font-medium text-warning">Выбранные позиции в разных валютах — платите раздельно.</p>
              <Button class="h-12 w-full text-base" :disabled="(!selectedItemIds.size && !selectedExpenseIds.size) || selectionMixed" @click="openPaySelected">
                Оплатить выбранное
              </Button>
              <Button variant="ghost" class="h-10 w-full text-neutral-500" @click="cancelSelection">Отмена</Button>
            </div>
          </template>
          <template v-else>
            <div v-if="Object.keys(allTotalsByCurrency).length" class="flex flex-col gap-1.5 rounded-[10px] bg-neutral-50 px-3.5 py-3">
              <div v-for="(amt, cur) in allTotalsByCurrency" :key="cur" class="flex items-center justify-between gap-2">
                <span class="text-sm text-neutral-500">К оплате</span>
                <span class="text-sm font-semibold tabular-nums text-foreground">{{ amt.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) }} {{ cur }}</span>
              </div>
            </div>
            <p v-if="allTotalsMixed" class="text-sm font-medium text-warning">В приходе разные валюты — платите отдельными траншами.</p>
            <Button class="h-12 w-full text-base" :disabled="allTotalsMixed" @click="openPayFull">Оплатить всё</Button>
            <Button variant="ghost" class="h-10 w-full text-green-700" @click="openPaySelective">Оплатить выборочно →</Button>
          </template>
        </template>
      </template>
    </CardContent>
  </Card>

  <PaymentMakeSheet
    v-model:open="paySheetOpen"
    :procurement="procurement"
    :default-amount="paySheetDefaultAmount"
    :payment-type="paySheetType"
    :payable-id="paySheetPayableId"
    :schedule-entry-id="paySheetScheduleEntryId"
    :item-ids="paySheetItemIds"
    :expense-ids="paySheetExpenseIds"
    :currency="paySheetCurrency"
    @dispatch="onPaymentDispatch"
  />

  <PartnershipCapitalPaymentSheet
    v-model:open="capitalPaymentSheetOpen"
    :procurement="procurement"
    @dispatch="onPaymentDispatch"
  />

  <CashDepositSheet
    :open="depositSheetOpen"
    :account="depositAccount"
    @close="depositSheetOpen = false"
    @deposited="onDeposited"
  />

  <PaymentScheduleEditor
    v-if="settlement"
    v-model:open="scheduleEditorOpen"
    :total-amount="settlement.remaining_amount"
    :currency="settlement.currency_of_obligation"
    @dispatch="onPaymentDispatch"
  />
</template>
