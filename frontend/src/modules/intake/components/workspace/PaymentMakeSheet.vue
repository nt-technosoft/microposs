<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { AlertCircle, ArrowDownToLine, ArrowRightLeft, Repeat2 } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import CashDepositSheet from '@/modules/finance/views/CashDepositSheet.vue'
import CashTransferSheet from '@/modules/finance/views/CashTransferSheet.vue'
import CurrencyExchangeSheet from '@/modules/finance/views/CurrencyExchangeSheet.vue'
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

const settlement = computed(() => props.procurement.documents.settlement)
const obligationCurrency = computed(() =>
  (props.currency ?? settlement.value?.currency_of_obligation ?? props.procurement.documents.payment_status?.currency ?? 'UZS').toUpperCase()
)

const amount = ref('')
const notes = ref('')
const cashAccountId = ref<number | null>(null)
const cashAccounts = ref<CashAccountRecord[]>([])
const isLoadingAccounts = ref(false)
const depositSheetOpen = ref(false)
const exchangeSheetOpen = ref(false)
const transferSheetOpen = ref(false)
const transferSourceAccountId = ref<number | null>(null)

// Money discipline: an obligation is paid only from an operating cash register
// in the SAME currency. Agreement capital pools are restricted; mismatched
// currencies are never a source (no implicit conversion) — convert/top up first.
const operatingAccounts = computed(() =>
  cashAccounts.value.filter(
    (a) => a.kind !== 'agreement_capital' && a.kind !== 'fund_capital' &&
      (a.currency || 'UZS').toUpperCase() === obligationCurrency.value,
  ),
)
const selectedAccount = computed(() =>
  operatingAccounts.value.find((a) => a.id === cashAccountId.value) ?? null
)
const paymentTargetAccount = computed(() => selectedAccount.value ?? operatingAccounts.value[0] ?? null)
const insufficient = computed(() =>
  !!selectedAccount.value &&
  parseFloat(amount.value || '0') > parseFloat(selectedAccount.value.balance || '0')
)
const exchangeSourceAccounts = computed(() =>
  cashAccounts.value.filter(
    (a) =>
      a.is_active !== false &&
      a.kind !== 'agreement_capital' && a.kind !== 'fund_capital' &&
      (a.currency || 'UZS').toUpperCase() !== obligationCurrency.value &&
      parseFloat(a.balance || '0') > 0,
  ),
)
const transferSourceAccounts = computed(() =>
  cashAccounts.value.filter(
    (a) =>
      a.is_active !== false &&
      a.kind !== 'agreement_capital' && a.kind !== 'fund_capital' &&
      a.id !== paymentTargetAccount.value?.id &&
      (a.currency || 'UZS').toUpperCase() === obligationCurrency.value &&
      parseFloat(a.balance || '0') > 0,
  ),
)
const canQuickDeposit = computed(() => Boolean(paymentTargetAccount.value))
const canQuickExchange = computed(() => Boolean(paymentTargetAccount.value && exchangeSourceAccounts.value.length))
const canQuickTransfer = computed(() => Boolean(paymentTargetAccount.value && transferSourceAccounts.value.length))
const quickActionColumns = computed(() => canQuickTransfer.value ? 'grid-cols-3' : 'grid-cols-2')

async function loadAccounts(): Promise<void> {
  isLoadingAccounts.value = true
  try { cashAccounts.value = await fetchCashAccounts() }
  catch { cashAccounts.value = [] }
  finally { isLoadingAccounts.value = false }
}

watch(() => props.open, async (isOpen) => {
  if (!isOpen) return
  amount.value = props.defaultAmount ?? ''
  notes.value = ''
  if (!cashAccounts.value.length) await loadAccounts()
  const stillValid = operatingAccounts.value.some((a) => a.id === cashAccountId.value)
  if (!stillValid) cashAccountId.value = operatingAccounts.value[0]?.id ?? null
})

async function handleCashActionDone(): Promise<void> {
  depositSheetOpen.value = false
  exchangeSheetOpen.value = false
  transferSheetOpen.value = false
  await loadAccounts()
}

function openDepositSheet(): void {
  if (!paymentTargetAccount.value) return
  depositSheetOpen.value = true
}

function openExchangeSheet(): void {
  if (!paymentTargetAccount.value || !exchangeSourceAccounts.value.length) return
  exchangeSheetOpen.value = true
}

function openTransferSheet(): void {
  const source = transferSourceAccounts.value[0]
  if (!source || !paymentTargetAccount.value) return
  transferSourceAccountId.value = source.id
  transferSheetOpen.value = true
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
  !!(amount.value && parseFloat(amount.value) > 0 && cashAccountId.value && !insufficient.value)
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

      <!-- Касса (только в валюте обязательства) -->
      <div class="flex flex-col gap-1.5">
        <span class="text-xs font-medium uppercase tracking-wide text-neutral-500">Откуда платим ({{ obligationCurrency }})</span>
        <p v-if="isLoadingAccounts" class="text-sm text-neutral-500">Загрузка…</p>
        <!-- No register in the obligation currency: offer convert / top up -->
        <div v-else-if="!operatingAccounts.length" class="flex flex-col gap-2 rounded-[10px] border border-warning/30 bg-warning/10 px-3.5 py-3 text-sm text-foreground">
          <div class="flex items-start gap-2">
            <AlertCircle class="mt-0.5 size-4 shrink-0 text-warning" />
            <span>Нет кассы в валюте {{ obligationCurrency }}. Создайте кассу этой валюты, пополните её или сделайте обмен — платёж из кассы другой валюты невозможен.</span>
          </div>
        </div>
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

      <!-- Insufficient funds in the matching register -->
      <div v-if="insufficient" class="flex flex-col gap-2 rounded-[10px] border border-negative/30 bg-negative/5 px-3.5 py-3 text-sm text-foreground">
        <div class="flex items-start gap-2">
          <AlertCircle class="mt-0.5 size-4 shrink-0 text-negative" />
          <span>Недостаточно средств в кассе. Пополните её или сделайте обмен валют.</span>
        </div>
        <div
          v-if="canQuickDeposit || canQuickExchange || canQuickTransfer"
          :class="cn('grid gap-2', quickActionColumns)"
        >
          <Button
            v-if="canQuickDeposit"
            variant="outline"
            size="sm"
            class="h-10"
            type="button"
            @click="openDepositSheet"
          >
            <ArrowDownToLine data-icon="inline-start" />
            Пополнить
          </Button>
          <Button
            v-if="canQuickExchange"
            variant="outline"
            size="sm"
            class="h-10"
            type="button"
            @click="openExchangeSheet"
          >
            <ArrowRightLeft data-icon="inline-start" />
            Обменять
          </Button>
          <Button
            v-if="canQuickTransfer"
            variant="outline"
            size="sm"
            class="h-10"
            type="button"
            @click="openTransferSheet"
          >
            <Repeat2 data-icon="inline-start" />
            Перевести
          </Button>
        </div>
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

  <CashDepositSheet
    :open="depositSheetOpen"
    :account="paymentTargetAccount"
    @close="depositSheetOpen = false"
    @deposited="handleCashActionDone"
  />

  <CurrencyExchangeSheet
    :open="exchangeSheetOpen"
    :accounts="cashAccounts"
    :target-currency="obligationCurrency"
    :to-account-id="paymentTargetAccount?.id ?? null"
    @close="exchangeSheetOpen = false"
    @exchanged="handleCashActionDone"
  />

  <CashTransferSheet
    :open="transferSheetOpen"
    :accounts="cashAccounts"
    :from-account-id="transferSourceAccountId"
    :preferred-to-account-id="paymentTargetAccount?.id ?? null"
    @close="transferSheetOpen = false"
    @transferred="handleCashActionDone"
  />
</template>
