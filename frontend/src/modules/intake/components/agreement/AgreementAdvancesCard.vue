<script setup lang="ts">
import { computed } from 'vue'
import { Scale } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatPrice } from '@/utils/currency'
import type { CapitalPositionRow } from '@/api/partnerships'

const props = defineProps<{
  positions: CapitalPositionRow[]
}>()

const emit = defineEmits<{
  settle: [position: CapitalPositionRow]
  withdraw: [position: CapitalPositionRow]
}>()

const EPS = 0.01

function net(row: CapitalPositionRow): number {
  return Number(row.net) || 0
}
function owed(row: CapitalPositionRow): number {
  return Number(row.owed) || 0
}
function withdrawable(row: CapitalPositionRow): number {
  return Number(row.withdrawable) || 0
}
// Surplus that exists but is tied up in inventory until debtors top up.
function locked(row: CapitalPositionRow): number {
  return Math.max(0, -net(row) - withdrawable(row))
}

// Only sides with a non-zero net matter. Debtors (owe the pool) first.
const rows = computed(() =>
  [...props.positions]
    .filter((r) => Math.abs(net(r)) > EPS)
    .sort((a, b) => net(b) - net(a)),
)

const hasOwing = computed(() => rows.value.some((r) => owed(r) > EPS))
const ventureTotals = computed(() => props.positions.reduce((acc, row) => {
  acc.capitalRecovered += Number(row.capital_recovered_uzs ?? 0) || 0
  acc.remainingCapital += Number(row.remaining_inventory_capital_uzs ?? 0) || 0
  acc.provisionalProfit += Number(row.provisional_profit_uzs ?? 0) || 0
  acc.loss += Number(row.loss_uzs ?? 0) || 0
  acc.capitalAvailable += Number(row.capital_return_available_uzs ?? 0) || 0
  acc.profitAvailable += Number(row.provisional_profit_available_uzs ?? 0) || 0
  acc.negative += Number(row.negative_position_uzs ?? 0) || 0
  return acc
}, {
  capitalRecovered: 0,
  remainingCapital: 0,
  provisionalProfit: 0,
  loss: 0,
  capitalAvailable: 0,
  profitAvailable: 0,
  negative: 0,
}))
const hasVentureFacts = computed(() =>
  ventureTotals.value.capitalRecovered > EPS
  || ventureTotals.value.provisionalProfit > EPS
  || ventureTotals.value.loss > EPS,
)
</script>

<template>
  <Card class="rounded-2xl bg-background">
    <CardHeader>
      <div class="flex items-start justify-between gap-3">
        <div>
          <CardTitle class="text-base">Взаиморасчёты сторон</CardTitle>
          <CardDescription class="mt-1">
            Разница между договорной долей и фактически внесённым капиталом по всем приходам.
          </CardDescription>
        </div>
        <Scale class="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
      </div>
    </CardHeader>
    <CardContent class="flex flex-col gap-3">
      <div v-if="!rows.length" class="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
        Стороны внесли капитал по договору — взаиморасчётов нет.
      </div>

      <ul v-else class="flex flex-col gap-2">
        <li
          v-for="row in rows"
          :key="row.partner_id"
          class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border px-4 py-3"
        >
          <div class="min-w-0">
            <span class="block truncate font-medium text-foreground">{{ row.partner_name }}</span>
            <span class="mt-0.5 block text-xs text-muted-foreground">
              {{ net(row) > 0 ? 'должен довнести в пул' : 'переплатил — можно вернуть' }}
            </span>
            <span v-if="net(row) < 0 && locked(row) > 0.01" class="mt-0.5 block text-xs text-muted-foreground">
              ещё {{ formatPrice(locked(row), row.currency) }} — после погашения другой стороной
            </span>
          </div>
          <div class="flex items-center gap-3">
            <span
              class="text-sm font-semibold tabular-nums"
              :class="net(row) > 0 ? 'text-warning' : 'text-green-700'"
            >
              {{ formatPrice(net(row) > 0 ? owed(row) : withdrawable(row), row.currency) }}
            </span>
            <Button v-if="net(row) > 0" size="sm" type="button" @click="emit('settle', row)">
              Погасить
            </Button>
            <Button v-if="net(row) < 0 && withdrawable(row) > EPS" size="sm" variant="outline" type="button" @click="emit('withdraw', row)">
              Вернуть в пул
            </Button>
          </div>
        </li>
      </ul>

      <p v-if="hasOwing" class="text-xs leading-relaxed text-muted-foreground">
        Погашение довносит капитал должника в пул договора (деньгами или из его прибыли).
        Переплату другая сторона забирает отдельно — через «Возврат капитала».
      </p>

      <div v-if="hasVentureFacts" class="rounded-xl border border-border bg-muted/30 p-3">
        <div class="mb-2 flex items-center justify-between gap-3">
          <p class="text-sm font-medium text-foreground">Реализация по продажам</p>
          <span v-if="ventureTotals.negative > EPS" class="text-xs font-medium text-destructive">
            минус {{ formatPrice(ventureTotals.negative, 'UZS') }}
          </span>
        </div>
        <div class="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
          <div>
            <span class="block text-muted-foreground">Восстановлено капитала</span>
            <span class="font-semibold tabular-nums text-foreground">{{ formatPrice(ventureTotals.capitalRecovered, 'UZS') }}</span>
          </div>
          <div>
            <span class="block text-muted-foreground">Капитал к возврату</span>
            <span class="font-semibold tabular-nums text-foreground">{{ formatPrice(ventureTotals.capitalAvailable, 'UZS') }}</span>
          </div>
          <div>
            <span class="block text-muted-foreground">Предв. прибыль</span>
            <span class="font-semibold tabular-nums text-foreground">{{ formatPrice(ventureTotals.profitAvailable, 'UZS') }}</span>
          </div>
          <div>
            <span class="block text-muted-foreground">Убытки</span>
            <span class="font-semibold tabular-nums text-foreground">{{ formatPrice(ventureTotals.loss, 'UZS') }}</span>
          </div>
          <div class="sm:col-span-2">
            <span class="block text-muted-foreground">Остаток в товаре</span>
            <span class="font-semibold tabular-nums text-foreground">{{ formatPrice(ventureTotals.remainingCapital, 'UZS') }}</span>
          </div>
        </div>
      </div>
    </CardContent>
  </Card>
</template>
