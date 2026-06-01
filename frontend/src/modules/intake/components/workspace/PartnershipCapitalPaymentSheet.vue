<script setup lang="ts">
import { computed, ref, toRef, watch } from 'vue'
import { CheckCircle2, Circle, Check } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { cn } from '@/lib/utils'
import { formatPrice } from '@/utils/currency'
import { useActiveLines } from '@/modules/intake/composables/useActiveLines'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

type Partner = NonNullable<ProcurementWorkspacePayload['documents']['investment']>['partners'][number]
type AllocationRow = { partnerId: number; amount: string; currency: string; capped: boolean }

const props = defineProps<{ open: boolean; procurement: ProcurementWorkspacePayload }>()
const emit = defineEmits<{
  'update:open': [value: boolean]
  dispatch: [actionKey: string, payload: Record<string, unknown>]
}>()

const { obligationItems, obligationExpenses } = useActiveLines(toRef(props, 'procurement'))

const selectedItemIds = ref<Set<number>>(new Set())
const selectedExpenseIds = ref<Set<number>>(new Set())
const allocations = ref<AllocationRow[]>([])

const investment = computed(() => props.procurement.documents.investment)

function lineAmount(item: ProcurementWorkspacePayload['documents']['items'][number]): number {
  return (parseFloat(item.quantity) || 0) * (parseFloat(item.unit_purchase_price) || 0)
}
function expenseAmount(expense: ProcurementWorkspacePayload['documents']['expenses'][number]): number {
  return parseFloat(expense.amount) || 0
}

// Capital already allocated to this procurement (per currency). Net of any
// FROM_PROCUREMENT reversals. This is what's already funded.
const allocatedByCurrency = computed<Record<string, number>>(() => {
  const totals: Record<string, number> = {}
  for (const a of investment.value?.allocations ?? []) {
    const c = (a.currency || 'UZS').toUpperCase()
    const amt = parseFloat(a.amount) || 0
    totals[c] = (totals[c] ?? 0) + (a.direction === 'TO_PROCUREMENT' ? amt : -amt)
  }
  return totals
})

const isPaidLine = (line: { payment_state?: string; lifecycle_state?: string } | undefined): boolean =>
  line?.payment_state === 'PAID'
  || line?.lifecycle_state === 'READY_FOR_RECEIVE'
  || line?.lifecycle_state === 'RECEIVED'
const isItemFunded = (id: number) => isPaidLine(obligationItems.value.find((item) => item.id === id))
const isExpenseFunded = (id: number) => isPaidLine(obligationExpenses.value.find((expense) => expense.id === id))

const unfundedItems = computed(() => obligationItems.value.filter((it) => !isItemFunded(it.id)))
const unfundedExpenses = computed(() => obligationExpenses.value.filter((ex) => !isExpenseFunded(ex.id)))

const selectedTotals = computed<Record<string, number>>(() => {
  const totals: Record<string, number> = {}
  for (const item of unfundedItems.value) {
    if (!selectedItemIds.value.has(item.id)) continue
    const c = (item.currency || 'UZS').toUpperCase()
    totals[c] = (totals[c] ?? 0) + lineAmount(item)
  }
  for (const expense of unfundedExpenses.value) {
    if (!selectedExpenseIds.value.has(expense.id)) continue
    const c = (expense.currency || 'UZS').toUpperCase()
    totals[c] = (totals[c] ?? 0) + expenseAmount(expense)
  }
  return totals
})

const selectedCurrencies = computed(() => Object.keys(selectedTotals.value).filter((c) => selectedTotals.value[c] > 0))
const hasSelection = computed(() => selectedItemIds.value.size > 0 || selectedExpenseIds.value.size > 0)
const isMixedSelection = computed(() => selectedCurrencies.value.length > 1)
const selectedCurrency = computed(() => selectedCurrencies.value[0] ?? investment.value?.currency ?? 'UZS')
const selectedTotal = computed(() => selectedTotals.value[selectedCurrency.value] ?? 0)
const alreadyFunded = computed(() => allocatedByCurrency.value[selectedCurrency.value] ?? 0)
const allocatedTotal = computed(() => allocations.value.reduce((s, r) => s + (parseFloat(r.amount) || 0), 0))
const allocationDelta = computed(() => Number((selectedTotal.value - allocatedTotal.value).toFixed(2)))
const allUnfundedSelected = computed(
  () => unfundedItems.value.length === 0 && unfundedExpenses.value.length === 0,
)
const canSubmit = computed(() =>
  hasSelection.value && !isMixedSelection.value && selectedTotal.value > 0 && Math.abs(allocationDelta.value) <= 0.01,
)

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
    partner, weight: partnerWeight(partner), available: partnerAvailable(partner.partner_id, currency), amount: 0,
  }))
  const weightTotal = rows.reduce((s, r) => s + r.weight, 0) || rows.length || 1
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
// Allocation across partners is computed silently from the pool (proportional
// to available capital) — payment comes from the common agreement pocket, NOT a
// manual per-partner step. Per-partner SHARES are fixed at receive (snapshot).
function recomputeAllocations(): void {
  const inv = investment.value
  if (!inv || isMixedSelection.value) { allocations.value = []; return }
  allocations.value = allocateProportionally(selectedTotal.value, inv.partners, selectedCurrency.value)
}
function toggleItem(id: number): void {
  if (isItemFunded(id)) return
  const next = new Set(selectedItemIds.value)
  next.has(id) ? next.delete(id) : next.add(id)
  selectedItemIds.value = next
  recomputeAllocations()
}
function toggleExpense(id: number): void {
  if (isExpenseFunded(id)) return
  const next = new Set(selectedExpenseIds.value)
  next.has(id) ? next.delete(id) : next.add(id)
  selectedExpenseIds.value = next
  recomputeAllocations()
}
function submit(): void {
  if (!canSubmit.value) return
  emit('dispatch', 'ALLOCATE_CAPITAL', {
    item_ids: [...selectedItemIds.value],
    expense_ids: [...selectedExpenseIds.value],
    allocations: allocations.value
      .filter((row) => (parseFloat(row.amount) || 0) > 0)
      .map((row) => ({ partner_id: row.partnerId, amount: row.amount, currency: row.currency })),
  })
  emit('update:open', false)
}

watch(() => props.open, (isOpen) => {
  if (!isOpen) return
  // Default to funding only what isn't already covered.
  selectedItemIds.value = new Set(unfundedItems.value.map((item) => item.id))
  selectedExpenseIds.value = new Set(unfundedExpenses.value.map((expense) => expense.id))
  recomputeAllocations()
})
</script>

<template>
  <AppBottomSheet :open="open" title="Оплата из партнёрского капитала" @close="emit('update:open', false)">
    <div class="flex flex-col gap-4">
      <!-- Everything already funded -->
      <div v-if="allUnfundedSelected" class="flex items-center gap-2 rounded-[10px] bg-green-50 px-3.5 py-3 text-sm font-medium text-positive">
        <CheckCircle2 class="size-4 shrink-0" />
        Всё уже профинансировано из капитала.
      </div>

      <template v-else>
        <!-- Remaining to fund -->
        <div class="flex flex-col gap-1.5 rounded-[10px] bg-neutral-50 px-3.5 py-3">
          <div v-if="alreadyFunded > 0" class="flex items-center justify-between gap-2">
            <span class="text-sm text-neutral-500">Уже профинансировано</span>
            <span class="text-sm font-semibold tabular-nums text-foreground">{{ formatPrice(alreadyFunded, selectedCurrency) }}</span>
          </div>
          <div class="flex items-center justify-between gap-2">
            <span class="text-sm text-neutral-500">Осталось профинансировать</span>
            <span class="text-base font-semibold tabular-nums text-foreground">{{ formatPrice(selectedTotal, selectedCurrency) }}</span>
          </div>
        </div>

        <!-- Товары -->
        <div class="flex flex-col gap-1.5">
          <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Товары</span>
          <div class="flex flex-col gap-1">
            <button
              v-for="item in obligationItems"
              :key="item.id"
              type="button"
              :disabled="isItemFunded(item.id)"
              :class="cn(
                'flex w-full items-center gap-2.5 rounded-lg border px-3 py-2 text-left transition-colors',
                isItemFunded(item.id)
                  ? 'border-neutral-200 bg-neutral-50 opacity-70'
                  : selectedItemIds.has(item.id) ? 'border-primary bg-primary/5' : 'border-neutral-200 hover:bg-neutral-50',
              )"
              @click="toggleItem(item.id)"
            >
              <Check v-if="isItemFunded(item.id)" class="size-4 shrink-0 text-positive" />
              <component v-else :is="selectedItemIds.has(item.id) ? CheckCircle2 : Circle" :class="cn('size-4 shrink-0', selectedItemIds.has(item.id) ? 'text-primary' : 'text-neutral-300')" />
              <span class="min-w-0 flex-1 truncate text-sm text-foreground">{{ item.product_variant_name }}</span>
              <span v-if="isItemFunded(item.id)" class="shrink-0 text-xs font-medium text-positive">оплачено</span>
              <span class="shrink-0 text-xs tabular-nums text-neutral-500">{{ formatPrice(lineAmount(item), item.currency) }}</span>
            </button>
          </div>
        </div>

        <!-- Расходы -->
        <div v-if="obligationExpenses.length" class="flex flex-col gap-1.5">
          <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Расходы</span>
          <div class="flex flex-col gap-1">
            <button
              v-for="expense in obligationExpenses"
              :key="expense.id"
              type="button"
              :disabled="isExpenseFunded(expense.id)"
              :class="cn(
                'flex w-full items-center gap-2.5 rounded-lg border px-3 py-2 text-left transition-colors',
                isExpenseFunded(expense.id)
                  ? 'border-neutral-200 bg-neutral-50 opacity-70'
                  : selectedExpenseIds.has(expense.id) ? 'border-primary bg-primary/5' : 'border-neutral-200 hover:bg-neutral-50',
              )"
              @click="toggleExpense(expense.id)"
            >
              <Check v-if="isExpenseFunded(expense.id)" class="size-4 shrink-0 text-positive" />
              <component v-else :is="selectedExpenseIds.has(expense.id) ? CheckCircle2 : Circle" :class="cn('size-4 shrink-0', selectedExpenseIds.has(expense.id) ? 'text-primary' : 'text-neutral-300')" />
              <span class="min-w-0 flex-1 truncate text-sm text-foreground">{{ expense.expense_type }}</span>
              <span v-if="isExpenseFunded(expense.id)" class="shrink-0 text-xs font-medium text-positive">оплачено</span>
              <span class="shrink-0 text-xs tabular-nums text-neutral-500">{{ formatPrice(expenseAmount(expense), expense.currency) }}</span>
            </button>
          </div>
        </div>

        <div v-if="isMixedSelection" class="rounded-[10px] border border-warning/30 bg-warning/10 px-3.5 py-3 text-sm text-foreground">
          В выбранных строках разные валюты. Разделите оплату на отдельные транши.
        </div>

        <!-- Payment comes from the common pool; shares are fixed at receive -->
        <p v-else class="text-xs leading-relaxed text-neutral-500">
          Оплата идёт из общего капитала договора. Доли участников фиксируются при приёмке товара.
        </p>

        <div v-if="!isMixedSelection && allocationDelta > 0.01" class="rounded-[10px] border border-warning/30 bg-warning/10 px-3.5 py-2.5 text-sm text-foreground">
          В капитале договора не хватает {{ formatPrice(allocationDelta, selectedCurrency) }}. Сначала пополните капитал.
        </div>

        <button
          type="button"
          class="h-12 w-full rounded-[10px] bg-green-600 text-base font-semibold text-white transition-colors hover:bg-green-700 disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="!canSubmit"
          @click="submit"
        >
          Оплатить
        </button>
      </template>
    </div>
  </AppBottomSheet>
</template>
