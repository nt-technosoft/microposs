<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'
import { useToast } from '@/composables/useToast'
import { createCashTransfer, type CashAccountRecord } from '@/api/finance'
import { formatPrice } from '@/utils/currency'

const props = defineProps<{
  open: boolean
  accounts: CashAccountRecord[]
  fromAccountId: number | null
  preferredToAccountId?: number | null
}>()

const emit = defineEmits<{
  close: []
  transferred: []
}>()

const toast = useToast()
const toAccountId = ref<number | null>(null)
const amount = ref('')
const notes = ref('')
const isSaving = ref(false)
const error = ref<string | null>(null)

const fromAccount = computed(() =>
  props.accounts.find((a) => a.id === props.fromAccountId) ?? null,
)

const eligibleTargets = computed(() =>
  props.accounts.filter(
    (a) =>
      a.id !== props.fromAccountId &&
      a.is_active !== false &&
      a.currency === fromAccount.value?.currency,
  ),
)

const toOptions = computed(() =>
  eligibleTargets.value.map((a) => ({
    value: a.id,
    label: `${a.name} · ${formatPrice(a.balance, a.currency)}`,
  })),
)

watch(() => props.open, (open) => {
  if (!open) return
  const preferredTarget = eligibleTargets.value.find((account) => account.id === props.preferredToAccountId)
  toAccountId.value = preferredTarget?.id ?? null
  amount.value = ''
  notes.value = ''
  error.value = null
})

function resetForm() {
  toAccountId.value = null
  amount.value = ''
  notes.value = ''
  error.value = null
}

async function submit() {
  if (!props.fromAccountId || !toAccountId.value) {
    error.value = 'Выберите счёт назначения'
    return
  }
  const parsed = parseFloat(String(amount.value).replace(',', '.'))
  if (!parsed || parsed <= 0) {
    error.value = 'Введите сумму больше 0'
    return
  }
  isSaving.value = true
  error.value = null
  try {
    await createCashTransfer({
      from_account_id: props.fromAccountId,
      to_account_id: toAccountId.value,
      amount: parsed.toFixed(2),
      notes: notes.value,
    })
    toast.success('Перевод выполнен')
    resetForm()
    emit('transferred')
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    error.value = msg ?? 'Ошибка при переводе'
  } finally {
    isSaving.value = false
  }
}

function onClose() {
  resetForm()
  emit('close')
}
</script>

<template>
  <AppBottomSheet :open="props.open" title="Перевод между кассами" @close="onClose">
    <div class="sheet-body">
      <div v-if="fromAccount" class="from-info">
        <span class="from-label">Из кассы:</span>
        <span class="from-name">{{ fromAccount.name }}</span>
        <span class="from-balance">{{ formatPrice(fromAccount.balance, fromAccount.currency) }}</span>
      </div>

      <div class="field">
        <label class="field-label">В кассу</label>
        <BaseSelect
          v-model="toAccountId"
          :options="toOptions"
          placeholder="Выберите кассу"
        />
        <p v-if="eligibleTargets.length === 0" class="hint-text">
          Нет подходящих касс той же валюты
        </p>
      </div>

      <div class="field">
        <label class="field-label">Сумма ({{ fromAccount?.currency }})</label>
        <input
          v-model="amount"
          type="number"
          min="0.01"
          step="0.01"
          class="field-input"
          placeholder="0.00"
          inputmode="decimal"
        />
      </div>

      <div class="field">
        <label class="field-label">Комментарий</label>
        <input v-model="notes" type="text" class="field-input" placeholder="Необязательно" />
      </div>

      <p v-if="error" class="error-text">{{ error }}</p>

      <button
        class="btn-primary"
        :disabled="isSaving || eligibleTargets.length === 0"
        @click="submit"
      >
        {{ isSaving ? 'Сохранение…' : 'Перевести' }}
      </button>
    </div>
  </AppBottomSheet>
</template>

<style scoped>
.sheet-body {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding: var(--space-4);
}

.from-info {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3);
  background: var(--color-bg-subtle);
  border-radius: var(--radius-md);
}

.from-label {
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
}

.from-name {
  font-weight: var(--font-semibold);
  flex: 1;
}

.from-balance {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.field-label {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.field-input {
  padding: var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  background: var(--color-bg-base);
  color: var(--color-text-primary);
  width: 100%;
  box-sizing: border-box;
}

.hint-text {
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
}

.error-text {
  font-size: var(--text-sm);
  color: var(--color-danger-500);
}

.btn-primary {
  width: 100%;
  padding: var(--space-3);
  background: var(--color-brand-500);
  color: #fff;
  border-radius: var(--radius-md);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  cursor: pointer;
  transition: opacity var(--duration-fast) var(--ease-out);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
