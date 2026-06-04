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
}>()

const EPS = 0.01

function net(row: CapitalPositionRow): number {
  return Number(row.net) || 0
}

// Only sides with a non-zero net matter. Debtors (owe the pool) first.
const rows = computed(() =>
  [...props.positions]
    .filter((r) => Math.abs(net(r)) > EPS)
    .sort((a, b) => net(b) - net(a)),
)

const hasOwing = computed(() => rows.value.some((r) => net(r) > EPS))
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
              {{ net(row) > 0 ? 'должен пулу договора' : 'пул договора должен — можно вернуть' }}
            </span>
          </div>
          <div class="flex items-center gap-3">
            <span
              class="text-sm font-semibold tabular-nums"
              :class="net(row) > 0 ? 'text-warning' : 'text-green-700'"
            >
              {{ formatPrice(Math.abs(net(row)), row.currency) }}
            </span>
            <Button v-if="net(row) > 0" size="sm" type="button" @click="emit('settle', row)">
              Погасить
            </Button>
          </div>
        </li>
      </ul>

      <p v-if="hasOwing" class="text-xs leading-relaxed text-muted-foreground">
        Погашение довносит капитал должника в пул договора (деньгами или из его прибыли).
        Переплату другая сторона забирает отдельно — через «Возврат капитала».
      </p>
    </CardContent>
  </Card>
</template>
