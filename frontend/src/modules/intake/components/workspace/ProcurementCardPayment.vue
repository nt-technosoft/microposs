<script setup lang="ts">
import { ref, computed } from 'vue'
import { CheckCircle, AlertCircle } from 'lucide-vue-next'
import PaymentMakeSheet from './PaymentMakeSheet.vue'
import PaymentScheduleEditor from './PaymentScheduleEditor.vue'
import ConsignmentObligationsBlock from './ConsignmentObligationsBlock.vue'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

const props = defineProps<{ procurement: ProcurementWorkspacePayload }>()
const emit = defineEmits<{
  dispatch: [actionKey: string, payload: Record<string, unknown>]
}>()

const paySheetOpen = ref(false)
const paySheetType = ref<'cost' | 'payable' | 'schedule-entry'>('cost')
const paySheetDefaultAmount = ref<string | undefined>(undefined)
const paySheetPayableId = ref<number | undefined>(undefined)
const paySheetScheduleEntryId = ref<number | undefined>(undefined)
const scheduleEditorOpen = ref(false)

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
  paySheetOpen.value = true
}

function openPayPartial(): void {
  paySheetType.value = 'cost'
  paySheetDefaultAmount.value = undefined
  paySheetPayableId.value = undefined
  paySheetScheduleEntryId.value = undefined
  paySheetOpen.value = true
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

    <!-- PARTNERSHIP: payment done via financing (B-6 allocation) -->
    <template v-if="isPartnership">
      <div class="info-text">Оплата через инвестиционный договор — см. раздел «Финансирование».</div>
    </template>

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
        <button class="action-btn" type="button" @click="openPayFull">Оплатить полностью</button>
        <button class="action-btn secondary" type="button" @click="openPayPartial">Оплатить частично</button>
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
    @dispatch="onPaymentDispatch"
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
</style>
