<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RotateCcw } from 'lucide-vue-next'
import { Slider } from '@/components/ui/slider'
import { Button } from '@/components/ui/button'

const props = defineProps<{
  investorName: string
  operatorName: string
  plannedCapitalPercent: number
  actualCapitalPercent: number | null
  mudarabaRatio: number
}>()

// Baseline = the real (actual) capital share if there are contributions,
// otherwise the planned share.
const baseline = computed(() => Math.round(props.actualCapitalPercent ?? props.plannedCapitalPercent))
const model = ref<number[]>([baseline.value])
watch(baseline, (value) => { model.value = [value] })

const investorCapital = computed(() => model.value[0] ?? 0)
const operatorCapital = computed(() => Math.max(0, 100 - investorCapital.value))

function clampPercent(value: number): number {
  return Math.min(100, Math.max(0, Number.isFinite(value) ? value : 0))
}
const investorProfit = computed(() => Math.round(clampPercent(investorCapital.value * props.mudarabaRatio)))
const operatorProfit = computed(() => Math.max(0, 100 - investorProfit.value))

const isChanged = computed(() => investorCapital.value !== baseline.value)

function reset(): void {
  model.value = [baseline.value]
}
</script>

<template>
  <div class="flex flex-col gap-3 rounded-[10px] bg-neutral-50 p-3">
    <p class="text-xs leading-relaxed text-neutral-500">
      Прибыль делится пропорционально вложенному капиталу по коэффициенту договора.
      Подвигайте долю капитала инвестора — прибыль пересчитается.
    </p>

    <div class="flex flex-col gap-2">
      <div class="flex items-baseline justify-between gap-2 text-sm">
        <span class="text-neutral-600">Капитал инвестора</span>
        <strong class="tabular-nums text-foreground">{{ investorCapital }}%</strong>
      </div>
      <Slider :model-value="model" :min="0" :max="100" :step="1" @update:model-value="(v) => model = (v as number[])" />
      <div class="flex justify-between text-xs tabular-nums text-neutral-400">
        <span>{{ investorName }} {{ investorCapital }}%</span>
        <span>{{ operatorName }} {{ operatorCapital }}%</span>
      </div>
    </div>

    <div class="grid grid-cols-2 gap-2">
      <div class="flex flex-col gap-0.5 rounded-[8px] bg-surface px-3 py-2">
        <span class="truncate text-xs text-neutral-500">Прибыль · {{ investorName }}</span>
        <strong class="text-base font-semibold tabular-nums text-foreground">{{ investorProfit }}%</strong>
      </div>
      <div class="flex flex-col gap-0.5 rounded-[8px] bg-surface px-3 py-2">
        <span class="truncate text-xs text-neutral-500">Прибыль · {{ operatorName }}</span>
        <strong class="text-base font-semibold tabular-nums text-foreground">{{ operatorProfit }}%</strong>
      </div>
    </div>

    <Button
      v-if="isChanged"
      variant="ghost"
      size="sm"
      class="self-start text-neutral-500"
      @click="reset"
    >
      <RotateCcw data-icon="inline-start" />
      Сбросить к факту
    </Button>
  </div>
</template>
