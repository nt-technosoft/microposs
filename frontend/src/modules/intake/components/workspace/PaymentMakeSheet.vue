<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useRouter } from 'vue-router'
import { AlertCircle, ArrowRight } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { formatPrice } from '@/utils/currency'
import { fetchCashAccounts, type CashAccountRecord } from '@/api/finance'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

const props = defineProps<{
  open: boolean
  procurement: ProcurementWorkspacePayload
  defaultAmount?: string
  paymentType: 'cost' | 'payable' | 'schedule-entry'
  payableId?: number
  scheduleEntryId?: number
  itemIds?: number[]
  expenseIds?: number[]
  currency?: string
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  dispatch: [actionKey: string, payload: Record<string, unknown>]
}>()

const router = useRouter()

const settlement = computed(() => props.procurement.documents.settlement)
const obligationCurrency = computed(() =>
  (props.currency ?? settlement.value?.currency_of_obligation ?? props.procurement.documents.payment_status?.currency ?? 'UZS').toUpperCase()
)

const amount = ref('')
const notes = ref('')
const cashAccountId = ref<number | null>(null)
const cashAccounts = ref<CashAccountRecord[]>([])
const isLoadingAccounts = ref(false)

// Operating cash only — agreement capital pools are restricted partnership
// funds and must never be a source for paying a procurement cost here.
const operatingAccounts = computed(() =>
  cashAccounts.value.filter((a) => a.kind !== 'agreement_capital'),
)
const selectedAccount = computed(() =>
  operatingAccounts.value.find((a) => a.id === cashAccountId.value) ?? null
)
const currencyMismatch = computed(() =>
  !!selectedAccount.value &&
  selectedAccount.value.currency.toUpperCase() !== obligationCurrency.value
)

async function loadAccounts(): Promise<void> {
  isLoadingAccounts.value = true
  try { cashAccounts.value = await fetchCashAccounts() }
  catch { cashAccounts.value = [] }
  finally { isLoadingAccounts.value = false }
}

watch(() => props.open, (isOpen) => {
  if (!isOpen) return
  amount.value = props.defaultAmount ?? ''
  notes.value = ''
  cashAccountId.value = operatingAccounts.value[0]?.id ?? null
  if (!cashAccounts.value.length) loadAccounts()
})

function openExchange(): void {
  const remaining = settlement.value?.remaining_amount ?? ''
  router.push({
    path: '/finance/currency-exchange',
    query: {
      from_currency: selectedAccount.value?.currency ?? 'UZS',
      to_currency: obligationCurrency.value,
      amount: String(remaining),
    },
  })
  emit('update:open', false)
}

function onSave(): void {
  const base: Record<string, unknown> = {
    cash_account_id: cashAccountId.value,
    amount: parseFloat(amount.value) || 0,
    currency: obligationCurrency.value,
    fx_rate: '1',
    notes: notes.value,
  }
  if (props.paymentType === 'cost') {
    const payload: Record<string, unknown> = { ...base }
    if (props.itemIds?.length) payload.item_ids = props.itemIds
    if (props.expenseIds?.length) payload.expense_ids = props.expenseIds
    emit('dispatch', 'PAY_COSTS', payload)
  } else {
    emit('dispatch', 'PAY_SUPPLIER_PAYABLE', {
      ...base,
      payable_id: props.payableId,
      ...(props.scheduleEntryId ? { schedule_entry_id: props.scheduleEntryId } : {}),
    })
  }
  emit('update:open', false)
}

const canSave = () =>
  !!(amount.value && parseFloat(amount.value) > 0 && cashAccountId.value && !currencyMismatch.value)
</script>

<template>
  <AppBottomSheet :open="open" title="Платёж" @close="emit('update:open', false)">
    <div class="flex flex-col gap-4">
      <!-- Сумма -->
      <div class="flex flex-col gap-1.5">
        <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Сумма</span>
        <div class="flex items-center gap-2 rounded-[12px] border border-neutral-200 px-4 py-3 focus-within:border-green-400">
          <input
            v-model="amount"
            type="number"
            min="0"
            step="0.01"
            inputmode="decimal"
            placeholder="0"
            class="min-w-0 flex-1 bg-transparent text-2xl font-semibold tabular-nums text-foreground outline-none placeholder:text-neutral-300"
          />
          <span class="shrink-0 text-sm font-medium text-neutral-500">{{ obligationCurrency }}</span>
        </div>
      </div>

      <!-- Касса -->
      <div class="flex flex-col gap-1.5">
        <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Откуда платим</span>
        <p v-if="isLoadingAccounts" class="text-sm text-neutral-500">Загрузка…</p>
        <p v-else-if="!operatingAccounts.length" class="text-sm text-neutral-500">Нет активных касс</p>
        <div v-else class="flex flex-col gap-2">
          <button
            v-for="acc in operatingAccounts"
            :key="acc.id"
            type="button"
            :class="cn(
              'flex w-full items-center justify-between gap-3 rounded-[10px] border px-3.5 py-3 transition-colors',
              acc.id === cashAccountId ? 'border-primary bg-primary/5' : 'border-neutral-200 hover:bg-neutral-50',
            )"
            @click="cashAccountId = acc.id"
          >
            <span class="min-w-0 truncate text-sm font-medium text-foreground">{{ acc.name }}</span>
            <span class="shrink-0 text-xs tabular-nums text-neutral-500">{{ formatPrice(parseFloat(acc.balance) || 0, acc.currency) }}</span>
          </button>
        </div>
      </div>

      <!-- Currency mismatch -->
      <div v-if="currencyMismatch" class="flex flex-col gap-2 rounded-[10px] border border-warning/30 bg-warning/10 px-3.5 py-3 text-sm text-foreground">
        <div class="flex items-start gap-2">
          <AlertCircle class="mt-0.5 size-4 shrink-0 text-warning" />
          <span>Касса в {{ selectedAccount?.currency }}, обязательство в {{ obligationCurrency }}. Сначала конвертируйте валюту.</span>
        </div>
        <Button variant="outline" size="sm" class="h-9 self-start gap-1" @click="openExchange">
          Конвертировать
          <ArrowRight class="size-4" />
        </Button>
      </div>

      <!-- Примечание -->
      <div class="flex flex-col gap-1.5">
        <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Примечание (необязательно)</span>
        <Input v-model="notes" type="text" class="h-11" placeholder="Комментарий к платежу" />
      </div>

      <Button class="h-12 w-full text-base" :disabled="!canSave()" @click="onSave">
        Сохранить платёж
      </Button>
    </div>
  </AppBottomSheet>
</template>
