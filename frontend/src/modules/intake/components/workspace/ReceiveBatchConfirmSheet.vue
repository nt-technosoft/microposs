<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { fetchLocations } from '@/api/inventory'
import { fetchCashAccounts, type CashAccountRecord } from '@/api/finance'
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

const props = defineProps<{ open: boolean; procurement: ProcurementWorkspacePayload }>()
const emit = defineEmits<{
  'update:open': [value: boolean]
  dispatch: [actionKey: string, payload: Record<string, unknown>]
}>()

const warehouseId = ref<number | null>(null)
const receivedAt = ref(new Date().toISOString().slice(0, 10))
const lines = ref<LineState[]>([])
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

const receivableItems = computed(() =>
  props.procurement.documents.items.filter((it) => {
    if (parseFloat(it.remaining_quantity) <= 0) return false
    if (it.lifecycle_state === 'RECEIVED' || it.lifecycle_state === 'CANCELLED') return false
    if (isPrepaid.value && it.lifecycle_state !== 'READY_FOR_RECEIVE') return false
    return true
  }),
)

const blockedPrepaidItems = computed(() =>
  isPrepaid.value
    ? props.procurement.documents.items.filter(
        (it) => it.lifecycle_state !== 'READY_FOR_RECEIVE' &&
                 it.lifecycle_state !== 'RECEIVED' &&
                 it.lifecycle_state !== 'CANCELLED',
      )
    : [],
)

const totalReceived = computed(() => lines.value.reduce((s, l) => s + (parseFloat(l.qtyReceived) || 0), 0))
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

function prefillCapAllocs(): void {
  const inv = investment.value
  if (!inv) return
  const total = batchObligationTotal.value
  const currency = batchObligationCurrency.value
  capAllocs.value = inv.partners.map((p) => {
    const contractedAmount = total * (parseFloat(p.profit_share) || 0)
    const availableStr = inv.available_by_partner[String(p.partner_id)]?.[currency] ?? '0'
    const available = parseFloat(availableStr) || 0
    const amount = Math.min(contractedAmount, available)
    return {
      partnerId: p.partner_id,
      amount: amount.toFixed(2),
      currency,
      isCorrected: amount < contractedAmount - 0.001,
    }
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
  sharesConfirmed.value = false
  receivedAt.value = new Date().toISOString().slice(0, 10)
  errors.value = {}
  initLines(receivableItems.value)
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

function onSave(): void {
  if (!validate() || !warehouseId.value) return
  if (isPartnership.value && !sharesConfirmed.value) return
  if (isAtReceipt.value && isOwnFunds.value && !selectedCashAccountId.value) return
  const itemDiscrepancies: Record<string, { qty_received: string; discrepancy_reason: string }> = {}
  for (const l of lines.value) {
    itemDiscrepancies[String(l.itemId)] = { qty_received: l.qtyReceived, discrepancy_reason: l.reason }
  }
  const payload: Record<string, unknown> = {
    warehouse_id: warehouseId.value,
    received_at: receivedAt.value,
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
</script>

<template>
  <AppBottomSheet :open="open" :title="isAtReceipt ? 'Принять и оплатить' : 'Приёмка товара'" @close="emit('update:open', false)">
    <div class="sheet-body">
      <div class="section-label">Склад</div>
      <select class="select-field" :value="warehouseId" @change="warehouseId = Number(($event.target as HTMLSelectElement).value)">
        <option v-for="w in warehouses" :key="w.id" :value="w.id">{{ w.name }}</option>
      </select>

      <div class="section-label">Дата приёмки</div>
      <input class="input-field" type="date" v-model="receivedAt" />

      <div v-if="isAtReceipt" class="step-header">
        <span class="step-num">1</span>
        <span class="step-label">Приём товаров</span>
      </div>

      <div class="section-label">Товары к приёмке</div>
      <div v-if="receivableItems.length === 0" class="no-items-hint">
        Нет позиций для приёмки.{{ isPrepaid ? ' Сначала оплатите товары.' : '' }}
      </div>
      <div v-for="item in receivableItems" :key="item.id" class="item-block">
        <div class="item-name">{{ item.product_variant_name }}</div>
        <div class="item-qty-row">
          <span class="qty-label">Заказано: {{ Math.round(parseFloat(item.remaining_quantity)) }}</span>
          <label class="qty-input-label">
            Принято:
            <input
              class="qty-input"
              type="number"
              min="0"
              :max="Math.round(parseFloat(item.remaining_quantity))"
              step="1"
              :value="lines.find(l => l.itemId === item.id)?.qtyReceived ?? intQty(item.remaining_quantity)"
              @input="onQtyChange(item.id, ($event.target as HTMLInputElement).value)"
            />
          </label>
        </div>
        <div v-if="parseInt(lines.find(l => l.itemId === item.id)?.qtyReceived ?? item.remaining_quantity) < Math.round(parseFloat(item.remaining_quantity))" class="reason-row">
          <select
            class="select-field"
            :value="lines.find(l => l.itemId === item.id)?.reason ?? 'NONE'"
            @change="(e) => { const l = lines.find(x => x.itemId === item.id); if (l) l.reason = (e.target as HTMLSelectElement).value as ReasonKey }"
          >
            <option v-for="r in REASONS" :key="r.key" :value="r.key">{{ r.label }}</option>
          </select>
        </div>
        <div v-if="errors[item.id]" class="error-text">{{ errors[item.id] }}</div>
      </div>

      <!-- PREPAID: blocked items notice -->
      <template v-if="blockedPrepaidItems.length">
        <div class="section-label">Ожидают оплаты</div>
        <div v-for="item in blockedPrepaidItems" :key="item.id" class="blocked-item-row">
          <span class="blocked-item-name">{{ item.product_variant_name }}</span>
          <span class="blocked-item-qty">{{ item.quantity }} шт.</span>
        </div>
      </template>

      <!-- AT_RECEIPT OWN_FUNDS: payment block -->
      <div v-if="isAtReceipt" class="step-header">
        <span class="step-num">2</span>
        <span class="step-label">Оплата</span>
      </div>

      <template v-if="isAtReceipt && isOwnFunds">
        <div class="section-label">Оплата при получении</div>
        <select
          class="select-field"
          :value="selectedCashAccountId"
          @change="selectedCashAccountId = Number(($event.target as HTMLSelectElement).value)"
        >
          <option v-if="!cashAccounts.length" :value="null">Загрузка…</option>
          <option v-for="a in cashAccounts" :key="a.id" :value="a.id">
            {{ a.name }} · {{ parseFloat(a.balance).toLocaleString('ru-RU') }} {{ a.currency }}
          </option>
        </select>
        <label class="qty-input-label">
          Сумма ({{ batchObligationCurrency }}):
          <input
            class="input-field"
            type="number"
            min="0"
            step="0.01"
            :value="paymentAmount"
            @input="paymentAmount = ($event.target as HTMLInputElement).value"
          />
        </label>
        <p v-if="batchObligationTotal > 0 && parseFloat(paymentAmount) < batchObligationTotal" class="hint-warn">
          Сумма меньше стоимости приёмки ({{ batchObligationTotal.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) }} {{ batchObligationCurrency }})
        </p>
      </template>

      <!-- PARTNERSHIP capital allocation -->
      <template v-if="isPartnership && investment">
        <div class="shares-header">
          <div class="section-label">Распределение по партнёрам ({{ batchObligationCurrency }})</div>
          <button v-if="sharesConfirmed" class="edit-shares-btn" type="button" @click="sharesConfirmed = false">Изменить</button>
        </div>
        <div v-for="alloc in capAllocs" :key="alloc.partnerId" class="cap-row">
          <span class="cap-name" :class="{ 'cap-corrected': alloc.isCorrected }">
            {{ investment.partners.find(p => p.partner_id === alloc.partnerId)?.partner_name ?? `#${alloc.partnerId}` }}
            <span v-if="alloc.isCorrected" class="cap-correction-hint">↓ лимит</span>
          </span>
          <template v-if="sharesConfirmed">
            <span class="cap-confirmed-amount">{{ parseFloat(alloc.amount).toLocaleString('ru-RU', { maximumFractionDigits: 2 }) }}</span>
          </template>
          <template v-else>
            <input
              class="cap-input"
              type="number"
              min="0"
              step="0.01"
              :value="alloc.amount"
              @input="alloc.amount = ($event.target as HTMLInputElement).value"
            />
          </template>
          <span class="cap-currency">{{ alloc.currency }}</span>
        </div>
        <button v-if="!sharesConfirmed" class="confirm-shares-btn" type="button" @click="sharesConfirmed = true">
          Подтвердить доли
        </button>
      </template>

      <button
        class="primary-btn"
        type="button"
        :disabled="!warehouseId || !receivableItems.length || (isAtReceipt && isOwnFunds && !selectedCashAccountId) || (isPartnership && !sharesConfirmed)"
        @click="onSave"
      >
        {{ isAtReceipt ? 'Принять и оплатить' : 'Принять' }}
        ({{ Math.round(totalReceived) }} из {{ Math.round(totalPlanned) }})
      </button>
    </div>
  </AppBottomSheet>
</template>

<style scoped>
.sheet-body { display: grid; gap: var(--space-3); }
.section-label { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: .04em; }
.select-field { width: 100%; min-height: 44px; padding: 0 var(--space-3); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); font-size: var(--text-sm); appearance: auto; }
.input-field { width: 100%; min-height: 44px; padding: 0 var(--space-3); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); font-size: var(--text-sm); }
.item-block { display: grid; gap: var(--space-2); padding: var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); }
.item-name { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.item-qty-row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); flex-wrap: wrap; }
.qty-label { font-size: var(--text-sm); color: var(--color-text-secondary); }
.qty-input-label { display: flex; align-items: center; gap: var(--space-2); font-size: var(--text-sm); color: var(--color-text-secondary); }
.qty-input { width: 80px; min-height: 36px; padding: 0 var(--space-2); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); font-size: var(--text-sm); text-align: right; }
.reason-row { margin-top: 2px; }
.error-text { font-size: var(--text-xs); color: var(--color-error); }
.cap-row { display: flex; align-items: center; gap: var(--space-2); }
.cap-name { flex: 1; font-size: var(--text-sm); color: var(--color-text-primary); min-width: 0; display: flex; align-items: center; gap: var(--space-1); }
.cap-corrected { color: var(--color-warning); }
.cap-correction-hint { font-size: var(--text-xs); color: var(--color-warning); }
.cap-input { width: 120px; min-height: 40px; padding: 0 var(--space-2); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); font-size: var(--text-sm); text-align: right; }
.cap-currency { font-size: var(--text-sm); color: var(--color-text-secondary); flex-shrink: 0; }
.primary-btn { min-height: 48px; border: 0; border-radius: var(--radius-lg); background: var(--color-brand-500); color: var(--color-text-inverse); font-weight: var(--font-semibold); cursor: pointer; }
.primary-btn:disabled { opacity: .55; cursor: not-allowed; }
.hint-warn { margin: 0; font-size: var(--text-xs); color: var(--color-warning); }
.step-header { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-2) 0; border-top: 1px solid var(--color-border-subtle); margin-top: var(--space-1); }
.step-num { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: var(--radius-full); background: var(--color-brand-500); color: white; font-size: var(--text-xs); font-weight: var(--font-semibold); flex-shrink: 0; }
.step-label { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.no-items-hint { font-size: var(--text-sm); color: var(--color-text-secondary); padding: var(--space-2) 0; }
.blocked-item-row { display: flex; align-items: center; justify-content: space-between; padding: var(--space-2) var(--space-3); background: color-mix(in srgb, var(--color-warning) 8%, transparent); border-radius: var(--radius-md); }
.blocked-item-name { font-size: var(--text-sm); color: var(--color-text-secondary); }
.blocked-item-qty { font-size: var(--text-sm); color: var(--color-text-tertiary); font-variant-numeric: tabular-nums; }
.shares-header { display: flex; align-items: center; justify-content: space-between; }
.edit-shares-btn { padding: var(--space-1) var(--space-2); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: transparent; color: var(--color-text-secondary); font-size: var(--text-xs); cursor: pointer; }
.cap-confirmed-amount { width: 120px; text-align: right; font-size: var(--text-sm); font-weight: var(--font-semibold); font-variant-numeric: tabular-nums; color: var(--color-text-primary); }
.confirm-shares-btn { display: flex; align-items: center; justify-content: center; min-height: 44px; border: 1px solid var(--color-brand-500); border-radius: var(--radius-md); background: transparent; color: var(--color-brand-700); font-size: var(--text-sm); font-weight: var(--font-semibold); cursor: pointer; }
</style>
