<script setup lang="ts">
import { computed } from 'vue'
import { CheckCircle2, Scale } from 'lucide-vue-next'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatPrice } from '@/utils/currency'
import type { ProcurementVentureSummary } from '@/api/partnerships'

const props = defineProps<{
  summary: ProcurementVentureSummary | null
  saving?: boolean
  readonly?: boolean
}>()

const emit = defineEmits<{
  settle: [type: 'CONSTRUCTIVE' | 'FINAL']
}>()

const totals = computed(() => props.summary?.totals ?? null)
const hasFacts = computed(() => {
  if (!totals.value) return false
  return Number(totals.value.capital_recovered_uzs || 0) > 0
    || Number(totals.value.provisional_profit_uzs || 0) > 0
    || Number(totals.value.loss_uzs || 0) > 0
})
// FINAL settlement requires the stock to be sold/reversed. Gate on the SAME
// authoritative signal the backend uses (has_active_lots) so UI and backend never
// diverge. Close-blocking reasons live in the dedicated close card, not here.
const canFinal = computed(() => props.summary?.has_active_lots === false)
const auditWarnings = computed(() => props.summary?.audit_warnings ?? [])
const participantRows = computed(() => (props.summary?.positions ?? []).filter((row) => row.role !== 'OPERATOR'))
</script>

<template>
  <Card v-if="summary && hasFacts" class="rounded-2xl bg-background">
    <CardHeader>
      <div class="flex items-start justify-between gap-3">
        <div>
          <CardTitle class="text-base">Операционная сводка после прихода</CardTitle>
          <CardDescription class="mt-1">
            Продажи, остаток товара и доступные действия по капиталу/прибыли.
          </CardDescription>
        </div>
        <Scale class="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
      </div>
    </CardHeader>
    <CardContent class="flex flex-col gap-3">
      <div
        v-if="auditWarnings.length"
        class="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
      >
        {{ auditWarnings[0].message }}
      </div>
      <div class="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
        <div>
          <span class="block text-muted-foreground">Восстановлено</span>
          <span class="font-semibold tabular-nums text-foreground">{{ formatPrice(totals?.capital_recovered_uzs || 0, 'UZS') }}</span>
        </div>
        <div>
          <span class="block text-muted-foreground">К возврату</span>
          <span class="font-semibold tabular-nums text-foreground">{{ formatPrice(totals?.capital_return_available_uzs || 0, 'UZS') }}</span>
        </div>
        <div>
          <span class="block text-muted-foreground">Прибыль к выплате</span>
          <span class="font-semibold tabular-nums text-foreground">{{ formatPrice(totals?.provisional_profit_available_uzs || 0, 'UZS') }}</span>
        </div>
        <div>
          <span class="block text-muted-foreground">Убытки</span>
          <span class="font-semibold tabular-nums text-foreground">{{ formatPrice(totals?.loss_uzs || 0, 'UZS') }}</span>
        </div>
        <div class="sm:col-span-2">
          <span class="block text-muted-foreground">Остаток в товаре</span>
          <span class="font-semibold tabular-nums text-foreground">{{ formatPrice(totals?.remaining_inventory_capital_uzs || 0, 'UZS') }}</span>
        </div>
      </div>

      <div v-if="participantRows.length" class="divide-y divide-border border-y border-border">
        <div v-for="row in participantRows" :key="row.partner_id" class="grid gap-1 py-2 text-xs sm:grid-cols-[1fr_auto]">
          <span class="min-w-0">
            <strong class="block truncate text-foreground">{{ row.partner_name }}</strong>
            <span class="text-muted-foreground">остаток в товаре {{ formatPrice(row.remaining_inventory_capital_uzs, 'UZS') }}</span>
          </span>
          <span class="text-left tabular-nums text-foreground sm:text-right">
            <strong class="block">{{ formatPrice(row.capital_return_available_uzs, 'UZS') }}</strong>
            <span class="block text-muted-foreground">капитал · прибыль {{ formatPrice(row.provisional_profit_available_uzs, 'UZS') }}</span>
          </span>
        </div>
      </div>

      <p v-if="!readonly && !canFinal" class="text-xs text-muted-foreground">
        Финальная сверка станет доступна после распродажи остатка товара.
      </p>

      <div v-if="!readonly" class="grid gap-2 sm:grid-cols-2">
        <Button variant="outline" type="button" :disabled="saving" @click="emit('settle', 'CONSTRUCTIVE')">
          <CheckCircle2 data-icon="inline-start" />
          Конструктивная сверка
        </Button>
        <Button type="button" :disabled="saving || !canFinal" @click="emit('settle', 'FINAL')">
          <CheckCircle2 data-icon="inline-start" />
          Финальная сверка
        </Button>
      </div>
    </CardContent>
  </Card>
</template>
