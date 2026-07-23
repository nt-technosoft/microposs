<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { CheckCircle2, Circle } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import MoneyCurrencyInput from '@/components/forms/MoneyCurrencyInput.vue'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { useFxRate } from '@/composables/useFxRate'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

type Expense = ProcurementWorkspacePayload['documents']['expenses'][number]
type SavePayload = { id?: number; expense_type: string; amount: number; currency: string; fx_rate: string; allocation_method: string; target_item_ids: number[] }

const EXPENSE_TYPES = [
  { key: 'LOGISTICS', label: 'Логистика' },
  { key: 'CUSTOMS', label: 'Таможня' },
  { key: 'FEE', label: 'Комиссия' },
  { key: 'OTHER', label: 'Прочее' },
] as const

const ALLOC_METHODS = [
  { key: 'BY_VALUE', label: 'По стоимости' },
  { key: 'BY_QUANTITY', label: 'По количеству' },
] as const

const props = defineProps<{ open: boolean; procurement: ProcurementWorkspacePayload; editingExpenseId: number | null }>()
const emit = defineEmits<{ 'update:open': [value: boolean]; save: [payload: SavePayload]; delete: [expenseId: number] }>()

const expenseType = ref('LOGISTICS')
const amount = ref('')
const currency = ref<'UZS' | 'USD'>('UZS')
const fxRateLocal = ref('1')
const allocMethod = ref('BY_VALUE')
const targetScope = ref<'all' | 'selected'>('all')
const selectedTargets = ref<number[]>([])

const {
  rate: fetchedFx,
  load: loadFx,
  isLoading: fxLoading,
  error: fxError,
} = useFxRate()

const editExpense = computed<Expense | null>(() =>
  props.editingExpenseId
    ? (props.procurement.documents.expenses.find((e) => e.id === props.editingExpenseId) ?? null)
    : null,
)
const canMutate = computed(() =>
  props.procurement.status === 'OPEN' && (!editExpense.value || !editExpense.value.locked_reason),
)
// Defensive: never offer soft-deleted (CANCELLED) goods as expense targets
// (the payload already excludes them at the source).
const items = computed(() =>
  props.procurement.documents.items.filter((it) => it.lifecycle_state !== 'CANCELLED'),
)
const targetableItems = computed(() =>
  canMutate.value ? items.value.filter((it) => it.lifecycle_state === 'DRAFT') : items.value,
)
const hasLockedItems = computed(() => targetableItems.value.length !== items.value.length)
const lockedCurrency = computed<'UZS' | 'USD' | null>(() => {
  const currencies = new Set(
    [
      ...props.procurement.documents.items
        .filter((item) => item.lifecycle_state !== 'CANCELLED')
        .map((item) => item.currency === 'USD' ? 'USD' : 'UZS'),
      ...props.procurement.documents.expenses
        .filter((expense) => expense.lifecycle_state !== 'CANCELLED' && expense.id !== props.editingExpenseId)
        .map((expense) => expense.currency === 'USD' ? 'USD' : 'UZS'),
    ],
  )
  return currencies.size === 1 ? ([...currencies][0] as 'UZS' | 'USD') : null
})
const allowedCurrencies = computed<Array<'UZS' | 'USD'>>(() =>
  lockedCurrency.value ? [lockedCurrency.value] : ['USD', 'UZS'],
)
const usdFxMissing = computed(() =>
  currency.value === 'USD'
  && (!fxRateLocal.value || !Number.isFinite(Number.parseFloat(fxRateLocal.value)) || Number.parseFloat(fxRateLocal.value) <= 1),
)

watch(fetchedFx, (r) => { if (r) fxRateLocal.value = r })
watch(currency, (cur) => {
  if (cur === 'USD') void ensureUsdFxRate()
  else fxRateLocal.value = '1'
})

async function ensureUsdFxRate(): Promise<boolean> {
  if (currency.value !== 'USD') return true
  const parsed = Number.parseFloat(fxRateLocal.value)
  if (Number.isFinite(parsed) && parsed > 1) return true
  try {
    const loaded = await loadFx()
    fxRateLocal.value = loaded
    const nextParsed = Number.parseFloat(loaded)
    return Number.isFinite(nextParsed) && nextParsed > 1
  } catch {
    return false
  }
}

watch(() => props.open, (isOpen) => {
  if (!isOpen) return
  const ex = editExpense.value
  if (ex) {
    expenseType.value = ex.expense_type; amount.value = ex.amount
    currency.value = ex.currency === 'USD' ? 'USD' : 'UZS'; fxRateLocal.value = ex.fx_rate
    allocMethod.value = ex.allocation_method
    if (ex.target_item_ids.length) { targetScope.value = 'selected'; selectedTargets.value = [...ex.target_item_ids] }
    else { targetScope.value = 'all'; selectedTargets.value = [] }
  } else {
    expenseType.value = 'LOGISTICS'; amount.value = ''; currency.value = lockedCurrency.value ?? (props.procurement.documents.procurement.primary_currency === 'USD' ? 'USD' : 'UZS')
    fxRateLocal.value = '1'; allocMethod.value = 'BY_VALUE'
    void ensureUsdFxRate()
    targetScope.value = hasLockedItems.value ? 'selected' : 'all'
    selectedTargets.value = hasLockedItems.value ? targetableItems.value.map((it) => it.id) : []
  }
})

function toggleTarget(itemId: number): void {
  if (!canMutate.value) return
  selectedTargets.value = selectedTargets.value.includes(itemId)
    ? selectedTargets.value.filter((id) => id !== itemId)
    : [...selectedTargets.value, itemId]
}

function toggleAllTargets(): void {
  if (!canMutate.value) return
  selectedTargets.value = selectedTargets.value.length === targetableItems.value.length
    ? []
    : targetableItems.value.map((it) => it.id)
}

async function onSave(): Promise<void> {
  if (!canMutate.value) return
  if (!await ensureUsdFxRate()) return
  emit('save', {
    ...(props.editingExpenseId ? { id: props.editingExpenseId } : {}),
    expense_type: expenseType.value,
    amount: parseFloat(amount.value) || 0,
    currency: currency.value,
    fx_rate: fxRateLocal.value,
    allocation_method: allocMethod.value,
    target_item_ids: targetScope.value === 'selected' ? [...selectedTargets.value] : [],
  })
  emit('update:open', false)
}

function onDelete(): void {
  if (!canMutate.value) return
  if (!props.editingExpenseId) return
  emit('delete', props.editingExpenseId)
  emit('update:open', false)
}
</script>

<template>
  <AppBottomSheet :open="open" title="Расход" @close="emit('update:open', false)">
    <div class="flex flex-col gap-4">
      <!-- Тип расхода -->
      <div class="flex flex-col gap-1.5">
        <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Тип расхода</span>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="t in EXPENSE_TYPES"
            :key="t.key"
            type="button"
            :class="cn(
              'rounded-full border px-3 py-1.5 text-sm transition-colors',
              expenseType === t.key ? 'border-primary bg-primary/5 font-medium text-foreground' : 'border-neutral-200 text-neutral-600 hover:bg-neutral-50',
              !canMutate && 'cursor-default opacity-70 hover:bg-transparent',
            )"
            :disabled="!canMutate"
            @click="expenseType = t.key"
          >{{ t.label }}</button>
        </div>
      </div>

      <!-- Сумма -->
      <div class="flex flex-col gap-1.5">
        <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Сумма</span>
        <MoneyCurrencyInput v-model:model-value="amount" v-model:currency="currency" :currencies="allowedCurrencies" :disabled="!canMutate" />
        <p v-if="lockedCurrency" class="text-xs text-neutral-400">Валюта прихода зафиксирована: {{ lockedCurrency }}.</p>
        <div
          v-if="currency === 'USD' && usdFxMissing && fxError"
          class="rounded-[10px] bg-amber-50 px-3 py-2 text-xs text-amber-700"
        >
          <p>{{ fxError || 'Для USD-расхода нужен курс USD/UZS. Без курса приход нельзя корректно сверить.' }}</p>
          <button
            v-if="canMutate"
            type="button"
            class="mt-2 font-medium underline underline-offset-2"
            @click="void ensureUsdFxRate()"
          >
            Получить курс автоматически
          </button>
        </div>
      </div>

      <!-- Метод распределения -->
      <div class="flex flex-col gap-1.5">
        <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Распределить по товарам</span>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="m in ALLOC_METHODS"
            :key="m.key"
            type="button"
            :class="cn(
              'rounded-full border px-3 py-1.5 text-sm transition-colors',
              allocMethod === m.key ? 'border-primary bg-primary/5 font-medium text-foreground' : 'border-neutral-200 text-neutral-600 hover:bg-neutral-50',
              !canMutate && 'cursor-default opacity-70 hover:bg-transparent',
            )"
            :disabled="!canMutate"
            @click="allocMethod = m.key"
          >{{ m.label }}</button>
        </div>
      </div>

      <!-- Распределить на -->
      <div class="flex flex-col gap-1.5">
        <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">На какие товары</span>
        <div class="flex flex-wrap gap-2">
          <button
            type="button"
            :disabled="!canMutate || hasLockedItems"
            :class="cn(
              'rounded-full border px-3 py-1.5 text-sm transition-colors',
              targetScope === 'all' ? 'border-primary bg-primary/5 font-medium text-foreground' : 'border-neutral-200 text-neutral-600 hover:bg-neutral-50',
              (!canMutate || hasLockedItems) && 'cursor-not-allowed opacity-40 hover:bg-transparent',
            )"
            @click="targetScope = 'all'"
          >Все товары</button>
          <button
            type="button"
            :disabled="!canMutate || !targetableItems.length"
            :class="cn(
              'rounded-full border px-3 py-1.5 text-sm transition-colors',
              targetScope === 'selected' ? 'border-primary bg-primary/5 font-medium text-foreground' : 'border-neutral-200 text-neutral-600 hover:bg-neutral-50',
              (!canMutate || !targetableItems.length) && 'cursor-not-allowed opacity-40 hover:bg-transparent',
            )"
            @click="targetScope = 'selected'"
          >Выбранные</button>
        </div>
        <p v-if="canMutate && hasLockedItems" class="text-xs text-neutral-400">
          Уже оплаченные или принятые товары нельзя добавлять в новые расходы.
        </p>
      </div>

      <template v-if="targetScope === 'selected' && targetableItems.length">
        <div class="flex items-center justify-between">
          <span class="text-xs text-neutral-500">Выбрано {{ selectedTargets.length }} из {{ targetableItems.length }}</span>
          <button v-if="canMutate" type="button" class="text-xs font-medium text-green-700" @click="toggleAllTargets">
            {{ selectedTargets.length === targetableItems.length ? 'Снять все' : 'Выбрать все' }}
          </button>
        </div>
        <div class="flex max-h-[40vh] flex-col gap-1 overflow-y-auto">
          <button
            v-for="item in targetableItems"
            :key="item.id"
            type="button"
            :disabled="!canMutate"
            :class="cn(
              'flex w-full items-center gap-2.5 rounded-lg border px-3 py-1.5 text-left transition-colors',
              selectedTargets.includes(item.id) ? 'border-primary bg-primary/5' : 'border-neutral-200 hover:bg-neutral-50',
              !canMutate && 'cursor-default opacity-80 hover:bg-transparent',
            )"
            @click="toggleTarget(item.id)"
          >
            <component
              :is="selectedTargets.includes(item.id) ? CheckCircle2 : Circle"
              :class="cn('size-4 shrink-0', selectedTargets.includes(item.id) ? 'text-primary' : 'text-neutral-300')"
            />
            <span class="min-w-0 flex-1 truncate text-sm text-foreground">{{ item.product_variant_name }}</span>
            <span class="shrink-0 text-xs tabular-nums text-neutral-500">{{ Math.round(parseFloat(item.quantity) || 0) }} шт</span>
          </button>
        </div>
      </template>

      <div class="flex flex-col gap-2 pt-1">
        <p v-if="!canMutate" class="rounded-[10px] bg-neutral-50 px-3.5 py-3 text-sm text-neutral-500">
          Расход уже участвует в оплате или приёмке, поэтому доступен только для просмотра.
        </p>
        <Button v-if="canMutate" class="h-12 w-full text-base" :disabled="!amount || fxLoading" @click="onSave">Сохранить</Button>
        <button
          v-if="canMutate && editingExpenseId"
          type="button"
          class="h-11 rounded-[10px] border border-negative/30 text-sm font-medium text-negative transition-colors hover:bg-negative/5"
          @click="onDelete"
        >
          Удалить расход
        </button>
      </div>
    </div>
  </AppBottomSheet>
</template>
