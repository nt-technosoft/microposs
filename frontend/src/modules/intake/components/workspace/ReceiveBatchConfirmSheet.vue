<script setup lang="ts">
import { ref, computed, watch, toRef } from 'vue'
import { CheckCircle2, Circle, ChevronLeft, Pencil } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import DatePickerField from '@/components/forms/DatePickerField.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { fetchLocations } from '@/api/inventory'
import { fetchCashAccounts, type CashAccountRecord } from '@/api/finance'
import { useActiveLines } from '@/modules/intake/composables/useActiveLines'
import type { Location } from '@/types/models'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

type Item = ProcurementWorkspacePayload['documents']['items'][number]

const REASONS = [
  { key: 'NONE', label: 'Без расхождения' },
  { key: 'MISSING_EXPECTED_LATER', label: 'Не привезли, ждём' },
  { key: 'DAMAGED', label: 'Повреждено' },
  { key: 'QUALITY_REJECT', label: 'Брак' },
  { key: 'ACCEPT_AS_SHORTFALL', label: 'Принять недовоз' },
] as const

type ReasonKey = typeof REASONS[number]['key']

interface LineState {
  itemId: number
  qtyReceived: string
  reason: ReasonKey
}

interface CapAlloc { partnerId: number; amount: string; currency: string; isCorrected?: boolean }
type Partner = NonNullable<ProcurementWorkspacePayload['documents']['investment']>['partners'][number]

const props = defineProps<{ open: boolean; procurement: ProcurementWorkspacePayload }>()
const emit = defineEmits<{
  'update:open': [value: boolean]
  dispatch: [actionKey: string, payload: Record<string, unknown>]
}>()

const { items: activeItems } = useActiveLines(toRef(props, 'procurement'))

const warehouseId = ref<number | null>(null)
const receivedAt = ref(new Date().toISOString().slice(0, 10))
const lines = ref<LineState[]>([])
const selectedItemIds = ref<Set<number>>(new Set())
const capAllocs = ref<CapAlloc[]>([])
const warehouses = ref<Location[]>([])
const cashAccounts = ref<CashAccountRecord[]>([])
const selectedCashAccountId = ref<number | null>(null)
const paymentAmount = ref('')
const errors = ref<Record<number, string>>({})
const sharesConfirmed = ref(false)

const investment = computed(() => props.procurement.documents.investment)
const isPartnership = computed(() => props.procurement.documents.source.funding_source === 'PARTNERSHIP')
const isAtReceipt = computed(() => props.procurement.documents.settlement?.type === 'AT_RECEIPT')
const isPrepaid = computed(() => props.procurement.documents.settlement?.type === 'PREPAID')
const isOwnFunds = computed(() => !isPartnership.value)

// ─── Wizard steps (dynamic by funding/settlement) ───
type StepKey = 'where' | 'items' | 'shares' | 'payment'
const STEP_TITLES: Record<StepKey, string> = {
  where: 'Куда и когда',
  items: 'Что приняли',
  shares: 'Доли капитала',
  payment: 'Оплата',
}
const currentStepIndex = ref(0)
// Order: goods first → money snapshot (shares / payment) → where & when last.
const steps = computed<StepKey[]>(() => {
  const s: StepKey[] = ['items']
  if (isPartnership.value) s.push('shares')
  if (isAtReceipt.value && isOwnFunds.value) s.push('payment')
  s.push('where')
  return s
})

// ─── Items step: receipt mode + per-row expand ───
const receiptMode = ref<'full' | 'partial'>('full')
const expandedItemId = ref<number | null>(null)
function orderedQty(item: Item): number {
  return Math.round(parseFloat(item.remaining_quantity) || 0)
}
function acceptedQty(item: Item): number {
  const line = lines.value.find((l) => l.itemId === item.id)
  return parseInt(line?.qtyReceived ?? item.remaining_quantity) || 0
}
const currentStep = computed<StepKey>(() => steps.value[currentStepIndex.value] ?? 'where')
const isLastStep = computed(() => currentStepIndex.value >= steps.value.length - 1)
const stepTitle = computed(() => STEP_TITLES[currentStep.value])

const allReceivableItems = computed(() =>
  activeItems.value.filter((it) => {
    if (parseFloat(it.remaining_quantity) <= 0) return false
    if (it.lifecycle_state === 'RECEIVED') return false
    if (!isPartnership.value && isPrepaid.value && it.lifecycle_state !== 'READY_FOR_RECEIVE') return false
    return true
  }),
)
const receivableItems = computed(() =>
  allReceivableItems.value.filter((it) => selectedItemIds.value.has(it.id)),
)

const blockedPrepaidItems = computed(() =>
  !isPartnership.value && isPrepaid.value
    ? activeItems.value.filter(
        (it) => it.lifecycle_state !== 'READY_FOR_RECEIVE' && it.lifecycle_state !== 'RECEIVED',
      )
    : [],
)

const totalReceived = computed(() =>
  lines.value.reduce((s, l) => selectedItemIds.value.has(l.itemId) ? s + (parseFloat(l.qtyReceived) || 0) : s, 0),
)
const totalPlanned = computed(() => receivableItems.value.reduce((s, it) => s + (parseFloat(it.remaining_quantity) || 0), 0))

const receiveBatchCostByCurrency = computed((): Record<string, number> => {
  const totals: Record<string, number> = {}
  for (const l of lines.value) {
    const item = receivableItems.value.find((it) => it.id === l.itemId)
    if (!item) continue
    const qty = parseInt(l.qtyReceived) || 0
    const price = parseFloat(item.unit_purchase_price) || 0
    const cur = item.currency || 'UZS'
    totals[cur] = (totals[cur] ?? 0) + qty * price
  }
  return totals
})

const batchObligationCurrency = computed((): string => {
  const currencies = Object.keys(receiveBatchCostByCurrency.value)
  return currencies[0] ?? (props.procurement.documents.payment_status?.currency ?? 'UZS')
})

const batchObligationTotal = computed((): number =>
  receiveBatchCostByCurrency.value[batchObligationCurrency.value] ?? 0,
)
const capitalAllocatedTotal = computed(() =>
  capAllocs.value.reduce((sum, row) => sum + (parseFloat(row.amount) || 0), 0),
)
const capitalShortfall = computed(() =>
  Math.max(0, Number((batchObligationTotal.value - capitalAllocatedTotal.value).toFixed(2))),
)
const receiveMixedCurrency = computed(() =>
  Object.keys(receiveBatchCostByCurrency.value).filter((currency) => receiveBatchCostByCurrency.value[currency] > 0).length > 1,
)

function prefillCapAllocs(): void {
  const inv = investment.value
  if (!inv) return
  const total = batchObligationTotal.value
  const currency = batchObligationCurrency.value
  capAllocs.value = distributeCapital(total, inv.partners, currency)
}

function partnerWeight(partner: Partner): number {
  const planned = parseFloat(partner.planned_capital_share)
  if (planned > 0) return planned
  const profit = parseFloat(partner.profit_share)
  return profit > 0 ? profit : 1
}

function receiveAvailable(partnerId: number, currency: string): number {
  const inv = investment.value
  if (!inv) return 0
  let available = 0
  for (const allocation of inv.allocations) {
    if (allocation.partner_id !== partnerId || allocation.currency !== currency) continue
    const amount = parseFloat(allocation.amount) || 0
    available += allocation.direction === 'TO_PROCUREMENT' ? amount : -amount
  }
  for (const batch of props.procurement.documents.receive_batches) {
    const snapshot = batch.capital_snapshot as { partners?: Array<{ partner_id: number; capital_amount_contract_currency?: string }> } | null
    for (const partner of snapshot?.partners ?? []) {
      if (partner.partner_id === partnerId) available -= parseFloat(partner.capital_amount_contract_currency ?? '0') || 0
    }
  }
  return Math.max(0, available)
}

function distributeCapital(total: number, partners: Partner[], currency: string): CapAlloc[] {
  const weightTotal = partners.reduce((sum, p) => sum + partnerWeight(p), 0) || partners.length || 1
  const rows = partners.map((p) => {
    const contractedAmount = total * partnerWeight(p) / weightTotal
    const available = receiveAvailable(p.partner_id, currency)
    const amount = Math.min(contractedAmount, available)
    return {
      partnerId: p.partner_id,
      amount: amount.toFixed(2),
      currency,
      isCorrected: amount < contractedAmount - 0.001,
    }
  })
  let remaining = Number((total - rows.reduce((sum, row) => sum + (parseFloat(row.amount) || 0), 0)).toFixed(2))
  for (const row of rows) {
    if (remaining <= 0) break
    const headroom = Math.max(0, receiveAvailable(row.partnerId, currency) - (parseFloat(row.amount) || 0))
    const topUp = Math.min(headroom, remaining)
    row.amount = ((parseFloat(row.amount) || 0) + topUp).toFixed(2)
    remaining = Number((remaining - topUp).toFixed(2))
  }
  return rows
}

function redistributeCapital(changedPartnerId: number, rawValue: string): void {
  const inv = investment.value
  if (!inv) return
  const currency = batchObligationCurrency.value
  const changed = Math.min(Math.max(parseFloat(rawValue) || 0, 0), receiveAvailable(changedPartnerId, currency))
  const otherPartners = inv.partners.filter((p) => p.partner_id !== changedPartnerId)
  const remainder = Math.max(0, batchObligationTotal.value - changed)
  capAllocs.value = [
    {
      partnerId: changedPartnerId,
      amount: changed.toFixed(2),
      currency,
      isCorrected: changed + 0.001 >= receiveAvailable(changedPartnerId, currency),
    },
    ...distributeCapital(remainder, otherPartners, currency),
  ].sort((a, b) => {
    const aIndex = inv.partners.findIndex((p) => p.partner_id === a.partnerId)
    const bIndex = inv.partners.findIndex((p) => p.partner_id === b.partnerId)
    return aIndex - bIndex
  })
}

function intQty(val: string | number): string {
  return String(Math.round(parseFloat(String(val)) || 0))
}

function initLines(items: Item[]): void {
  lines.value = items.map((it) => ({
    itemId: it.id,
    qtyReceived: intQty(it.remaining_quantity),
    reason: 'NONE',
  }))
}

watch(() => props.open, async (isOpen) => {
  if (!isOpen) return
  currentStepIndex.value = 0
  receiptMode.value = 'full'
  expandedItemId.value = null
  sharesConfirmed.value = false
  receivedAt.value = new Date().toISOString().slice(0, 10)
  errors.value = {}
  selectedItemIds.value = new Set(allReceivableItems.value.map((it) => it.id))
  initLines(allReceivableItems.value)
  if (isPartnership.value) prefillCapAllocs()
  if (!warehouses.value.length) {
    try { warehouses.value = await fetchLocations() } catch { warehouses.value = [] }
  }
  if (!warehouseId.value && warehouses.value.length) {
    warehouseId.value = warehouses.value[0].id
  }
  if (isAtReceipt.value && isOwnFunds.value) {
    if (!cashAccounts.value.length) {
      try { cashAccounts.value = await fetchCashAccounts() } catch { cashAccounts.value = [] }
    }
    if (!selectedCashAccountId.value && cashAccounts.value.length) {
      selectedCashAccountId.value = cashAccounts.value[0].id
    }
    paymentAmount.value = batchObligationTotal.value.toFixed(2)
  }
})

function onQtyChange(itemId: number, val: string): void {
  const l = lines.value.find((x) => x.itemId === itemId)
  if (!l) return
  l.qtyReceived = intQty(val)
  const item = receivableItems.value.find((it) => it.id === itemId)
  if (item && parseInt(l.qtyReceived) < Math.round(parseFloat(item.remaining_quantity)) && l.reason === 'NONE') {
    l.reason = 'MISSING_EXPECTED_LATER'
  }
  if (isPartnership.value) prefillCapAllocs()
  if (isAtReceipt.value && isOwnFunds.value) {
    paymentAmount.value = batchObligationTotal.value.toFixed(2)
  }
}

function validate(): boolean {
  const errs: Record<number, string> = {}
  for (const l of lines.value) {
    if (!selectedItemIds.value.has(l.itemId)) continue
    const item = receivableItems.value.find((it) => it.id === l.itemId)
    if (!item) continue
    const qty = parseInt(l.qtyReceived) || 0
    const rem = Math.round(parseFloat(item.remaining_quantity) || 0)
    if (qty > rem) { errs[l.itemId] = `Не более ${rem}`; continue }
    if (qty < rem && l.reason === 'NONE') errs[l.itemId] = 'Укажите причину расхождения'
  }
  errors.value = errs
  return Object.keys(errs).length === 0
}

function toggleItemSelection(itemId: number): void {
  const next = new Set(selectedItemIds.value)
  next.has(itemId) ? next.delete(itemId) : next.add(itemId)
  selectedItemIds.value = next
  if (isPartnership.value) prefillCapAllocs()
  if (isAtReceipt.value && isOwnFunds.value) {
    paymentAmount.value = batchObligationTotal.value.toFixed(2)
  }
}

function onSave(): void {
  if (!validate() || !warehouseId.value) return
  if (isPartnership.value && !sharesConfirmed.value) return
  if (isAtReceipt.value && isOwnFunds.value && !selectedCashAccountId.value) return
  const itemDiscrepancies: Record<string, { qty_received: string; discrepancy_reason: string }> = {}
  for (const l of lines.value) {
    if (!selectedItemIds.value.has(l.itemId)) continue
    itemDiscrepancies[String(l.itemId)] = { qty_received: l.qtyReceived, discrepancy_reason: l.reason }
  }
  const payload: Record<string, unknown> = {
    warehouse_id: warehouseId.value,
    received_at: receivedAt.value,
    item_ids: [...selectedItemIds.value],
    item_discrepancies: itemDiscrepancies,
  }
  if (isPartnership.value && capAllocs.value.length) {
    payload.capital_allocations = capAllocs.value.map((a) => ({ partner_id: a.partnerId, amount: a.amount, currency: a.currency }))
  }
  if (isAtReceipt.value && isOwnFunds.value) {
    const acct = cashAccounts.value.find((a) => a.id === selectedCashAccountId.value)
    payload.payment_payload = {
      cash_account_id: selectedCashAccountId.value,
      amount: paymentAmount.value,
      currency: acct?.currency ?? 'UZS',
    }
  }
  emit('dispatch', 'RECEIVE_BATCH', payload)
  emit('update:open', false)
}

// ─── Wizard navigation ───
const canProceed = computed(() => {
  switch (currentStep.value) {
    case 'where': return !!warehouseId.value
    case 'items': return receivableItems.value.length > 0 && !receiveMixedCurrency.value
    case 'shares': return !receiveMixedCurrency.value && capitalShortfall.value <= 0
    case 'payment': return !!selectedCashAccountId.value && parseFloat(paymentAmount.value) > 0
    default: return true
  }
})

function goNext(): void {
  if (!canProceed.value) return
  if (currentStep.value === 'items' && !validate()) return
  if (currentStep.value === 'shares') sharesConfirmed.value = true
  if (isLastStep.value) { onSave(); return }
  currentStepIndex.value += 1
}

function goBack(): void {
  if (currentStepIndex.value <= 0) { emit('update:open', false); return }
  currentStepIndex.value -= 1
  if (currentStep.value === 'shares') sharesConfirmed.value = false
}

function setReceiptMode(mode: 'full' | 'partial'): void {
  receiptMode.value = mode
  expandedItemId.value = null
  errors.value = {}
  if (mode === 'full') {
    // Full receipt: every item in, full ordered quantity, no discrepancy.
    selectedItemIds.value = new Set(allReceivableItems.value.map((it) => it.id))
    initLines(allReceivableItems.value)
  }
}
</script>

<template>
  <AppBottomSheet :open="open" :title="isAtReceipt ? 'Принять и оплатить' : 'Приёмка товара'" @close="emit('update:open', false)">
    <div class="flex flex-col gap-4">
      <!-- Progress -->
      <div class="flex items-center justify-between gap-3">
        <span class="text-sm font-semibold text-foreground">{{ stepTitle }}</span>
        <div class="flex items-center gap-2">
          <div class="flex items-center gap-1">
            <span
              v-for="(s, i) in steps"
              :key="s"
              :class="cn('h-1.5 rounded-full transition-all', i === currentStepIndex ? 'w-5 bg-green-600' : i < currentStepIndex ? 'w-1.5 bg-green-400' : 'w-1.5 bg-neutral-200')"
            />
          </div>
          <span class="text-xs tabular-nums text-neutral-400">{{ currentStepIndex + 1 }}/{{ steps.length }}</span>
        </div>
      </div>

      <!-- STEP: where -->
      <template v-if="currentStep === 'where'">
        <div class="flex flex-col gap-1.5">
          <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Склад</span>
          <Select
            :model-value="warehouseId != null ? String(warehouseId) : undefined"
            @update:model-value="(v) => (warehouseId = v ? Number(v) : null)"
          >
            <SelectTrigger class="h-11! w-full justify-between rounded-[10px] border-neutral-200 px-3 text-sm">
              <SelectValue placeholder="Выберите склад" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="w in warehouses" :key="w.id" :value="String(w.id)" class="py-2.5">{{ w.name }}</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="flex flex-col gap-1.5">
          <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Дата приёмки</span>
          <DatePickerField v-model="receivedAt" />
        </div>
      </template>

      <!-- STEP: items -->
      <template v-else-if="currentStep === 'items'">
        <p v-if="allReceivableItems.length === 0" class="text-sm text-neutral-500">
          Нет позиций для приёмки.{{ isPrepaid ? ' Сначала оплатите товары.' : '' }}
        </p>

        <template v-else>
          <!-- Mode: full (one-tap) vs partial (per-item) -->
          <div class="flex rounded-[10px] bg-neutral-100 p-1">
            <button
              type="button"
              :class="cn('flex-1 rounded-[8px] py-1.5 text-sm transition-colors', receiptMode === 'full' ? 'bg-surface font-medium text-foreground shadow-sm' : 'text-neutral-500')"
              @click="setReceiptMode('full')"
            >Полная приёмка</button>
            <button
              type="button"
              :class="cn('flex-1 rounded-[8px] py-1.5 text-sm transition-colors', receiptMode === 'partial' ? 'bg-surface font-medium text-foreground shadow-sm' : 'text-neutral-500')"
              @click="setReceiptMode('partial')"
            >Частичная</button>
          </div>

          <!-- FULL: compact read-only confirmation -->
          <template v-if="receiptMode === 'full'">
            <p class="text-xs leading-relaxed text-neutral-500">
              Все {{ allReceivableItems.length }} {{ allReceivableItems.length === 1 ? 'позиция принимается' : 'позиции принимаются' }} полностью. Для недовоза или брака переключите на «Частичная».
            </p>
            <div class="flex flex-col">
              <div
                v-for="item in allReceivableItems"
                :key="item.id"
                class="flex items-center gap-2.5 border-b border-neutral-100 py-2 last:border-0"
              >
                <CheckCircle2 class="size-4 shrink-0 text-primary" />
                <span class="min-w-0 flex-1 truncate text-sm text-foreground">{{ item.product_variant_name }}</span>
                <span class="shrink-0 text-sm font-medium tabular-nums text-foreground">{{ orderedQty(item) }} шт</span>
              </div>
            </div>
          </template>

          <!-- PARTIAL: per-item, compact by default, fields on explicit edit -->
          <div v-else class="flex flex-col gap-1.5">
            <div
              v-for="item in allReceivableItems"
              :key="item.id"
              :class="cn('rounded-[10px] border transition-colors', selectedItemIds.has(item.id) ? 'border-primary' : 'border-neutral-100 bg-neutral-50')"
            >
              <div role="button" class="flex cursor-pointer items-center gap-2 px-2.5 py-2" @click="toggleItemSelection(item.id)">
                <component :is="selectedItemIds.has(item.id) ? CheckCircle2 : Circle" :class="cn('size-5 shrink-0', selectedItemIds.has(item.id) ? 'text-primary' : 'text-neutral-300')" />
                <span :class="cn('min-w-0 flex-1 truncate text-sm', selectedItemIds.has(item.id) ? 'text-foreground' : 'text-neutral-400 line-through')">{{ item.product_variant_name }}</span>
                <template v-if="selectedItemIds.has(item.id)">
                  <span :class="cn('shrink-0 text-sm tabular-nums', acceptedQty(item) < orderedQty(item) ? 'font-medium text-warning' : 'text-neutral-600')">
                    {{ acceptedQty(item) }}<span v-if="acceptedQty(item) < orderedQty(item)" class="text-neutral-400">/{{ orderedQty(item) }}</span> шт
                  </span>
                  <button
                    type="button"
                    :class="cn('flex size-7 shrink-0 items-center justify-center rounded-md transition-colors', expandedItemId === item.id ? 'bg-primary/10 text-primary' : 'text-neutral-400 hover:bg-neutral-100 hover:text-neutral-600')"
                    aria-label="Изменить количество"
                    @click.stop="expandedItemId = expandedItemId === item.id ? null : item.id"
                  >
                    <Pencil class="size-3.5" />
                  </button>
                </template>
              </div>
              <div v-if="selectedItemIds.has(item.id) && expandedItemId === item.id" class="flex flex-col gap-2 border-t border-neutral-100 px-2.5 py-2.5" @click.stop>
                <div class="flex items-center justify-between gap-3">
                  <span class="text-xs text-neutral-500">Заказано {{ orderedQty(item) }}</span>
                  <div class="flex items-center gap-2">
                    <span class="text-xs text-neutral-500">Принято</span>
                    <input
                      class="h-9 w-20 rounded-[8px] border border-neutral-200 bg-surface px-2 text-right text-sm tabular-nums outline-none focus:border-green-500 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                      type="number"
                      min="0"
                      :max="orderedQty(item)"
                      step="1"
                      :value="lines.find(l => l.itemId === item.id)?.qtyReceived ?? intQty(item.remaining_quantity)"
                      @input="onQtyChange(item.id, ($event.target as HTMLInputElement).value)"
                    />
                  </div>
                </div>
                <Select
                  v-if="acceptedQty(item) < orderedQty(item)"
                  :model-value="lines.find(l => l.itemId === item.id)?.reason ?? 'NONE'"
                  @update:model-value="(v) => { const l = lines.find(x => x.itemId === item.id); if (l) l.reason = v as ReasonKey }"
                >
                  <SelectTrigger class="h-10! w-full justify-between rounded-[8px] border-neutral-200 px-2.5 text-sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem v-for="r in REASONS" :key="r.key" :value="r.key" class="py-2.5">{{ r.label }}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <p v-if="errors[item.id]" class="px-2.5 pb-2 text-xs text-negative">{{ errors[item.id] }}</p>
            </div>
          </div>
        </template>

        <template v-if="blockedPrepaidItems.length">
          <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Ожидают оплаты</span>
          <div class="flex flex-col gap-1.5">
            <div v-for="item in blockedPrepaidItems" :key="item.id" class="flex items-center justify-between rounded-[10px] bg-warning/10 px-3.5 py-2.5">
              <span class="text-sm text-neutral-600">{{ item.product_variant_name }}</span>
              <span class="text-sm tabular-nums text-neutral-500">{{ item.quantity }} шт</span>
            </div>
          </div>
        </template>

        <p v-if="receiveMixedCurrency" class="rounded-[10px] border border-warning/30 bg-warning/10 px-3.5 py-2.5 text-sm text-foreground">
          В выбранной приёмке разные валюты. Разделите приёмку на отдельные партии.
        </p>
      </template>

      <!-- STEP: shares (partnership) -->
      <template v-else-if="currentStep === 'shares' && investment">
        <p class="text-xs leading-relaxed text-neutral-500">
          Доли участников в этой партии. Предзаполнено из плановых долей; можно скорректировать в пределах доступного капитала. Фиксируется при приёмке.
        </p>
        <div class="flex items-center justify-between rounded-[10px] bg-neutral-50 px-3.5 py-3">
          <span class="text-sm text-neutral-500">Стоимость приёмки</span>
          <span class="text-sm font-semibold tabular-nums text-foreground">{{ batchObligationTotal.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) }} {{ batchObligationCurrency }}</span>
        </div>
        <div class="flex flex-col gap-2.5">
          <div v-for="alloc in capAllocs" :key="alloc.partnerId" class="grid grid-cols-[minmax(0,1fr)_120px_auto] items-center gap-2">
            <div class="min-w-0">
              <span class="block truncate text-sm text-foreground">{{ investment.partners.find(p => p.partner_id === alloc.partnerId)?.partner_name ?? ('#' + alloc.partnerId) }}</span>
              <small v-if="alloc.isCorrected" class="text-xs text-warning">↓ по доступному</small>
            </div>
            <input
              class="h-10 w-full rounded-[8px] border border-neutral-200 bg-surface px-2 text-right text-sm tabular-nums outline-none focus:border-green-500"
              type="number"
              min="0"
              step="0.01"
              :value="alloc.amount"
              @input="redistributeCapital(alloc.partnerId, ($event.target as HTMLInputElement).value)"
            />
            <span class="text-sm text-neutral-500">{{ alloc.currency }}</span>
          </div>
        </div>
        <div v-if="capitalShortfall > 0" class="rounded-[10px] border border-warning/30 bg-warning/10 px-3.5 py-2.5 text-sm text-foreground">
          Не хватает капитала: {{ capitalShortfall.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) }} {{ batchObligationCurrency }}. Пополните капитал договора.
        </div>
      </template>

      <!-- STEP: payment (own funds AT_RECEIPT) -->
      <template v-else-if="currentStep === 'payment'">
        <div class="flex flex-col gap-1.5">
          <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Касса</span>
          <Select
            :model-value="selectedCashAccountId != null ? String(selectedCashAccountId) : undefined"
            @update:model-value="(v) => (selectedCashAccountId = v ? Number(v) : null)"
          >
            <SelectTrigger class="h-11! w-full justify-between rounded-[10px] border-neutral-200 px-3 text-sm">
              <SelectValue :placeholder="cashAccounts.length ? 'Выберите кассу' : 'Загрузка…'" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="a in cashAccounts" :key="a.id" :value="String(a.id)" class="py-2.5">
                {{ a.name }} · {{ parseFloat(a.balance).toLocaleString('ru-RU') }} {{ a.currency }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="flex flex-col gap-1.5">
          <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Сумма ({{ batchObligationCurrency }})</span>
          <Input v-model="paymentAmount" type="number" min="0" step="0.01" class="h-11 tabular-nums [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none" />
          <p v-if="batchObligationTotal > 0 && parseFloat(paymentAmount) < batchObligationTotal" class="text-xs text-warning">
            Меньше стоимости приёмки ({{ batchObligationTotal.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) }} {{ batchObligationCurrency }})
          </p>
        </div>
      </template>

      <!-- Footer nav -->
      <div class="flex items-center gap-2 pt-2">
        <Button variant="outline" class="h-12 flex-1" @click="goBack">
          <ChevronLeft class="mr-1 size-4" />{{ currentStepIndex === 0 ? 'Отмена' : 'Назад' }}
        </Button>
        <Button class="h-12 flex-[2] text-base" :disabled="!canProceed" @click="goNext">
          {{ isLastStep ? (isAtReceipt && isOwnFunds ? 'Принять и оплатить' : 'Принять — ' + Math.round(totalReceived) + '/' + Math.round(totalPlanned)) : 'Далее' }}
        </Button>
      </div>
    </div>
  </AppBottomSheet>
</template>
