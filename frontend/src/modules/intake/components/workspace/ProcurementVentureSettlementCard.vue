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
const blockingReasons = computed(() => props.summary?.blocking_reasons ?? [])
</script>

<template>
  <Card v-if="summary && hasFacts" class="rounded-2xl bg-background">
    <CardHeader>
      <div class="flex items-start justify-between gap-3">
        <div>
          <CardTitle class="text-base">Сверка венчура</CardTitle>
          <CardDescription class="mt-1">
            Продажи уже сформировали восстановленный капитал и предварительный результат.
          </CardDescription>
        </div>
        <Scale class="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
      </div>
    </CardHeader>
    <CardContent class="flex flex-col gap-3">
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
          <span class="block text-muted-foreground">Предв. прибыль</span>
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

      <div v-if="blockingReasons.length" class="rounded-xl border border-warning/30 bg-warning/10 p-3 text-sm text-warning">
        <p v-for="reason in blockingReasons" :key="reason">{{ reason }}</p>
      </div>

      <div class="grid gap-2 sm:grid-cols-2">
        <Button variant="outline" type="button" :disabled="saving" @click="emit('settle', 'CONSTRUCTIVE')">
          <CheckCircle2 data-icon="inline-start" />
          Конструктивная сверка
        </Button>
        <Button type="button" :disabled="saving || blockingReasons.length > 0" @click="emit('settle', 'FINAL')">
          <CheckCircle2 data-icon="inline-start" />
          Финальная сверка
        </Button>
      </div>
    </CardContent>
  </Card>
</template>
