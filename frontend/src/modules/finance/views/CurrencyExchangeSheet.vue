<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowRightLeft, RefreshCcw } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { createCurrencyExchange, type CashAccountRecord } from '@/api/finance'
import { useFxRate } from '@/composables/useFxRate'
import { useToast } from '@/composables/useToast'
import { formatPrice } from '@/utils/currency'

const props = defineProps<{
  open: boolean
  accounts: CashAccountRecord[]
  targetCurrency?: string | null
  toAccountId?: number | null
  defaultAmount?: string | number | null
}>()

const emit = defineEmits<{
  close: []
  exchanged: []
}>()

const toast = useToast()
const {
  rate: latestUsdUzsRate,
  load: loadLatestUsdUzsRate,
} = useFxRate({ baseCurrency: 'USD', quoteCurrency: 'UZS' })

const fromAccountId = ref<number | null>(null)
const toAccountId = ref<number | null>(null)
const fromAmount = ref('')
const notes = ref('')
const isSaving = ref(false)
const error = ref<string | null>(null)

const activeAccounts = computed(() => props.accounts.filter((account) => account.is_active !== false))
const targetCurrency = computed(() => (props.targetCurrency ?? '').toUpperCase())
const fromAccount = computed(() => activeAccounts.value.find((account) => account.id === fromAccountId.value) ?? null)
const toAccount = computed(() => activeAccounts.value.find((account) => account.id === toAccountId.value) ?? null)

const toAccounts = computed(() =>
  activeAccounts.value.filter((account) =>
    targetCurrency.value
      ? account.currency.toUpperCase() === targetCurrency.value
      : account.id !== fromAccountId.value && account.currency !== fromAccount.value?.currency,
  ),
)

const fromAccounts = computed(() =>
  activeAccounts.value.filter((account) =>
    account.id !== toAccountId.value &&
      (!toAccount.value || account.currency !== toAccount.value.currency),
  ),
)

const fromOptions = computed(() => fromAccounts.value.map((account) => ({
  value: account.id,
  label: `${account.name} · ${formatPrice(account.balance, account.currency)}`,
})))

const toOptions = computed(() => toAccounts.value.map((account) => ({
  value: account.id,
  label: `${account.name} · ${formatPrice(account.balance, account.currency)}`,
})))

function pairRateFromStandardRate(fromCurrency: string, toCurrency: string, standardRateRaw: string): number {
  const standardRate = Number.parseFloat(standardRateRaw)
  if (!Number.isFinite(standardRate) || standardRate <= 0) return 0
  if (fromCurrency === toCurrency) return 1
  if (fromCurrency === 'USD' && toCurrency === 'UZS') return standardRate
  if (fromCurrency === 'UZS' && toCurrency === 'USD') return 1 / standardRate
  return 0
}

const pairRate = computed(() => {
  if (!fromAccount.value || !toAccount.value) return 0
  return pairRateFromStandardRate(fromAccount.value.currency, toAccount.value.currency, latestUsdUzsRate.value)
})

const fromAmountNumber = computed(() => {
  const value = Number.parseFloat(String(fromAmount.value).replace(',', '.'))
  return Number.isFinite(value) && value > 0 ? value : 0
})

const previewToAmount = computed(() => fromAmountNumber.value * pairRate.value)

function normalizePair(): void {
  const preferredTo = props.toAccountId
    ? toAccounts.value.find((account) => account.id === props.toAccountId)
    : null
  toAccountId.value = preferredTo?.id ?? toAccounts.value[0]?.id ?? null
  fromAccountId.value = fromAccounts.value[0]?.id ?? null
}

watch(() => props.open, async (open) => {
  if (!open) return
  error.value = null
  notes.value = ''
  fromAmount.value = props.defaultAmount != null ? String(props.defaultAmount) : ''
  await loadLatestUsdUzsRate()
  normalizePair()
})

watch(toAccountId, () => {
  if (!props.open) return
  if (!fromAccounts.value.some((account) => account.id === fromAccountId.value)) {
    fromAccountId.value = fromAccounts.value[0]?.id ?? null
  }
})

function resetForm(): void {
  fromAccountId.value = null
  toAccountId.value = null
  fromAmount.value = ''
  notes.value = ''
  error.value = null
}

async function submit(): Promise<void> {
  error.value = null
  if (!fromAccount.value || !toAccount.value) {
    error.value = 'Выберите кассы для обмена'
    return
  }
  if (fromAmountNumber.value <= 0) {
    error.value = 'Введите сумму больше 0'
    return
  }
  if (pairRate.value <= 0) {
    error.value = 'Не удалось определить курс'
    return
  }
  isSaving.value = true
  try {
    await createCurrencyExchange({
      from_account_id: fromAccount.value.id,
      to_account_id: toAccount.value.id,
      from_amount: fromAmountNumber.value.toFixed(2),
      rate: pairRate.value.toFixed(6),
      notes: notes.value.trim(),
    })
    toast.success('Обмен выполнен')
    resetForm()
    emit('exchanged')
  } catch (submitError: unknown) {
    error.value = submitError instanceof Error ? submitError.message : 'Ошибка при обмене'
  } finally {
    isSaving.value = false
  }
}

function onClose(): void {
  resetForm()
  emit('close')
}
</script>

<template>
  <AppBottomSheet :open="props.open" title="Обмен валют" @close="onClose">
    <div class="flex flex-col gap-4 p-4">
      <div class="rounded-xl bg-muted/60 px-3.5 py-3">
        <p class="text-sm font-medium text-foreground">Обмен между кассами</p>
        <p class="mt-1 text-sm leading-relaxed text-muted-foreground">
          Деньги спишутся из одной кассы и поступят в кассу нужной валюты.
        </p>
      </div>

      <div class="flex flex-col gap-1.5">
        <span class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Из кассы</span>
        <BaseSelect
          :model-value="fromAccountId"
          :options="fromOptions"
          title="Из кассы"
          placeholder="Выберите кассу"
          @update:model-value="(value) => (fromAccountId = value as number | null)"
        />
      </div>

      <div class="flex flex-col gap-1.5">
        <span class="text-xs font-medium uppercase tracking-wide text-muted-foreground">В кассу</span>
        <BaseSelect
          :model-value="toAccountId"
          :options="toOptions"
          title="В кассу"
          placeholder="Выберите кассу"
          @update:model-value="(value) => (toAccountId = value as number | null)"
        />
      </div>

      <div class="flex flex-col gap-1.5">
        <span class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Сумма списания</span>
        <Input v-model="fromAmount" type="number" min="0.01" step="0.01" inputmode="decimal" class="h-11 tabular-nums" placeholder="0.00" />
      </div>

      <div class="flex items-center justify-between gap-3 rounded-xl border border-border px-3.5 py-3">
        <span class="text-sm text-muted-foreground">Поступит</span>
        <span class="text-sm font-semibold tabular-nums text-foreground">
          {{ formatPrice(previewToAmount, toAccount?.currency ?? (targetCurrency || 'UZS')) }}
        </span>
      </div>

      <div class="flex flex-col gap-1.5">
        <span class="text-xs font-medium uppercase tracking-wide text-muted-foreground">Комментарий</span>
        <Input v-model="notes" type="text" class="h-11" placeholder="Необязательно" />
      </div>

      <p v-if="error" class="text-sm text-destructive">{{ error }}</p>

      <Button class="h-11" :disabled="isSaving || !fromAccount || !toAccount || fromAmountNumber <= 0" @click="submit">
        <RefreshCcw v-if="isSaving" data-icon="inline-start" />
        <ArrowRightLeft v-else data-icon="inline-start" />
        {{ isSaving ? 'Сохранение…' : 'Обменять' }}
      </Button>
    </div>
  </AppBottomSheet>
</template>
