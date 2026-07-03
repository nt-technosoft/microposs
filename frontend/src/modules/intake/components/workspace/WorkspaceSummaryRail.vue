<script setup lang="ts">
import { computed } from 'vue'
import { ArrowRight } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { formatPrice } from '@/utils/currency'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

const props = defineProps<{ procurement: ProcurementWorkspacePayload }>()

const emit = defineEmits<{ navigate: [key: string] }>()

const itemsTotal = computed(() => formatPrice(props.procurement.summaries.items_total_uzs))
const expensesTotal = computed(() => Number.parseFloat(props.procurement.summaries.expenses_total_uzs || '0'))
const expensesLabel = computed(() => formatPrice(props.procurement.summaries.expenses_total_uzs))

function totalByCurrency<T extends { currency?: string }>(
  rows: T[],
  amountFor: (row: T) => number,
): string | null {
  const totals = rows.reduce<Record<string, number>>((acc, row) => {
    const currency = String(row.currency || 'UZS').toUpperCase()
    acc[currency] = (acc[currency] ?? 0) + amountFor(row)
    return acc
  }, {})
  const entries = Object.entries(totals).filter(([, amount]) => amount > 0)
  if (entries.length === 0) return null
  return entries.map(([currency, amount]) => formatPrice(amount, currency)).join(' · ')
}

const itemsNativeLabel = computed(() =>
  totalByCurrency(
    props.procurement.documents.items.filter((item) => item.lifecycle_state !== 'CANCELLED'),
    (item) => (Number.parseFloat(item.quantity) || 0) * (Number.parseFloat(item.unit_purchase_price) || 0),
  ),
)
const expensesNativeLabel = computed(() =>
  totalByCurrency(
    props.procurement.documents.expenses.filter((expense) => expense.lifecycle_state !== 'CANCELLED'),
    (expense) => Number.parseFloat(expense.amount) || 0,
  ),
)

const remaining = computed(() => {
  const byCurrency = props.procurement.documents.payment_status?.remaining_by_currency ?? {}
  const entries = Object.entries(byCurrency)
    .map(([currency, amount]) => [currency, Number.parseFloat(amount || '0')] as const)
    .filter(([, amount]) => amount > 0)
  if (entries.length === 0) return null
  return entries.map(([currency, amount]) => formatPrice(amount, currency)).join(' · ')
})

const nextAction = computed(() => props.procurement.display.next_action)
const currentStep = computed(() => props.procurement.flow.current_step)
</script>

<template>
  <div class="flex flex-col gap-4 rounded-[14px] border border-neutral-200 bg-surface p-4">
    <div class="flex flex-col gap-3">
      <div class="flex items-baseline justify-between gap-3">
        <span class="text-xs text-neutral-500">Закупка, UZS учёт</span>
        <div class="text-right">
          <strong class="block text-sm font-semibold tabular-nums text-foreground">{{ itemsTotal }}</strong>
          <span v-if="itemsNativeLabel && itemsNativeLabel !== itemsTotal" class="text-[11px] tabular-nums text-neutral-400">
            исходно {{ itemsNativeLabel }}
          </span>
        </div>
      </div>
      <div v-if="expensesTotal > 0" class="flex items-baseline justify-between gap-3">
        <span class="text-xs text-neutral-500">Расходы, UZS учёт</span>
        <div class="text-right">
          <strong class="block text-sm font-medium tabular-nums text-foreground">{{ expensesLabel }}</strong>
          <span v-if="expensesNativeLabel && expensesNativeLabel !== expensesLabel" class="text-[11px] tabular-nums text-neutral-400">
            исходно {{ expensesNativeLabel }}
          </span>
        </div>
      </div>
      <div v-if="remaining" class="flex items-baseline justify-between gap-3">
        <span class="text-xs text-neutral-500">К оплате</span>
        <strong class="text-sm font-semibold tabular-nums text-warning">{{ remaining }}</strong>
      </div>
    </div>

    <template v-if="nextAction.label">
      <Separator />
      <div class="flex flex-col gap-2">
        <span class="text-xs text-neutral-500">Следующий шаг</span>
        <Button
          variant="outline"
          class="justify-between"
          @click="emit('navigate', currentStep)"
        >
          {{ nextAction.label }}
          <ArrowRight data-icon="inline-end" />
        </Button>
        <p v-if="nextAction.reason" class="text-xs text-neutral-500">{{ nextAction.reason }}</p>
      </div>
    </template>
  </div>
</template>
