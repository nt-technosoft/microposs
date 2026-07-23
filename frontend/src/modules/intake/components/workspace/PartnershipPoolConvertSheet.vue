<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ArrowDown } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { Button } from '@/components/ui/button'
import { useFxRate } from '@/composables/useFxRate'
import { formatPrice } from '@/utils/currency'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

const props = defineProps<{
  open: boolean
  procurement: ProcurementWorkspacePayload
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  dispatch: [actionKey: string, payload: Record<string, unknown>]
}>()

const CURRENCY_NAME: Record<string, string> = { USD: 'доллары', UZS: 'сумы' }

const investment = computed(() => props.procurement.documents.investment)
const baseCurrency = computed(() => (investment.value?.currency ?? 'UZS').toUpperCase())
const targetCurrency = computed(() => (baseCurrency.value === 'USD' ? 'UZS' : 'USD'))
const baseName = computed(() => CURRENCY_NAME[baseCurrency.value] ?? baseCurrency.value)
const targetName = computed(() => CURRENCY_NAME[targetCurrency.value] ?? targetCurrency.value)

const basePool = computed(
  () => investment.value?.currency_pools.find((p) => p.is_base) ?? (investment.value?.pool ?? null),
)
const baseBalance = computed(() => Number.parseFloat(basePool.value?.balance ?? '0') || 0)

// The rate is always shown the human way: сум за 1 доллар (central-bank value).
const { rate: fetchedRate, rateDate, isLoading: rateLoading, load: loadRate } = useFxRate({
  baseCurrency: 'USD',
  quoteCurrency: 'UZS',
})
const rate = ref('')
const fromAmount = ref('')

const rateValue = computed(() => Number.parseFloat(rate.value) || 0)
const fromValue = computed(() => Number.parseFloat(fromAmount.value) || 0)

// Direction-aware conversion. UI rate is UZS per 1 USD regardless of direction.
const toAmount = computed(() => {
  if (!rateValue.value || !fromValue.value) return 0
  return baseCurrency.value === 'USD' ? fromValue.value * rateValue.value : fromValue.value / rateValue.value
})
// Backend `rate` = target currency per 1 base currency.
const backendRate = computed(() => {
  if (!rateValue.value) return 0
  return baseCurrency.value === 'USD' ? rateValue.value : 1 / rateValue.value
})

const insufficient = computed(() => fromValue.value > baseBalance.value)
const canConvert = computed(() => fromValue.value > 0 && rateValue.value > 0 && !insufficient.value)

const rateHint = computed(() => {
  if (rateLoading.value) return 'Загружаем курс…'
  if (rateDate.value) return `Курс ЦБ на ${new Date(rateDate.value).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })} — можно изменить`
  return 'Можно изменить'
})

watch(() => props.open, async (isOpen) => {
  if (!isOpen) return
  fromAmount.value = ''
  rate.value = ''
  try {
    const loaded = await loadRate()
    rate.value = loaded || String(fetchedRate.value || '')
  } catch {
    rate.value = ''
  }
})

function fillAll(): void {
  fromAmount.value = String(baseBalance.value)
}

function onConvert(): void {
  if (!canConvert.value) return
  emit('dispatch', 'CONVERT_CAPITAL_POOL', {
    to_currency: targetCurrency.value,
    from_amount: fromValue.value,
    rate: backendRate.value,
  })
  emit('update:open', false)
}
</script>

<template>
  <AppBottomSheet :open="open" title="Обмен валюты в договоре" @close="emit('update:open', false)">
    <div class="flex flex-col gap-5">
      <p class="text-sm leading-relaxed text-neutral-500">
        В пуле сейчас <span class="font-medium text-foreground">{{ formatPrice(baseBalance, baseCurrency) }}</span>.
        Чтобы оплачивать расходы в {{ targetName }}, обменяйте часть на {{ targetName }} по курсу.
        Это реальный обмен — деньги остаются в договоре.
      </p>

      <!-- Отдаёте -->
      <div class="flex flex-col gap-2">
        <div class="flex items-baseline justify-between">
          <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Отдаёте</span>
          <button type="button" class="text-xs font-medium text-green-700" @click="fillAll">Всё</button>
        </div>
        <div class="flex items-center gap-2 rounded-[12px] border border-neutral-200 px-4 py-3 focus-within:border-green-400">
          <input
            v-model="fromAmount"
            type="number"
            inputmode="decimal"
            min="0"
            placeholder="0"
            class="min-w-0 flex-1 bg-transparent text-2xl font-semibold tabular-nums text-foreground outline-none placeholder:text-neutral-300"
          />
          <span class="shrink-0 text-sm font-medium text-neutral-500">{{ baseCurrency }}</span>
        </div>
        <span class="text-xs tabular-nums" :class="insufficient ? 'text-negative' : 'text-neutral-400'">
          Доступно {{ formatPrice(baseBalance, baseCurrency) }}
        </span>
      </div>

      <!-- Курс -->
      <div class="flex items-center gap-3">
        <ArrowDown class="size-4 shrink-0 text-neutral-300" />
        <div class="flex flex-1 items-center gap-2">
          <span class="shrink-0 text-xs font-medium uppercase tracking-wide text-neutral-500">Курс</span>
          <input
            v-model="rate"
            type="number"
            inputmode="decimal"
            min="0"
            placeholder="0"
            class="w-28 rounded-[10px] border border-neutral-200 bg-transparent px-3 py-2 text-right text-sm font-semibold tabular-nums text-foreground outline-none focus:border-green-400"
          />
          <span class="shrink-0 text-xs text-neutral-500">сум за 1 $</span>
        </div>
      </div>
      <span class="-mt-3 pl-7 text-xs text-neutral-400">{{ rateHint }}</span>

      <!-- Получаете -->
      <div class="flex flex-col gap-1.5 rounded-[12px] bg-green-50/60 px-4 py-3">
        <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Получаете</span>
        <span class="text-2xl font-bold tabular-nums text-green-800">{{ formatPrice(toAmount, targetCurrency) }}</span>
      </div>

      <Button class="h-12 w-full text-base" :disabled="!canConvert" @click="onConvert">
        Обменять
      </Button>
    </div>
  </AppBottomSheet>
</template>
