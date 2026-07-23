<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  AlertTriangle,
  CheckCircle2,
  CircleSlash,
  Package,
  ReceiptText,
  RotateCcw,
  Trash2,
} from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import MoneyCurrencyInput from '@/components/forms/MoneyCurrencyInput.vue'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

type AmendmentTarget = 'items' | 'expenses'
type CurrencyCode = 'USD' | 'UZS'
type ProcurementItem = ProcurementWorkspacePayload['documents']['items'][number]
type ProcurementExpense = ProcurementWorkspacePayload['documents']['expenses'][number]

type DraftItem = {
  id: number
  product_variant_id: number
  name: string
  quantity: string
  unit_purchase_price: string
  currency: CurrencyCode
  fx_rate: string
  cancelled: boolean
}

type DraftExpense = {
  id: number
  expense_type: string
  amount: string
  currency: CurrencyCode
  fx_rate: string
  allocation_method: string
  target_item_ids: number[]
  cancelled: boolean
}

const props = defineProps<{
  open: boolean
  procurement: ProcurementWorkspacePayload
  target: AmendmentTarget
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  dispatch: [action: string, payload: Record<string, unknown>]
}>()

const activeTarget = ref<AmendmentTarget>(props.target)
const reason = ref('')
const localError = ref<string | null>(null)
const draftItems = ref<DraftItem[]>([])
const draftExpenses = ref<DraftExpense[]>([])
const allowedCurrencies: CurrencyCode[] = ['USD', 'UZS']

const itemById = computed(() => new Map(props.procurement.documents.items.map((item) => [item.id, item])))
const expenseById = computed(() => new Map(props.procurement.documents.expenses.map((expense) => [expense.id, expense])))

const targetOptions = computed(() =>
  props.procurement.documents.items.filter((item) => item.lifecycle_state !== 'CANCELLED'),
)

const editableItems = computed(() =>
  draftItems.value.filter((item) => isEditableItem(itemById.value.get(item.id))),
)

const lockedItems = computed(() =>
  draftItems.value.filter((item) => !isEditableItem(itemById.value.get(item.id))),
)

const editableExpenses = computed(() =>
  draftExpenses.value.filter((expense) => isEditableExpense(expenseById.value.get(expense.id))),
)

const lockedExpenses = computed(() =>
  draftExpenses.value.filter((expense) => {
    const source = expenseById.value.get(expense.id)
    return source?.lifecycle_state !== 'CANCELLED' && !isEditableExpense(source)
  }),
)

const title = computed(() =>
  activeTarget.value === 'items' ? 'Корректировка товаров' : 'Корректировка расходов',
)

const canSubmit = computed(() => {
  if (!reason.value.trim()) return false
  return activeTarget.value === 'items'
    ? editableItems.value.length > 0
    : editableExpenses.value.length > 0
})

watch(
  () => props.open,
  (open) => {
    if (!open) return
    activeTarget.value = props.target
    reason.value = ''
    localError.value = null
    resetDrafts()
  },
  { immediate: true },
)

watch(
  () => props.target,
  (target) => {
    activeTarget.value = target
    localError.value = null
  },
)

watch(
  () => props.procurement,
  () => resetDrafts(),
  { deep: true },
)

function resetDrafts(): void {
  draftItems.value = props.procurement.documents.items.map((item) => ({
    id: item.id,
    product_variant_id: item.product_variant_id,
    name: item.product_variant_name,
    quantity: item.quantity,
    unit_purchase_price: item.unit_purchase_price,
    currency: normalizeCurrency(item.currency),
    fx_rate: item.fx_rate,
    cancelled: false,
  }))

  draftExpenses.value = props.procurement.documents.expenses.map((expense) => ({
    id: expense.id,
    expense_type: expense.expense_type,
    amount: expense.amount,
    currency: normalizeCurrency(expense.currency),
    fx_rate: expense.fx_rate,
    allocation_method: expense.allocation_method,
    target_item_ids: [...expense.target_item_ids],
    cancelled: false,
  }))
}

function normalizeCurrency(value: string): CurrencyCode {
  return value?.toUpperCase() === 'USD' ? 'USD' : 'UZS'
}

function formatMoney(value: string, currency: string): string {
  const amount = Number.parseFloat(value) || 0
  return `${amount.toLocaleString('ru-RU', { maximumFractionDigits: 2 })} ${currency}`
}

function close(): void {
  emit('update:open', false)
}

function isEditableItem(item?: ProcurementItem): boolean {
  if (!item) return false
  return !['RECEIVED', 'CANCELLED'].includes(item.lifecycle_state)
}

function isEditableExpense(expense?: ProcurementExpense): boolean {
  if (!expense) return false
  return !['RECEIVED', 'CANCELLED'].includes(expense.lifecycle_state)
}

function canCancelItem(item?: ProcurementItem): boolean {
  if (!item) return false
  return item.lifecycle_state === 'DRAFT' && item.payment_state !== 'PAID'
}

function canCancelExpense(expense?: ProcurementExpense): boolean {
  if (!expense) return false
  return expense.lifecycle_state === 'DRAFT' && expense.payment_state !== 'PAID'
}

function stateLabel(state?: string): string {
  if (state === 'DRAFT') return 'черновик'
  if (state === 'READY_FOR_RECEIVE') return 'зафиксировано'
  if (state === 'RECEIVED') return 'принято'
  if (state === 'CANCELLED') return 'отменено'
  return state ?? 'нет статуса'
}

function expenseTypeLabel(type: string): string {
  if (type === 'CUSTOMS') return 'Таможня'
  if (type === 'DELIVERY') return 'Доставка'
  if (type === 'OTHER') return 'Расход'
  return type
}

function allocationLabel(method: string): string {
  if (method === 'BY_QUANTITY') return 'по количеству'
  return 'по стоимости'
}

function targetLabel(expense: DraftExpense): string {
  if (expense.target_item_ids.length === 0) return 'все товары'
  return `${expense.target_item_ids.length} поз.`
}

function toggleItemCancel(item: DraftItem): void {
  if (!canCancelItem(itemById.value.get(item.id))) return
  item.cancelled = !item.cancelled
}

function toggleExpenseCancel(expense: DraftExpense): void {
  if (!canCancelExpense(expenseById.value.get(expense.id))) return
  expense.cancelled = !expense.cancelled
}

function toggleExpenseTarget(expense: DraftExpense, itemId: number): void {
  if (expense.target_item_ids.length === 0) {
    expense.target_item_ids = targetOptions.value.map((item) => item.id)
  }

  const exists = expense.target_item_ids.includes(itemId)
  expense.target_item_ids = exists
    ? expense.target_item_ids.filter((id) => id !== itemId)
    : [...expense.target_item_ids, itemId]
}

function setExpenseAllTargets(expense: DraftExpense): void {
  expense.target_item_ids = []
}

function isTargetSelected(expense: DraftExpense, itemId: number): boolean {
  return expense.target_item_ids.length === 0 || expense.target_item_ids.includes(itemId)
}

function buildItemPayload(): Record<string, unknown>[] {
  return editableItems.value.map((item) => {
    if (item.cancelled) {
      return { id: item.id, _cancel: true }
    }

    return {
      id: item.id,
      product_variant_id: item.product_variant_id,
      quantity: item.quantity,
      unit_purchase_price: item.unit_purchase_price,
      currency: item.currency,
      fx_rate: item.fx_rate,
    }
  })
}

function buildExpensePayload(): Record<string, unknown>[] {
  return editableExpenses.value.map((expense) => {
    if (expense.cancelled) {
      return { id: expense.id, _cancel: true }
    }

    return {
      id: expense.id,
      expense_type: expense.expense_type,
      amount: expense.amount,
      currency: expense.currency,
      fx_rate: expense.fx_rate,
      allocation_method: expense.allocation_method,
      target_item_ids: expense.target_item_ids,
    }
  })
}

function submit(): void {
  localError.value = null
  const trimmedReason = reason.value.trim()

  if (!trimmedReason) {
    localError.value = 'Укажите причину корректировки.'
    return
  }

  if (activeTarget.value === 'items') {
    if (!editableItems.value.length) {
      localError.value = 'Нет товаров, доступных для корректировки.'
      return
    }
    emit('dispatch', 'AMEND_ITEMS', { items: buildItemPayload(), reason: trimmedReason })
    close()
    return
  }

  if (!editableExpenses.value.length) {
    localError.value = 'Нет расходов, доступных для корректировки.'
    return
  }
  emit('dispatch', 'AMEND_EXPENSES', { expenses: buildExpensePayload(), reason: trimmedReason })
  close()
}
</script>

<template>
  <AppBottomSheet :open="open" :title="title" @close="close">
    <div class="flex flex-col gap-4">
      <Alert class="border-primary/20 bg-primary/5 text-foreground">
        <AlertTriangle class="size-4 text-primary" />
        <AlertDescription class="text-sm leading-snug">
          Корректировка создаёт отдельный документ. Уже принятые строки остаются только для просмотра.
        </AlertDescription>
      </Alert>

      <div class="flex flex-col gap-1.5">
        <span class="px-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Что корректируем</span>
        <div class="grid grid-cols-2 gap-1 rounded-[14px] border border-border bg-muted/70 p-1">
        <Button
          type="button"
          variant="ghost"
          :class="cn(
            'h-11 rounded-[10px] gap-2 text-sm font-semibold transition-all',
            activeTarget === 'items'
              ? 'border border-border bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:bg-background/60',
          )"
          @click="activeTarget = 'items'; localError = null"
        >
          <Package data-icon="inline-start" />
          Товары
          <Badge :variant="activeTarget === 'items' ? 'secondary' : 'outline'" class="ml-1">{{ editableItems.length }}</Badge>
        </Button>
        <Button
          type="button"
          variant="ghost"
          :class="cn(
            'h-11 rounded-[10px] gap-2 text-sm font-semibold transition-all',
            activeTarget === 'expenses'
              ? 'border border-border bg-background text-foreground shadow-sm'
              : 'text-muted-foreground hover:bg-background/60',
          )"
          @click="activeTarget = 'expenses'; localError = null"
        >
          <ReceiptText data-icon="inline-start" />
          Расходы
          <Badge :variant="activeTarget === 'expenses' ? 'secondary' : 'outline'" class="ml-1">{{ editableExpenses.length }}</Badge>
        </Button>
        </div>
      </div>

      <div v-if="activeTarget === 'items'" class="flex flex-col gap-3">
        <div v-if="editableItems.length" class="flex flex-col gap-2">
          <div
            v-for="item in editableItems"
            :key="item.id"
            :class="cn(
              'rounded-2xl border border-border bg-card p-3 transition-colors',
              item.cancelled && 'border-destructive/30 bg-destructive/5',
            )"
          >
            <div class="mb-3 flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div :class="cn('truncate text-base font-semibold', item.cancelled && 'line-through text-muted-foreground')">
                  {{ item.name }}
                </div>
                <div class="mt-1 flex flex-wrap gap-1.5">
                  <Badge variant="outline">{{ stateLabel(itemById.get(item.id)?.lifecycle_state) }}</Badge>
                  <Badge variant="secondary">{{ item.currency }}</Badge>
                </div>
              </div>
              <Button
                v-if="canCancelItem(itemById.get(item.id))"
                type="button"
                :variant="item.cancelled ? 'outline' : 'destructive'"
                size="sm"
                @click="toggleItemCancel(item)"
              >
                <RotateCcw v-if="item.cancelled" class="size-4" />
                <Trash2 v-else class="size-4" />
                {{ item.cancelled ? 'Вернуть' : 'Убрать' }}
              </Button>
              <Badge v-else variant="secondary">нельзя удалить</Badge>
            </div>

            <div class="grid grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] gap-2">
              <label class="flex flex-col gap-1">
                <span class="text-xs font-medium uppercase text-muted-foreground">Кол-во</span>
                <Input v-model="item.quantity" inputmode="decimal" :disabled="item.cancelled" class="h-12 rounded-[10px] text-base tabular-nums" />
              </label>
              <label class="flex flex-col gap-1">
                <span class="text-xs font-medium uppercase text-muted-foreground">Цена закупки</span>
                <MoneyCurrencyInput
                  v-model:model-value="item.unit_purchase_price"
                  v-model:currency="item.currency"
                  :currencies="allowedCurrencies"
                  :disabled="item.cancelled"
                  size="lg"
                  aria-label="Цена закупки"
                />
              </label>
            </div>
          </div>
        </div>

        <div v-if="lockedItems.length" class="rounded-2xl border border-dashed border-border bg-muted/30 p-3">
          <div class="mb-2 flex items-center gap-2 text-sm font-semibold text-muted-foreground">
            <CircleSlash class="size-4" />
            Зафиксировано
          </div>
          <div class="flex flex-col gap-2">
            <div
              v-for="item in lockedItems"
              :key="item.id"
              class="flex items-center justify-between gap-3 rounded-xl border border-border bg-background px-3 py-2.5"
            >
              <div class="min-w-0">
                <div class="truncate text-sm font-semibold text-foreground">{{ item.name }}</div>
                <div class="mt-0.5 text-xs text-muted-foreground">
                  {{ item.quantity }} шт. · {{ formatMoney(item.unit_purchase_price, item.currency) }}
                </div>
              </div>
              <Badge variant="outline" class="shrink-0">{{ stateLabel(itemById.get(item.id)?.lifecycle_state) }}</Badge>
            </div>
          </div>
        </div>
      </div>

      <div v-else class="flex flex-col gap-3">
        <div v-if="editableExpenses.length" class="flex flex-col gap-2">
          <div
            v-for="expense in editableExpenses"
            :key="expense.id"
            :class="cn(
              'rounded-2xl border border-border bg-card p-3 transition-colors',
              expense.cancelled && 'border-destructive/30 bg-destructive/5',
            )"
          >
            <div class="mb-3 flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div :class="cn('truncate text-base font-semibold', expense.cancelled && 'line-through text-muted-foreground')">
                  {{ expenseTypeLabel(expense.expense_type) }}
                </div>
                <div class="mt-1 flex flex-wrap gap-1.5">
                  <Badge variant="outline">{{ stateLabel(expenseById.get(expense.id)?.lifecycle_state) }}</Badge>
                  <Badge variant="secondary">{{ allocationLabel(expense.allocation_method) }}</Badge>
                  <Badge variant="secondary">{{ targetLabel(expense) }}</Badge>
                </div>
              </div>
              <Button
                v-if="canCancelExpense(expenseById.get(expense.id))"
                type="button"
                :variant="expense.cancelled ? 'outline' : 'destructive'"
                size="sm"
                @click="toggleExpenseCancel(expense)"
              >
                <RotateCcw v-if="expense.cancelled" class="size-4" />
                <Trash2 v-else class="size-4" />
                {{ expense.cancelled ? 'Вернуть' : 'Убрать' }}
              </Button>
              <Badge v-else variant="secondary">нельзя удалить</Badge>
            </div>

            <div class="grid grid-cols-1 gap-2">
              <label class="flex flex-col gap-1">
                <span class="text-xs font-medium uppercase text-muted-foreground">Сумма</span>
                <MoneyCurrencyInput
                  v-model:model-value="expense.amount"
                  v-model:currency="expense.currency"
                  :currencies="allowedCurrencies"
                  :disabled="expense.cancelled"
                  size="lg"
                  aria-label="Сумма расхода"
                />
              </label>
            </div>

            <div class="mt-3 flex flex-col gap-2">
              <div class="flex items-center justify-between gap-3">
                <span class="text-xs font-medium uppercase text-muted-foreground">К каким товарам</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  :disabled="expense.cancelled"
                  @click="setExpenseAllTargets(expense)"
                >
                  Все товары
                </Button>
              </div>
              <div class="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                <button
                  v-for="item in targetOptions"
                  :key="item.id"
                  type="button"
                  :disabled="expense.cancelled"
                  :class="cn(
                    'inline-flex min-h-9 max-w-full items-center gap-2 rounded-[10px] border px-2.5 py-1.5 text-left text-xs font-medium transition-colors',
                    isTargetSelected(expense, item.id)
                      ? 'border-primary/40 bg-primary/10 text-primary'
                      : 'border-border bg-background text-muted-foreground',
                    expense.cancelled && 'opacity-50',
                  )"
                  @click="toggleExpenseTarget(expense, item.id)"
                >
                  <CheckCircle2 v-if="isTargetSelected(expense, item.id)" class="size-3.5 shrink-0" />
                  <span v-else class="size-3.5 shrink-0 rounded-full border border-border" />
                  <span class="truncate">{{ item.product_variant_name }}</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        <div v-if="lockedExpenses.length" class="rounded-2xl border border-dashed border-border bg-muted/30 p-3">
          <div class="mb-2 flex items-center gap-2 text-sm font-semibold text-muted-foreground">
            <CircleSlash class="size-4" />
            Расходы уже зафиксированы
          </div>
          <p class="mb-3 text-sm leading-snug text-muted-foreground">
            Сейчас backend меняет только черновые расходы. Оплаченные или принятые расходы показаны без кнопок редактирования.
          </p>
          <div class="flex flex-col gap-2">
            <div
              v-for="expense in lockedExpenses"
              :key="expense.id"
              class="flex items-center justify-between gap-3 rounded-xl border border-border bg-background px-3 py-2.5"
            >
              <div class="min-w-0">
                <div class="truncate text-sm font-semibold text-foreground">{{ expenseTypeLabel(expense.expense_type) }}</div>
                <div class="mt-0.5 text-xs text-muted-foreground">
                  {{ allocationLabel(expense.allocation_method) }} · {{ targetLabel(expense) }}
                </div>
              </div>
              <div class="flex shrink-0 flex-col items-end gap-1">
                <span class="text-sm font-semibold tabular-nums text-foreground">{{ formatMoney(expense.amount, expense.currency) }}</span>
                <Badge variant="outline">{{ stateLabel(expenseById.get(expense.id)?.lifecycle_state) }}</Badge>
              </div>
            </div>
          </div>
        </div>
      </div>

      <label class="flex flex-col gap-1">
        <span class="text-xs font-medium uppercase text-muted-foreground">Причина</span>
        <Textarea
          v-model="reason"
          class="min-h-20 resize-none"
          placeholder="Например: исправили количество после сверки с поставщиком"
        />
      </label>

      <Alert v-if="localError" variant="destructive">
        <AlertTriangle class="size-4" />
        <AlertDescription>{{ localError }}</AlertDescription>
      </Alert>

      <div class="grid grid-cols-[0.9fr_1.1fr] gap-2 pt-1">
        <Button type="button" variant="outline" size="lg" class="h-11 rounded-xl" @click="close">
          Отмена
        </Button>
        <Button type="button" size="lg" class="h-11 rounded-xl" :disabled="!canSubmit" @click="submit">
          Сохранить
        </Button>
      </div>
    </div>
  </AppBottomSheet>
</template>
