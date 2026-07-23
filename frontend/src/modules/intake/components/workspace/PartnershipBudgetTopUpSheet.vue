<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import MoneyCurrencyInput from '@/components/forms/MoneyCurrencyInput.vue'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'
import { fetchCashAccounts, type CashAccountRecord } from '@/api/finance'
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

type Partner = NonNullable<ProcurementWorkspacePayload['documents']['investment']>['partners'][number]
// External: new money from outside lands directly in the agreement pool.
// Turnover: the business moves money it already holds (operating cash → pool).
type SourceMode = 'EXTERNAL' | 'TURNOVER'

const investment = computed(() => props.procurement.documents.investment)
const partners = computed(() => investment.value?.partners ?? [])
const agreementCurrency = computed(() => (investment.value?.currency ?? 'UZS').toUpperCase())
const pool = computed(() => investment.value?.pool ?? null)

const partnerId = ref<number | null>(null)
const sourceMode = ref<SourceMode>('EXTERNAL')
const amount = ref('')
const notes = ref('')
const fromCashAccountId = ref<number | null>(null)
const cashAccounts = ref<CashAccountRecord[]>([])
const isLoadingAccounts = ref(false)

const selectedPartner = computed(() => partners.value.find((p) => p.partner_id === partnerId.value) ?? null)
const isBusiness = computed(() => selectedPartner.value?.role === 'OPERATOR')
// Turnover spends an *operating* account in the agreement currency — never an
// agreement capital pool (a pool can't fund itself or another agreement).
const eligibleAccounts = computed(() =>
  cashAccounts.value.filter(
    (a) => a.kind !== 'agreement_capital' && a.kind !== 'fund_capital'
      && a.currency.toUpperCase() === agreementCurrency.value,
  ),
)
const selectedAccount = computed(
  () => eligibleAccounts.value.find((a) => a.id === fromCashAccountId.value) ?? null,
)
const amountValue = computed(() => parseFloat(amount.value) || 0)
const insufficientTurnover = computed(
  () => sourceMode.value === 'TURNOVER'
    && !!selectedAccount.value
    && amountValue.value > (parseFloat(selectedAccount.value.balance) || 0),
)

function partnerLabel(partner: Partner): string {
  return partner.role === 'OPERATOR' ? 'Бизнес' : partner.partner_name
}

function onSelectPartner(partner: Partner): void {
  partnerId.value = partner.partner_id
  // Investor money is always new external capital; the business may instead
  // commit money it already holds (turnover).
  sourceMode.value = 'EXTERNAL'
}

async function loadAccounts(): Promise<void> {
  isLoadingAccounts.value = true
  try {
    cashAccounts.value = await fetchCashAccounts()
  } catch {
    cashAccounts.value = []
  } finally {
    isLoadingAccounts.value = false
    fromCashAccountId.value = eligibleAccounts.value[0]?.id ?? null
  }
}

watch(() => props.open, (isOpen) => {
  if (!isOpen) return
  amount.value = ''
  notes.value = ''
  const initial = partners.value.find((p) => p.role === 'INVESTOR') ?? partners.value[0] ?? null
  partnerId.value = initial?.partner_id ?? null
  sourceMode.value = 'EXTERNAL'
  if (!cashAccounts.value.length) loadAccounts()
  else fromCashAccountId.value = eligibleAccounts.value[0]?.id ?? null
})

const canSave = computed(() => {
  if (!partnerId.value || amountValue.value <= 0) return false
  if (sourceMode.value === 'TURNOVER') {
    return !!fromCashAccountId.value && !insufficientTurnover.value
  }
  return true
})

function onSave(): void {
  if (!canSave.value) return
  const base: Record<string, unknown> = {
    partner_id: partnerId.value,
    amount: amountValue.value,
    currency: agreementCurrency.value,
    notes: notes.value,
  }
  if (sourceMode.value === 'TURNOVER') {
    base.mode = 'BUSINESS_FROM_TURNOVER'
    base.from_cash_account_id = fromCashAccountId.value
  }
  emit('dispatch', 'RECORD_CAPITAL_CONTRIBUTION', base)
  emit('update:open', false)
}
</script>

<template>
  <AppBottomSheet :open="open" title="Пополнить капитал договора" @close="emit('update:open', false)">
    <div class="flex flex-col gap-4">
      <!-- Pool balance — the single source of truth for partnership money -->
      <div v-if="pool" class="flex items-center justify-between rounded-[10px] bg-neutral-50 px-3 py-2.5">
        <span class="text-xs font-medium text-neutral-500">Сейчас в пуле договора</span>
        <span class="text-sm font-semibold tabular-nums text-foreground">
          {{ formatPrice(parseFloat(pool.balance) || 0, pool.currency) }}
        </span>
      </div>

      <!-- Who contributes -->
      <div class="flex flex-col gap-2">
        <span class="text-xs font-medium text-neutral-500">Кто вносит</span>
        <div class="grid grid-cols-2 gap-2">
          <button
            v-for="partner in partners"
            :key="partner.partner_id"
            type="button"
            :class="cn(
              'rounded-[10px] border px-3 py-2.5 text-sm font-medium transition-colors',
              partnerId === partner.partner_id
                ? 'border-primary bg-primary/5 text-foreground'
                : 'border-neutral-200 text-neutral-600 hover:bg-neutral-50',
            )"
            @click="onSelectPartner(partner)"
          >
            {{ partnerLabel(partner) }}
          </button>
        </div>
      </div>

      <!-- Source mode (business only) -->
      <div v-if="isBusiness" class="flex flex-col gap-2">
        <span class="text-xs font-medium text-neutral-500">Источник</span>
        <div class="grid grid-cols-2 gap-2">
          <button
            type="button"
            :class="cn(
              'rounded-[10px] border px-3 py-2.5 text-sm font-medium transition-colors',
              sourceMode === 'TURNOVER'
                ? 'border-primary bg-primary/5 text-foreground'
                : 'border-neutral-200 text-neutral-600 hover:bg-neutral-50',
            )"
            @click="sourceMode = 'TURNOVER'"
          >
            Из своих оборотов
          </button>
          <button
            type="button"
            :class="cn(
              'rounded-[10px] border px-3 py-2.5 text-sm font-medium transition-colors',
              sourceMode === 'EXTERNAL'
                ? 'border-primary bg-primary/5 text-foreground'
                : 'border-neutral-200 text-neutral-600 hover:bg-neutral-50',
            )"
            @click="sourceMode = 'EXTERNAL'"
          >
            Из кармана (новые)
          </button>
        </div>
      </div>

      <!-- Amount (locked to the agreement currency — the pool is mono-currency) -->
      <div class="flex flex-col gap-2">
        <span class="text-xs font-medium text-neutral-500">Сумма</span>
        <MoneyCurrencyInput
          v-model="amount"
          :currency="(agreementCurrency as 'USD' | 'UZS')"
          :currencies="[(agreementCurrency as 'USD' | 'UZS')]"
          aria-label="Сумма пополнения"
        />
      </div>

      <!-- Source account: ONLY for turnover (money leaves an operating account) -->
      <div v-if="sourceMode === 'TURNOVER'" class="flex flex-col gap-2">
        <span class="text-xs font-medium text-neutral-500">Из какой кассы</span>
        <p class="-mt-1 text-xs text-neutral-400">
          Деньги уйдут из этой кассы в пул договора.
        </p>
        <p v-if="isLoadingAccounts" class="text-sm text-neutral-500">Загрузка…</p>
        <p v-else-if="!eligibleAccounts.length" class="text-sm text-neutral-500">
          Нет кассы в валюте договора ({{ agreementCurrency }})
        </p>
        <div v-else class="flex flex-col gap-2">
          <button
            v-for="acc in eligibleAccounts"
            :key="acc.id"
            type="button"
            :class="cn(
              'flex items-center justify-between gap-3 rounded-[10px] border px-3 py-2.5 transition-colors',
              acc.id === fromCashAccountId
                ? 'border-primary bg-primary/5'
                : 'border-neutral-200 hover:bg-neutral-50',
            )"
            @click="fromCashAccountId = acc.id"
          >
            <span class="text-sm font-medium text-foreground">{{ acc.name }}</span>
            <span class="text-xs tabular-nums text-neutral-500">{{ formatPrice(parseFloat(acc.balance) || 0, acc.currency) }}</span>
          </button>
        </div>
        <p v-if="insufficientTurnover" class="rounded-[10px] bg-red-50 px-3 py-2.5 text-xs text-red-600">
          На кассе недостаточно средств для этого взноса.
        </p>
      </div>

      <!-- External money lands straight in the pool -->
      <p v-else class="rounded-[10px] bg-neutral-50 px-3 py-2.5 text-xs text-neutral-500">
        Новые деньги поступят прямо в пул договора. Операционная касса не меняется.
      </p>

      <Input v-model="notes" type="text" placeholder="Примечание (необязательно)" />

      <Button class="w-full" :disabled="!canSave" @click="onSave">
        Пополнить пул
      </Button>
    </div>
  </AppBottomSheet>
</template>
