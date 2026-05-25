<script setup lang="ts">
import { ref, computed } from 'vue'
import { CheckCircle, AlertCircle, PlusCircle, Square, CheckSquare } from 'lucide-vue-next'
import PaymentMakeSheet from './PaymentMakeSheet.vue'
import PaymentScheduleEditor from './PaymentScheduleEditor.vue'
import ConsignmentObligationsBlock from './ConsignmentObligationsBlock.vue'
import CashDepositSheet from '@/modules/finance/views/CashDepositSheet.vue'
import { fetchCashAccounts, type CashAccountRecord } from '@/api/finance'
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

const paySheetOpen = ref(false)
const paySheetType = ref<'cost' | 'payable' | 'schedule-entry'>('cost')
const paySheetDefaultAmount = ref<string | undefined>(undefined)
const paySheetPayableId = ref<number | undefined>(undefined)
const paySheetScheduleEntryId = ref<number | undefined>(undefined)
const paySheetItemIds = ref<number[] | undefined>(undefined)
const paySheetExpenseIds = ref<number[] | undefined>(undefined)
const scheduleEditorOpen = ref(false)

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

const isFilled = computed(() => paymentStatus.value?.state === 'paid_full')

const remainingAmount = computed(() => {
  const ps = paymentStatus.value
  if (!ps) return '0'
  const delta = parseFloat(ps.delta)
  return String(Math.max(0, -(delta)))
})

const firstOpenPayable = computed(() => payables.value.find((p) => p.status !== 'PAID') ?? null)

const allTotalsByCurrency = computed((): Record<string, number> => {
  const totals: Record<string, number> = {}
  for (const it of props.procurement.documents.items) {
    if (it.lifecycle_state === 'CANCELLED' || it.lifecycle_state === 'RECEIVED') continue
    const cur = it.currency || 'UZS'
    totals[cur] = (totals[cur] ?? 0) + (parseFloat(it.quantity) || 0) * (parseFloat(it.unit_purchase_price) || 0)
  }
  for (const ex of props.procurement.documents.expenses) {
    if (ex.lifecycle_state === 'CANCELLED') continue
    const cur = ex.currency || 'UZS'
    totals[cur] = (totals[cur] ?? 0) + (parseFloat(ex.amount) || 0)
  }
  return totals
})

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
const selectionAmount = computed((): string => {
  if (selectionMixed.value || !selectionCurrencies.value.length) return ''
  const cur = selectionCurrencies.value[0]
  return String(selectionTotal.value[cur] ?? 0)
})

function allocateFromCapitalPool(): void {
  const inv = props.procurement.documents.investment
  if (!inv || !paymentStatus.value) return
  const remaining = Math.max(0, -(parseFloat(paymentStatus.value.delta) || 0))
  const currency = paymentStatus.value.currency
  const allocations = inv.partners.map((p) => ({
    partner_id: p.partner_id,
    amount: (remaining * (parseFloat(p.profit_share) || 0)).toFixed(2),
    currency,
  }))
  emit('dispatch', 'ALLOCATE_CAPITAL', { allocations })
}

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
  paySheetDefaultAmount.value = remainingAmount.value
  paySheetPayableId.value = undefined
  paySheetScheduleEntryId.value = undefined
  paySheetItemIds.value = undefined
  paySheetExpenseIds.value = undefined
  paySheetOpen.value = true
}

function openPaySelective(): void {
  selectionMode.value = true
  selectedItemIds.value = new Set(
    props.procurement.documents.items
      .filter((it) => it.lifecycle_state !== 'CANCELLED' && it.lifecycle_state !== 'RECEIVED')
      .map((it) => it.id),
  )
  selectedExpenseIds.value = new Set(
    props.procurement.documents.expenses
      .filter((ex) => ex.lifecycle_state !== 'CANCELLED')
      .map((ex) => ex.id),
  )
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
  paySheetOpen.value = true
}

function openPayScheduleEntry(entryId: number, amount: string): void {
  const p = firstOpenPayable.value
  paySheetType.value = 'schedule-entry'
  paySheetDefaultAmount.value = amount
  paySheetPayableId.value = p?.id
  paySheetScheduleEntryId.value = entryId
  paySheetOpen.value = true
}

function onPaymentDispatch(actionKey: string, payload: Record<string, unknown>): void {
  emit('dispatch', actionKey, payload)
}
</script>

<template>
  <div class="payment-card">
    <div class="card-header">
      <span class="card-title">Оплата</span>
      <CheckCircle v-if="isFilled" class="status-ok" :size="18" :stroke-width="2" />
      <AlertCircle v-else class="status-warn" :size="18" :stroke-width="2" />
    </div>

    <div v-if="paymentStatus" class="obligation-block">
      <div class="ob-row">
        <span class="ob-label">Обязательство</span>
        <span class="ob-value">{{ fmt(paymentStatus.obligation_amount) }} {{ paymentStatus.currency }}</span>
      </div>
      <div class="ob-row">
        <span class="ob-label">Оплачено</span>
        <span class="ob-value">{{ fmt(paymentStatus.paid_amount) }} {{ paymentStatus.currency }}</span>
      </div>
      <div v-if="paymentStatus.state !== 'paid_full'" class="ob-row">
        <span class="ob-label">Остаток</span>
        <span class="ob-value warn">{{ fmt(remainingAmount) }} {{ paymentStatus.currency }}</span>
      </div>
    </div>

    <!-- Insufficient balance inline hint -->
    <div v-if="showTopUpHint" class="topup-hint">
      <AlertCircle :size="14" :stroke-width="2" class="topup-icon" />
      <span>{{ paymentError }}</span>
      <button class="topup-btn" type="button" @click="openTopUp">
        <PlusCircle :size="14" :stroke-width="2" />
        Пополнить кассу
      </button>
    </div>

    <!-- PARTNERSHIP: allocate from capital pool by profit shares -->
    <template v-if="isPartnership && !isFilled">
      <button class="action-btn" type="button" @click="allocateFromCapitalPool">
        Оплатить из capital pool
      </button>
    </template>
    <div v-else-if="isPartnership && isFilled" class="available-row">✓ Оплачено из capital pool</div>

    <!-- ON_SALE: consignment obligations -->
    <template v-else-if="isOnSale">
      <ConsignmentObligationsBlock :procurement="procurement" @pay="openPayPayable" />
    </template>

    <!-- INSTALLMENT -->
    <template v-else-if="isInstallment">
      <template v-if="!settlement?.schedule?.length">
        <div class="warn-text">⚠ Нет графика рассрочки</div>
        <button class="action-btn" type="button" @click="scheduleEditorOpen = true">Сгенерировать график</button>
      </template>
      <template v-else>
        <div class="schedule-list">
          <div v-for="entry in settlement.schedule" :key="entry.id" class="schedule-row">
            <div class="schedule-meta">
              <span class="seq">{{ entry.sequence_number }}.</span>
              <span class="entry-date">{{ fmtDate(entry.due_date) }}</span>
              <span class="entry-amount">{{ fmt(entry.amount) }} {{ entry.currency }}</span>
            </div>
            <button
              v-if="entry.status !== 'PAID'"
              class="entry-pay-btn"
              type="button"
              @click="openPayScheduleEntry(entry.id, entry.amount)"
            >Оплатить</button>
            <span v-else class="entry-paid">✓</span>
          </div>
        </div>
      </template>
    </template>

    <!-- DEFERRED -->
    <template v-else-if="isDeferred">
      <div v-if="settlement?.deadline_date" class="deadline-row">
        <span class="deadline-label">Дедлайн</span>
        <span class="deadline-value">
          {{ fmtDate(settlement.deadline_date) }}
          <span v-if="daysUntilDeadline !== null" class="days-hint">(через {{ daysUntilDeadline }} дн.)</span>
        </span>
      </div>
      <div v-if="payments.length" class="history-list">
        <div v-for="p in payments" :key="p.id" class="history-row">
          <span class="hist-date">{{ fmtDate(p.paid_at) }}</span>
          <span class="hist-amount">{{ fmt(p.amount) }} {{ p.currency }}</span>
        </div>
      </div>
      <button class="action-btn" type="button" @click="openPayPayable">Совершить платёж</button>
    </template>

    <!-- PARTIAL -->
    <template v-else-if="isPartial">
      <div v-if="settlement" class="partial-info">
        <div class="ob-row">
          <span class="ob-label">Предоплата</span>
          <span class="ob-value">{{ fmt(settlement.paid_amount) }} {{ settlement.currency_of_obligation }}</span>
        </div>
        <div v-if="settlement.deadline_date" class="ob-row">
          <span class="ob-label">Срок долга</span>
          <span class="ob-value">{{ fmtDate(settlement.deadline_date) }}</span>
        </div>
      </div>
      <div v-if="payments.length" class="history-list">
        <div v-for="p in payments" :key="p.id" class="history-row">
          <span class="hist-date">{{ fmtDate(p.paid_at) }}</span>
          <span class="hist-amount">{{ fmt(p.amount) }} {{ p.currency }}</span>
        </div>
      </div>
      <button class="action-btn" type="button" @click="openPayFull">
        Оплатить предоплату {{ settlement ? fmt(settlement.total_amount_due) : '' }}
      </button>
    </template>

    <!-- PREPAID (default) -->
    <template v-else-if="isPrepaid || !settlementType">
      <div v-if="payments.length" class="history-list">
        <div v-for="p in payments" :key="p.id" class="history-row">
          <span class="hist-date">{{ fmtDate(p.paid_at) }}</span>
          <span class="hist-amount">{{ fmt(p.amount) }} {{ p.currency }}</span>
        </div>
      </div>
      <template v-if="!isFilled">
        <!-- Selection mode -->
        <template v-if="selectionMode">
          <div class="selection-section">
            <div class="selection-header">Выберите товары для оплаты</div>
            <div
              v-for="it in procurement.documents.items"
              :key="it.id"
              class="selection-row"
              role="button"
              @click="toggleItem(it.id)"
            >
              <component :is="selectedItemIds.has(it.id) ? CheckSquare : Square" :size="18" :stroke-width="2" class="sel-icon" :class="{ checked: selectedItemIds.has(it.id) }" />
              <span class="sel-name">{{ it.product_variant_name }}</span>
              <span class="sel-amount">{{ ((parseFloat(it.quantity)||0)*(parseFloat(it.unit_purchase_price)||0)).toLocaleString('ru-RU', { maximumFractionDigits: 2 }) }} {{ it.currency }}</span>
            </div>
            <template v-if="procurement.documents.expenses.length">
              <div class="selection-header">Расходы</div>
              <div
                v-for="ex in procurement.documents.expenses"
                :key="ex.id"
                class="selection-row"
                role="button"
                @click="toggleExpense(ex.id)"
              >
                <component :is="selectedExpenseIds.has(ex.id) ? CheckSquare : Square" :size="18" :stroke-width="2" class="sel-icon" :class="{ checked: selectedExpenseIds.has(ex.id) }" />
                <span class="sel-name">{{ ex.expense_type }}</span>
                <span class="sel-amount">{{ (parseFloat(ex.amount)||0).toLocaleString('ru-RU', { maximumFractionDigits: 2 }) }} {{ ex.currency }}</span>
              </div>
            </template>
            <div v-if="selectionMixed" class="warn-text">Выбранные позиции в разных валютах — платите раздельно</div>
            <div class="selection-actions">
              <button class="action-btn" type="button" :disabled="!selectedItemIds.size && !selectedExpenseIds.size || selectionMixed" @click="openPaySelected">
                Оплатить выбранное
              </button>
              <button class="action-btn secondary" type="button" @click="cancelSelection">Отмена</button>
            </div>
          </div>
        </template>
        <template v-else>
          <!-- Per-currency totals -->
          <div v-if="Object.keys(allTotalsByCurrency).length" class="currency-totals">
            <div v-for="(amt, cur) in allTotalsByCurrency" :key="cur" class="currency-total-row">
              <span class="cur-label">К оплате</span>
              <span class="cur-amount">{{ amt.toLocaleString('ru-RU', { maximumFractionDigits: 2 }) }} {{ cur }}</span>
            </div>
          </div>
          <button class="action-btn primary-action" type="button" @click="openPayFull">Оплатить всё</button>
          <button class="text-link" type="button" @click="openPaySelective">Оплатить выборочно →</button>
        </template>
      </template>
    </template>
  </div>

  <PaymentMakeSheet
    v-model:open="paySheetOpen"
    :procurement="procurement"
    :default-amount="paySheetDefaultAmount"
    :payment-type="paySheetType"
    :payable-id="paySheetPayableId"
    :schedule-entry-id="paySheetScheduleEntryId"
    :item-ids="paySheetItemIds"
    :expense-ids="paySheetExpenseIds"
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

<style scoped>
.payment-card { display: grid; gap: var(--space-3); padding: var(--space-4); background: var(--color-bg-primary); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-lg); }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.card-title { font-size: var(--text-base); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.status-ok { color: var(--color-success); }
.status-warn { color: var(--color-warning); }
.obligation-block { display: grid; gap: var(--space-1); padding: var(--space-3); background: var(--color-bg-secondary); border-radius: var(--radius-md); }
.ob-row { display: flex; align-items: center; justify-content: space-between; }
.ob-label { font-size: var(--text-sm); color: var(--color-text-secondary); }
.ob-value { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); font-variant-numeric: tabular-nums; }
.ob-value.warn { color: var(--color-warning); }
.available-row { padding: var(--space-2) var(--space-3); font-size: var(--text-sm); color: var(--color-success); font-weight: var(--font-semibold); }
.info-text { font-size: var(--text-sm); color: var(--color-text-secondary); padding: var(--space-2) 0; }
.warn-text { font-size: var(--text-sm); color: var(--color-warning); font-weight: var(--font-semibold); }
.deadline-row { display: flex; align-items: center; justify-content: space-between; }
.deadline-label { font-size: var(--text-sm); color: var(--color-text-secondary); }
.deadline-value { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.days-hint { font-size: var(--text-xs); color: var(--color-text-secondary); font-weight: var(--font-normal); margin-left: var(--space-1); }
.partial-info { display: grid; gap: var(--space-1); }
.history-list { display: grid; gap: var(--space-1); }
.history-row { display: flex; align-items: center; justify-content: space-between; padding: var(--space-2) var(--space-3); background: var(--color-bg-secondary); border-radius: var(--radius-sm); }
.hist-date { font-size: var(--text-xs); color: var(--color-text-secondary); }
.hist-amount { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); font-variant-numeric: tabular-nums; }
.schedule-list { display: grid; gap: var(--space-2); }
.schedule-row { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); padding: var(--space-2) var(--space-3); background: var(--color-bg-secondary); border-radius: var(--radius-md); }
.schedule-meta { display: flex; align-items: center; gap: var(--space-2); flex: 1; min-width: 0; }
.seq { font-size: var(--text-xs); color: var(--color-text-tertiary); font-weight: var(--font-semibold); }
.entry-date { font-size: var(--text-sm); color: var(--color-text-secondary); }
.entry-amount { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); font-variant-numeric: tabular-nums; }
.entry-pay-btn { flex-shrink: 0; padding: var(--space-1) var(--space-3); border: 1px solid var(--color-brand-600); border-radius: var(--radius-full); background: transparent; color: var(--color-brand-700); font-size: var(--text-xs); font-weight: var(--font-semibold); cursor: pointer; }
.entry-paid { flex-shrink: 0; font-size: var(--text-sm); color: var(--color-success); }
.action-btn { display: flex; align-items: center; justify-content: center; width: 100%; min-height: 44px; padding: var(--space-3); border: 1px dashed var(--color-border-subtle); border-radius: var(--radius-md); background: transparent; color: var(--color-brand-700); font-size: var(--text-sm); font-weight: var(--font-semibold); cursor: pointer; }
.action-btn.secondary { color: var(--color-text-secondary); }
.action-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.selection-section { display: grid; gap: var(--space-2); }
.selection-header { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--color-text-tertiary); text-transform: uppercase; letter-spacing: 0.04em; padding: var(--space-1) 0; }
.selection-row { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-2) var(--space-3); background: var(--color-bg-secondary); border-radius: var(--radius-md); cursor: pointer; }
.sel-icon { flex-shrink: 0; color: var(--color-text-tertiary); }
.sel-icon.checked { color: var(--color-brand-600); }
.sel-name { flex: 1; font-size: var(--text-sm); color: var(--color-text-primary); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sel-amount { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-secondary); font-variant-numeric: tabular-nums; flex-shrink: 0; }
.selection-actions { display: grid; gap: var(--space-2); margin-top: var(--space-1); }
.currency-totals { display: grid; gap: var(--space-1); padding: var(--space-3); background: var(--color-bg-secondary); border-radius: var(--radius-md); }
.currency-total-row { display: flex; align-items: center; justify-content: space-between; }
.cur-label { font-size: var(--text-sm); color: var(--color-text-secondary); }
.cur-amount { font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-primary); font-variant-numeric: tabular-nums; }
.action-btn.primary-action { border: none; background: var(--color-brand-600); color: white; }
.text-link { background: none; border: none; color: var(--color-brand-700); font-size: var(--text-sm); font-weight: var(--font-semibold); cursor: pointer; padding: var(--space-1) 0; text-align: center; width: 100%; }
.topup-hint { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-2) var(--space-3); background: var(--color-danger-50, rgba(239, 68, 68, 0.08)); border-radius: var(--radius-md); font-size: var(--text-xs); color: var(--color-danger-700, #b91c1c); flex-wrap: wrap; }
.topup-icon { flex-shrink: 0; }
.topup-btn { display: inline-flex; align-items: center; gap: var(--space-1); margin-left: auto; padding: var(--space-1) var(--space-3); border: 1px solid currentColor; border-radius: var(--radius-full); font-size: var(--text-xs); font-weight: var(--font-semibold); cursor: pointer; background: transparent; color: var(--color-brand-700); flex-shrink: 0; }
</style>
