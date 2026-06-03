<script setup lang="ts">
import { computed } from 'vue'
import { ArrowRight, Scale } from 'lucide-vue-next'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatPrice } from '@/utils/currency'
import type { CapitalAdvanceRecord } from '@/api/partnerships'

const props = defineProps<{
  advances: CapitalAdvanceRecord[]
  loading?: boolean
}>()

const emit = defineEmits<{
  settle: [advance: CapitalAdvanceRecord]
}>()

// Open balances first; settled/cancelled drop to the bottom (history).
const sorted = computed(() =>
  [...props.advances].sort((a, b) => {
    const open = (s: string) => (s === 'OUTSTANDING' || s === 'PARTIAL' ? 0 : 1)
    return open(a.status) - open(b.status) || a.id - b.id
  }),
)

const hasOpen = computed(() => props.advances.some((a) => a.status === 'OUTSTANDING' || a.status === 'PARTIAL'))

function isOpen(a: CapitalAdvanceRecord): boolean {
  return a.status === 'OUTSTANDING' || a.status === 'PARTIAL'
}

function statusLabel(status: string): string {
  return { OUTSTANDING: 'Не погашен', PARTIAL: 'Частично', SETTLED: 'Погашен', CANCELLED: 'Аннулирован' }[status] ?? status
}

function modeLabel(mode: string): string {
  return mode === 'FROM_PROFIT' ? 'из прибыли' : 'разово'
}
</script>

<template>
  <Card class="rounded-2xl bg-background">
    <CardHeader>
      <div class="flex items-start justify-between gap-3">
        <div>
          <CardTitle class="text-base">Взаиморасчёты сторон</CardTitle>
          <CardDescription class="mt-1">
            Долги между сторонами, возникшие из разницы внесённого и договорного капитала.
          </CardDescription>
        </div>
        <Scale class="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
      </div>
    </CardHeader>
    <CardContent class="flex flex-col gap-3">
      <div v-if="!advances.length" class="rounded-xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
        Открытых взаиморасчётов нет — стороны внесли капитал ровно по договору.
      </div>

      <ul v-else class="flex flex-col gap-2">
        <li
          v-for="advance in sorted"
          :key="advance.id"
          class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border px-4 py-3"
          :class="{ 'opacity-60': !isOpen(advance) }"
        >
          <div class="min-w-0">
            <div class="flex items-center gap-1.5 font-medium text-foreground">
              <span class="truncate">{{ advance.debtor_name }}</span>
              <ArrowRight class="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span class="truncate">{{ advance.creditor_name || 'Пул' }}</span>
            </div>
            <div class="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <Badge variant="secondary">{{ statusLabel(advance.status) }}</Badge>
              <span>погашение: {{ modeLabel(advance.repayment_mode) }}</span>
            </div>
          </div>

          <div class="flex items-center gap-3">
            <div class="text-right">
              <p class="text-sm font-semibold tabular-nums text-foreground">
                {{ formatPrice(advance.outstanding_balance, advance.currency) }}
              </p>
              <p class="text-xs text-muted-foreground">из {{ formatPrice(advance.principal, advance.currency) }}</p>
            </div>
            <Button
              v-if="isOpen(advance)"
              size="sm"
              type="button"
              @click="emit('settle', advance)"
            >
              Погасить
            </Button>
          </div>
        </li>
      </ul>

      <p v-if="hasOpen" class="text-xs text-muted-foreground">
        Долг можно закрыть деньгами или из накопленной прибыли должника.
      </p>
    </CardContent>
  </Card>
</template>
