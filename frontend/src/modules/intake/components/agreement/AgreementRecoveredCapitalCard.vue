<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowDownToLine, Coins, RotateCcw } from 'lucide-vue-next'
import BaseSelect from '@/components/base/BaseSelect.vue'
import MoneyCurrencyInput from '@/components/forms/MoneyCurrencyInput.vue'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { formatPrice } from '@/utils/currency'
import type { CashAccountRecord } from '@/api/finance'

interface RecoveredCapitalRow {
  key: string
  procurementId: number
  partnerId: number
  partnerName: string
  role: string
  availableUzs: number
  recoveredUzs: number
  returnedUzs: number
}

const props = defineProps<{
  rows: RecoveredCapitalRow[]
  accounts: CashAccountRecord[]
  usdRate: string
  agreementCurrency: 'UZS' | 'USD'
  saving?: boolean
}>()

const emit = defineEmits<{
  returnCapital: [payload: { row: RecoveredCapitalRow; amount: string; currency: 'UZS' | 'USD'; fxRate: string; accountId: number }]
  returnCapitalBatch: [payload: { entries: Array<{ row: RecoveredCapitalRow; amount: string }>; currency: 'UZS' | 'USD'; fxRate: string; accountId: number }]
}>()

const selectedKey = ref('')
const amount = ref('')
const currency = ref<'UZS' | 'USD'>('UZS')
const accountId = ref<number | null>(null)
const batchAmount = ref('')

const eligibleAccounts = computed(() =>
  props.accounts.filter((account) => account.is_active && account.currency === currency.value),
)
const accountOptions = computed(() =>
  eligibleAccounts.value.map((account) => ({
    value: account.id,
    label: `${account.name} · ${formatPrice(account.balance, account.currency)}`,
  })),
)
// A return debits real cash, so default to a funded account. If none has a
// positive balance, auto-select nothing and let the placeholder force a choice.
const preferredAccountId = computed(() => {
  const funded = eligibleAccounts.value.find((account) => Number(account.balance || 0) > 0)
  return funded ? funded.id : null
})

const selectedRow = computed(() => props.rows.find((row) => row.key === selectedKey.value) ?? null)
const activeFxRate = computed(() => currency.value === 'USD' ? Number(props.usdRate || 0) : 1)
function floorMoney(value: number): number {
  return Math.floor(Math.max(0, value) * 100) / 100
}
function amountInCurrency(row: RecoveredCapitalRow, targetCurrency: 'UZS' | 'USD'): number {
  if (targetCurrency === 'UZS') return row.availableUzs
  return activeFxRate.value > 0 ? floorMoney(row.availableUzs / activeFxRate.value) : 0
}
const selectedAvailableAmount = computed(() => {
  if (!selectedRow.value) return 0
  return amountInCurrency(selectedRow.value, currency.value)
})
const totalAvailableAmount = computed(() =>
  props.rows.reduce((sum, row) => sum + amountInCurrency(row, currency.value), 0),
)
const batchAmountValue = computed(() => Number(batchAmount.value || 0))
const batchPreview = computed(() => {
  const total = Math.min(Math.max(batchAmountValue.value, 0), totalAvailableAmount.value)
  if (total <= 0 || totalAvailableAmount.value <= 0) return []
  let distributed = 0
  const rows = props.rows.map((row) => {
    const available = amountInCurrency(row, currency.value)
    const amount = floorMoney(total * (available / totalAvailableAmount.value))
    distributed += amount
    return { row, available, amount }
  })
  let residue = floorMoney(total - distributed)
  for (const item of rows) {
    if (residue <= 0) break
    const headroom = floorMoney(item.available - item.amount)
    const topUp = Math.min(headroom, residue)
    item.amount = floorMoney(item.amount + topUp)
    residue = floorMoney(residue - topUp)
  }
  return rows.filter((item) => item.amount > 0)
})
const canSubmit = computed(() => {
  const value = Number(amount.value || 0)
  return Boolean(selectedRow.value && accountId.value && value > 0 && value <= selectedAvailableAmount.value + 0.01)
})
const canSubmitBatch = computed(() =>
  Boolean(accountId.value && batchPreview.value.length && batchAmountValue.value > 0 && batchAmountValue.value <= totalAvailableAmount.value + 0.01),
)

function selectRow(row: RecoveredCapitalRow): void {
  selectedKey.value = row.key
  amount.value = floorMoney(selectedAvailableAmount.value).toFixed(2)
}

function setAccount(value: string | number | boolean | null): void {
  accountId.value = typeof value === 'number' ? value : Number(value) || null
}

function submit(): void {
  if (!selectedRow.value || !accountId.value || !canSubmit.value) return
  emit('returnCapital', {
    row: selectedRow.value,
    amount: amount.value,
    currency: currency.value,
    fxRate: currency.value === 'USD' ? props.usdRate : '1',
    accountId: accountId.value,
  })
}

function submitBatch(): void {
  if (!accountId.value || !canSubmitBatch.value) return
  emit('returnCapitalBatch', {
    entries: batchPreview.value.map((entry) => ({ row: entry.row, amount: entry.amount.toFixed(2) })),
    currency: currency.value,
    fxRate: currency.value === 'USD' ? props.usdRate : '1',
    accountId: accountId.value,
  })
}

watch(() => props.rows, (rows) => {
  if (!rows.length) {
    selectedKey.value = ''
    amount.value = ''
    batchAmount.value = ''
    return
  }
  if (!selectedKey.value || !rows.some((row) => row.key === selectedKey.value)) {
    selectRow(rows[0])
  }
  batchAmount.value = floorMoney(totalAvailableAmount.value).toFixed(2)
}, { immediate: true })

watch(() => props.agreementCurrency, (value) => {
  currency.value = value === 'USD' ? 'USD' : 'UZS'
}, { immediate: true })

watch(currency, () => {
  if (selectedRow.value) {
    amount.value = floorMoney(selectedAvailableAmount.value).toFixed(2)
  }
  batchAmount.value = floorMoney(totalAvailableAmount.value).toFixed(2)
})

watch(accountOptions, (options) => {
  if (!options.length) {
    accountId.value = null
    return
  }
  if (!accountId.value || !options.some((option) => option.value === accountId.value)) {
    accountId.value = preferredAccountId.value
  }
}, { immediate: true })
</script>

<template>
  <Card v-if="rows.length" class="rounded-2xl bg-background">
    <CardHeader>
      <div class="flex items-start justify-between gap-3">
        <div>
          <CardTitle class="text-base">Капитал от продаж</CardTitle>
          <CardDescription class="mt-1">
            Деньги уже восстановлены продажами. Возврат списывает реальную операционную кассу.
          </CardDescription>
        </div>
        <Coins class="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
      </div>
    </CardHeader>
    <CardContent class="flex flex-col gap-3">
      <div class="rounded-xl border border-border bg-muted/30 p-3">
        <div class="flex items-start justify-between gap-3">
          <div>
            <p class="text-sm font-medium text-foreground">Групповой возврат</p>
            <p class="mt-0.5 text-xs text-muted-foreground">
              Укажите общую сумму — система распределит её между инвесторами пропорционально доступному капиталу.
            </p>
          </div>
          <span class="shrink-0 text-sm font-semibold tabular-nums text-foreground">
            {{ formatPrice(totalAvailableAmount, currency) }}
          </span>
        </div>
        <div class="mt-3 grid gap-3 sm:grid-cols-[1fr_1fr]">
          <MoneyCurrencyInput
            v-model="batchAmount"
            v-model:currency="currency"
            :currencies="['UZS', 'USD']"
            placeholder="Общая сумма"
            aria-label="Общая сумма возврата капитала"
          />
          <Button type="button" variant="outline" :disabled="saving || !canSubmitBatch" @click="submitBatch">
            <ArrowDownToLine data-icon="inline-start" />
            Вернуть по всем
          </Button>
        </div>
        <div v-if="batchPreview.length" class="mt-3 grid gap-1.5">
          <div
            v-for="entry in batchPreview"
            :key="`batch-${entry.row.key}`"
            class="flex items-center justify-between gap-3 text-xs"
          >
            <span class="truncate text-muted-foreground">{{ entry.row.partnerName }}</span>
            <span class="font-medium tabular-nums text-foreground">{{ formatPrice(entry.amount, currency) }}</span>
          </div>
        </div>
      </div>

      <div class="grid gap-2">
        <button
          v-for="row in rows"
          :key="row.key"
          type="button"
          class="flex items-center justify-between gap-3 rounded-xl border px-3 py-2.5 text-left transition"
          :class="selectedKey === row.key ? 'border-primary bg-primary/5' : 'border-border bg-background hover:bg-muted/50'"
          @click="selectRow(row)"
        >
          <span class="min-w-0">
            <span class="block truncate text-sm font-medium text-foreground">
              #{{ row.procurementId }} · {{ row.partnerName }}
            </span>
            <span class="mt-0.5 block text-xs text-muted-foreground">
              восстановлено {{ formatPrice(row.recoveredUzs, 'UZS') }} · возвращено {{ formatPrice(row.returnedUzs, 'UZS') }}
            </span>
          </span>
          <span class="shrink-0 text-sm font-semibold tabular-nums text-foreground">
            {{ formatPrice(amountInCurrency(row, currency), currency) }}
          </span>
        </button>
      </div>

      <div class="grid gap-3 sm:grid-cols-[1fr_1fr]">
        <MoneyCurrencyInput
          v-model="amount"
          v-model:currency="currency"
          :currencies="['UZS', 'USD']"
          placeholder="Сумма возврата"
          aria-label="Сумма возврата капитала от продаж"
        />
        <BaseSelect
          :model-value="accountId"
          :options="accountOptions"
          title="Из какой кассы вернуть"
          @update:model-value="setAccount"
        />
      </div>

      <p v-if="currency === 'USD' && !Number(usdRate || 0)" class="text-sm text-destructive">
        Для USD-выплаты нужен курс USD/UZS.
      </p>
      <p v-else-if="selectedRow && Number(amount || 0) > selectedAvailableAmount + 0.01" class="text-sm text-destructive">
        Доступно только {{ formatPrice(selectedAvailableAmount, currency) }}.
      </p>
      <p v-else-if="!accountOptions.length" class="text-sm text-destructive">
        Нет активной {{ currency }}-кассы для возврата.
      </p>

      <Button type="button" :disabled="saving || !canSubmit" @click="submit">
        <RotateCcw data-icon="inline-start" />
        {{ saving ? 'Сохранение...' : 'Вернуть капитал' }}
      </Button>

      <p class="flex items-start gap-2 text-xs leading-relaxed text-muted-foreground">
        <ArrowDownToLine class="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        Это не уменьшает себестоимость и не пересчитывает приход. Это факт вывода уже восстановленной части капитала.
      </p>
    </CardContent>
  </Card>
</template>
