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
  saving?: boolean
}>()

const emit = defineEmits<{
  returnCapital: [payload: { row: RecoveredCapitalRow; amount: string; currency: 'UZS' | 'USD'; fxRate: string; accountId: number }]
}>()

const selectedKey = ref('')
const amount = ref('')
const currency = ref<'UZS' | 'USD'>('UZS')
const accountId = ref<number | null>(null)

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
const selectedAvailableAmount = computed(() => {
  if (!selectedRow.value) return 0
  if (currency.value === 'UZS') return selectedRow.value.availableUzs
  return activeFxRate.value > 0 ? selectedRow.value.availableUzs / activeFxRate.value : 0
})
const canSubmit = computed(() => {
  const value = Number(amount.value || 0)
  return Boolean(selectedRow.value && accountId.value && value > 0 && value <= selectedAvailableAmount.value + 0.01)
})

function selectRow(row: RecoveredCapitalRow): void {
  selectedKey.value = row.key
  amount.value = selectedAvailableAmount.value.toFixed(2)
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

watch(() => props.rows, (rows) => {
  if (!rows.length) {
    selectedKey.value = ''
    amount.value = ''
    return
  }
  if (!selectedKey.value || !rows.some((row) => row.key === selectedKey.value)) {
    selectRow(rows[0])
  }
}, { immediate: true })

watch(currency, () => {
  if (selectedRow.value) {
    amount.value = selectedAvailableAmount.value.toFixed(2)
  }
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
            {{ formatPrice(row.availableUzs, 'UZS') }}
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
