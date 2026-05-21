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

interface CapAlloc { partnerId: number; amount: string }

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

const investment = computed(() => props.procurement.documents.investment)
const isPartnership = computed(() => props.procurement.documents.source.funding_source === 'PARTNERSHIP')
const isAtReceipt = computed(() => props.procurement.documents.settlement?.type === 'AT_RECEIPT')
const isOwnFunds = computed(() => !isPartnership.value)

const receivableItems = computed(() =>
  props.procurement.documents.items.filter(
    (it) => parseFloat(it.remaining_quantity) > 0 &&
             it.lifecycle_state !== 'RECEIVED' && it.lifecycle_state !== 'CANCELLED',
  ),
)

const totalReceived = computed(() => lines.value.reduce((s, l) => s + (parseFloat(l.qtyReceived) || 0), 0))
const totalPlanned = computed(() => receivableItems.value.reduce((s, it) => s + (parseFloat(it.remaining_quantity) || 0), 0))

const receiveBatchCostUzs = computed(() => {
  let total = 0
  for (const l of lines.value) {
    const item = receivableItems.value.find((it) => it.id === l.itemId)
    if (!item) continue
    const qty = parseFloat(l.qtyReceived) || 0
    const price = parseFloat(item.unit_purchase_price) || 0
    const fx = parseFloat(item.fx_rate) || 1
    total += qty * price * fx
  }
  return Math.round(total)
})

function prefillCapAllocs(): void {
  const inv = investment.value
  if (!inv) return
  capAllocs.value = inv.partners.map((p) => ({
    partnerId: p.partner_id,
    amount: String(Math.round(receiveBatchCostUzs.value * (parseFloat(p.planned_capital_share) || 0))),
  }))
}

function initLines(items: Item[]): void {
  lines.value = items.map((it) => ({
    itemId: it.id,
    qtyReceived: it.remaining_quantity,
    reason: 'NONE',
  }))
}

watch(() => props.open, async (isOpen) => {
  if (!isOpen) return
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
    paymentAmount.value = String(receiveBatchCostUzs.value)
  }
})

function onQtyChange(itemId: number, val: string): void {
  const l = lines.value.find((x) => x.itemId === itemId)
  if (!l) return
  l.qtyReceived = val
  const item = receivableItems.value.find((it) => it.id === itemId)
  if (item && parseFloat(val) < parseFloat(item.remaining_quantity) && l.reason === 'NONE') {
    l.reason = 'MISSING_EXPECTED_LATER'
  }
  if (isPartnership.value) prefillCapAllocs()
  if (isAtReceipt.value && isOwnFunds.value) {
    paymentAmount.value = String(receiveBatchCostUzs.value)
  }
}

function validate(): boolean {
  const errs: Record<number, string> = {}
  for (const l of lines.value) {
    const item = receivableItems.value.find((it) => it.id === l.itemId)
    if (!item) continue
    const qty = parseFloat(l.qtyReceived) || 0
    const rem = parseFloat(item.remaining_quantity) || 0
    if (qty > rem) { errs[l.itemId] = `Не более ${rem}`; continue }
    if (qty < rem && l.reason === 'NONE') errs[l.itemId] = 'Укажите причину расхождения'
  }
  errors.value = errs
  return Object.keys(errs).length === 0
}

function onSave(): void {
  if (!validate() || !warehouseId.value) return
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
    payload.capital_allocations = capAllocs.value.map((a) => ({ partner_id: a.partnerId, amount: a.amount }))
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

      <div class="section-label">Товары</div>
      <div v-for="item in receivableItems" :key="item.id" class="item-block">
        <div class="item-name">{{ item.product_variant_name }}</div>
        <div class="item-qty-row">
          <span class="qty-label">Заказано: {{ item.remaining_quantity }}</span>
          <label class="qty-input-label">
            Принято:
            <input
              class="qty-input"
              type="number"
              min="0"
              :max="item.remaining_quantity"
              step="1"
              :value="lines.find(l => l.itemId === item.id)?.qtyReceived ?? item.remaining_quantity"
              @input="onQtyChange(item.id, ($event.target as HTMLInputElement).value)"
            />
          </label>
        </div>
        <div v-if="(lines.find(l => l.itemId === item.id)?.qtyReceived ?? item.remaining_quantity) < item.remaining_quantity" class="reason-row">
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

      <!-- AT_RECEIPT OWN_FUNDS: payment block -->
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
          Сумма (UZS):
          <input
            class="input-field"
            type="number"
            min="0"
            step="1"
            :value="paymentAmount"
            @input="paymentAmount = ($event.target as HTMLInputElement).value"
          />
        </label>
        <p v-if="receiveBatchCostUzs > 0 && parseFloat(paymentAmount) < receiveBatchCostUzs" class="hint-warn">
          Сумма меньше стоимости приёмки ({{ receiveBatchCostUzs.toLocaleString('ru-RU') }} сум)
        </p>
      </template>

      <!-- PARTNERSHIP capital allocation -->
      <template v-if="isPartnership && investment">
        <div class="section-label">Распределение капитала</div>
        <div v-for="alloc in capAllocs" :key="alloc.partnerId" class="cap-row">
          <span class="cap-name">{{ investment.partners.find(p => p.partner_id === alloc.partnerId)?.partner_name ?? `#${alloc.partnerId}` }}</span>
          <input
            class="cap-input"
            type="number"
            min="0"
            :value="alloc.amount"
            @input="alloc.amount = ($event.target as HTMLInputElement).value"
          />
          <span class="cap-currency">UZS</span>
        </div>
      </template>

      <button
        class="primary-btn"
        type="button"
        :disabled="!warehouseId || !receivableItems.length || (isAtReceipt && isOwnFunds && !selectedCashAccountId)"
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
.cap-name { flex: 1; font-size: var(--text-sm); color: var(--color-text-primary); min-width: 0; }
.cap-input { width: 120px; min-height: 40px; padding: 0 var(--space-2); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); font-size: var(--text-sm); text-align: right; }
.cap-currency { font-size: var(--text-sm); color: var(--color-text-secondary); flex-shrink: 0; }
.primary-btn { min-height: 48px; border: 0; border-radius: var(--radius-lg); background: var(--color-brand-500); color: var(--color-text-inverse); font-weight: var(--font-semibold); cursor: pointer; }
.primary-btn:disabled { opacity: .55; cursor: not-allowed; }
.hint-warn { margin: 0; font-size: var(--text-xs); color: #92400E; }
</style>
