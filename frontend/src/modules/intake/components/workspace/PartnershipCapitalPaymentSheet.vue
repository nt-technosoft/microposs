<script setup lang="ts">
import { computed, ref, toRef, watch } from 'vue'
import { CheckSquare, Square } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { useActiveLines } from '@/modules/intake/composables/useActiveLines'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

type Partner = NonNullable<ProcurementWorkspacePayload['documents']['investment']>['partners'][number]
type AllocationRow = {
  partnerId: number
  amount: string
  currency: string
  capped: boolean
}

const props = defineProps<{
  open: boolean
  procurement: ProcurementWorkspacePayload
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  dispatch: [actionKey: string, payload: Record<string, unknown>]
}>()

const { obligationItems, obligationExpenses } = useActiveLines(toRef(props, 'procurement'))

const selectedItemIds = ref<Set<number>>(new Set())
const selectedExpenseIds = ref<Set<number>>(new Set())
const allocations = ref<AllocationRow[]>([])

const investment = computed(() => props.procurement.documents.investment)
const selectedTotals = computed<Record<string, number>>(() => {
  const totals: Record<string, number> = {}
  for (const item of obligationItems.value) {
    if (!selectedItemIds.value.has(item.id)) continue
    const currency = (item.currency || 'UZS').toUpperCase()
    totals[currency] = (totals[currency] ?? 0) + (parseFloat(item.quantity) || 0) * (parseFloat(item.unit_purchase_price) || 0)
  }
  for (const expense of obligationExpenses.value) {
    if (!selectedExpenseIds.value.has(expense.id)) continue
    const currency = (expense.currency || 'UZS').toUpperCase()
    totals[currency] = (totals[currency] ?? 0) + (parseFloat(expense.amount) || 0)
  }
  return totals
})

const selectedCurrencies = computed(() => Object.keys(selectedTotals.value).filter((currency) => selectedTotals.value[currency] > 0))
const hasSelection = computed(() => selectedItemIds.value.size > 0 || selectedExpenseIds.value.size > 0)
const isMixedSelection = computed(() => selectedCurrencies.value.length > 1)
const selectedCurrency = computed(() => selectedCurrencies.value[0] ?? investment.value?.currency ?? 'UZS')
const selectedTotal = computed(() => selectedTotals.value[selectedCurrency.value] ?? 0)
const allocatedTotal = computed(() =>
  allocations.value.reduce((sum, row) => sum + (parseFloat(row.amount) || 0), 0),
)
const allocationDelta = computed(() => Number((selectedTotal.value - allocatedTotal.value).toFixed(2)))
const canSubmit = computed(() =>
  hasSelection.value && !isMixedSelection.value && selectedTotal.value > 0 && Math.abs(allocationDelta.value) <= 0.01,
)

function money(value: number): string {
  return value.toLocaleString('ru-RU', { maximumFractionDigits: 2 })
}

function lineAmount(item: ProcurementWorkspacePayload['documents']['items'][number]): number {
  return (parseFloat(item.quantity) || 0) * (parseFloat(item.unit_purchase_price) || 0)
}

function expenseAmount(expense: ProcurementWorkspacePayload['documents']['expenses'][number]): number {
  return parseFloat(expense.amount) || 0
}

function partnerAvailable(partnerId: number, currency: string): number {
  const raw = investment.value?.available_by_partner[String(partnerId)]?.[currency] ?? '0'
  const value = parseFloat(raw)
  return Number.isFinite(value) ? Math.max(0, value) : 0
}

function partnerWeight(partner: Partner): number {
  const planned = parseFloat(partner.planned_capital_share)
  if (planned > 0) return planned
  const profit = parseFloat(partner.profit_share)
  return profit > 0 ? profit : 1
}

function allocateProportionally(total: number, partners: Partner[], currency: string): AllocationRow[] {
  const rows = partners.map((partner) => ({
    partner,
    weight: partnerWeight(partner),
    available: partnerAvailable(partner.partner_id, currency),
    amount: 0,
  }))
  const weightTotal = rows.reduce((sum, row) => sum + row.weight, 0) || rows.length || 1
  let remaining = total

  for (const row of rows) {
    const target = Number((total * row.weight / weightTotal).toFixed(2))
    row.amount = Math.min(target, row.available)
    remaining = Number((remaining - row.amount).toFixed(2))
  }

  for (const row of rows) {
    if (remaining <= 0) break
    const headroom = Math.max(0, row.available - row.amount)
    const topUp = Math.min(headroom, remaining)
    row.amount = Number((row.amount + topUp).toFixed(2))
    remaining = Number((remaining - topUp).toFixed(2))
  }

  if (Math.abs(remaining) <= 0.01 && rows.length) {
    rows[rows.length - 1].amount = Number((rows[rows.length - 1].amount + remaining).toFixed(2))
  }

  return rows.map((row) => ({
    partnerId: row.partner.partner_id,
    amount: row.amount.toFixed(2),
    currency,
    capped: row.amount + 0.001 < total * row.weight / weightTotal,
  }))
}

function recomputeAllocations(): void {
  const inv = investment.value
  if (!inv || isMixedSelection.value) {
    allocations.value = []
    return
  }
  allocations.value = allocateProportionally(selectedTotal.value, inv.partners, selectedCurrency.value)
}

function redistributeAfterManualChange(changedPartnerId: number, rawValue: string): void {
  const inv = investment.value
  if (!inv) return
  const currency = selectedCurrency.value
  const changedAmount = Math.min(Math.max(parseFloat(rawValue) || 0, 0), partnerAvailable(changedPartnerId, currency))
  const otherPartners = inv.partners.filter((partner) => partner.partner_id !== changedPartnerId)
  const remainder = Math.max(0, selectedTotal.value - changedAmount)
  const next = allocateProportionally(remainder, otherPartners, currency)
  allocations.value = [
    {
      partnerId: changedPartnerId,
      amount: changedAmount.toFixed(2),
      currency,
      capped: changedAmount + 0.001 >= partnerAvailable(changedPartnerId, currency),
    },
    ...next,
  ].sort((a, b) => {
    const aIndex = inv.partners.findIndex((partner) => partner.partner_id === a.partnerId)
    const bIndex = inv.partners.findIndex((partner) => partner.partner_id === b.partnerId)
    return aIndex - bIndex
  })
}

function partnerName(partnerId: number): string {
  return investment.value?.partners.find((partner) => partner.partner_id === partnerId)?.partner_name ?? `#${partnerId}`
}

function toggleItem(id: number): void {
  const next = new Set(selectedItemIds.value)
  next.has(id) ? next.delete(id) : next.add(id)
  selectedItemIds.value = next
  recomputeAllocations()
}

function toggleExpense(id: number): void {
  const next = new Set(selectedExpenseIds.value)
  next.has(id) ? next.delete(id) : next.add(id)
  selectedExpenseIds.value = next
  recomputeAllocations()
}

function submit(): void {
  if (!canSubmit.value) return
  emit('dispatch', 'ALLOCATE_CAPITAL', {
    allocations: allocations.value
      .filter((row) => (parseFloat(row.amount) || 0) > 0)
      .map((row) => ({
        partner_id: row.partnerId,
        amount: row.amount,
        currency: row.currency,
      })),
  })
  emit('update:open', false)
}

watch(() => props.open, (isOpen) => {
  if (!isOpen) return
  selectedItemIds.value = new Set(obligationItems.value.map((item) => item.id))
  selectedExpenseIds.value = new Set(obligationExpenses.value.map((expense) => expense.id))
  recomputeAllocations()
})
</script>

<template>
  <AppBottomSheet :open="open" title="Оплата из партнёрского капитала" @close="emit('update:open', false)">
    <div class="sheet-body">
      <div class="summary-row">
        <span>К оплате</span>
        <strong>{{ money(selectedTotal) }} {{ selectedCurrency }}</strong>
      </div>

      <div class="section-label">Товары</div>
      <button
        v-for="item in obligationItems"
        :key="item.id"
        class="select-row"
        type="button"
        @click="toggleItem(item.id)"
      >
        <component :is="selectedItemIds.has(item.id) ? CheckSquare : Square" :size="18" :stroke-width="2" />
        <span class="row-name">{{ item.product_variant_name }}</span>
        <span class="row-amount">{{ money(lineAmount(item)) }} {{ item.currency }}</span>
      </button>

      <template v-if="obligationExpenses.length">
        <div class="section-label">Расходы</div>
        <button
          v-for="expense in obligationExpenses"
          :key="expense.id"
          class="select-row"
          type="button"
          @click="toggleExpense(expense.id)"
        >
          <component :is="selectedExpenseIds.has(expense.id) ? CheckSquare : Square" :size="18" :stroke-width="2" />
          <span class="row-name">{{ expense.expense_type }}</span>
          <span class="row-amount">{{ money(expenseAmount(expense)) }} {{ expense.currency }}</span>
        </button>
      </template>

      <div v-if="isMixedSelection" class="warning-box">
        В выбранных строках разные валюты. Разделите оплату на отдельные транши.
      </div>

      <template v-if="!isMixedSelection && allocations.length">
        <div class="section-label">Доли оплаты</div>
        <div v-for="row in allocations" :key="row.partnerId" class="allocation-row">
          <div class="allocation-name">
            <span>{{ partnerName(row.partnerId) }}</span>
            <small v-if="row.capped">по доступному остатку</small>
          </div>
          <input
            class="allocation-input"
            type="number"
            min="0"
            step="0.01"
            :value="row.amount"
            @input="redistributeAfterManualChange(row.partnerId, ($event.target as HTMLInputElement).value)"
          />
          <span class="currency">{{ row.currency }}</span>
        </div>
        <div v-if="Math.abs(allocationDelta) > 0.01" class="warning-box">
          Нужно распределить ещё {{ money(allocationDelta) }} {{ selectedCurrency }}.
        </div>
      </template>

      <button class="primary-btn" type="button" :disabled="!canSubmit" @click="submit">
        Оплатить
      </button>
    </div>
  </AppBottomSheet>
</template>

<style scoped>
.sheet-body { display: grid; gap: var(--space-3); }
.summary-row { display: flex; align-items: center; justify-content: space-between; padding: var(--space-3); background: var(--color-bg-secondary); border-radius: var(--radius-md); font-size: var(--text-sm); }
.summary-row strong { font-variant-numeric: tabular-nums; color: var(--color-text-primary); }
.section-label { font-size: var(--text-xs); font-weight: var(--font-semibold); color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: .04em; }
.select-row { display: flex; align-items: center; gap: var(--space-2); min-height: 44px; padding: var(--space-2) var(--space-3); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); cursor: pointer; text-align: left; }
.row-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--text-sm); }
.row-amount { flex-shrink: 0; font-size: var(--text-sm); color: var(--color-text-secondary); font-variant-numeric: tabular-nums; }
.allocation-row { display: grid; grid-template-columns: minmax(0, 1fr) 120px auto; align-items: center; gap: var(--space-2); }
.allocation-name { display: grid; gap: 2px; min-width: 0; font-size: var(--text-sm); color: var(--color-text-primary); }
.allocation-name span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.allocation-name small { color: var(--color-warning); font-size: var(--text-xs); }
.allocation-input { min-width: 0; min-height: 40px; padding: 0 var(--space-2); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); text-align: right; font-size: var(--text-sm); font-variant-numeric: tabular-nums; }
.currency { font-size: var(--text-sm); color: var(--color-text-secondary); font-weight: var(--font-semibold); }
.warning-box { padding: var(--space-3); border: 1px solid color-mix(in srgb, var(--color-warning) 25%, transparent); border-radius: var(--radius-md); background: color-mix(in srgb, var(--color-warning) 9%, transparent); color: var(--color-text-primary); font-size: var(--text-sm); }
.primary-btn { min-height: 48px; border: 0; border-radius: var(--radius-lg); background: var(--color-brand-500); color: var(--color-text-inverse); font-weight: var(--font-semibold); cursor: pointer; }
.primary-btn:disabled { opacity: .55; cursor: not-allowed; }
</style>
