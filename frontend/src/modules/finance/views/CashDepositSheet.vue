<script setup lang="ts">
import { ref } from 'vue'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { useToast } from '@/composables/useToast'
import { createOwnerContribution, type CashAccountRecord } from '@/api/finance'
import { formatPrice } from '@/utils/currency'

const props = defineProps<{
  open: boolean
  account: CashAccountRecord | null
}>()

const emit = defineEmits<{
  close: []
  deposited: []
}>()

const toast = useToast()
const amount = ref('')
const notes = ref('')
const isSaving = ref(false)
const error = ref<string | null>(null)

function resetForm() {
  amount.value = ''
  notes.value = ''
  error.value = null
}

async function submit() {
  if (!props.account) return
  const parsed = parseFloat(String(amount.value).replace(',', '.'))
  if (!parsed || parsed <= 0) {
    error.value = 'Введите сумму больше 0'
    return
  }
  isSaving.value = true
  error.value = null
  try {
    await createOwnerContribution({
      amount: parsed.toFixed(2),
      currency: props.account.currency,
      to_account_id: props.account.id,
      notes: notes.value,
    })
    toast.success('Пополнено')
    resetForm()
    emit('deposited')
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    error.value = msg ?? 'Ошибка при пополнении'
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
  <AppBottomSheet :open="props.open" title="Пополнить кассу" @close="onClose">
    <div v-if="props.account" class="sheet-body">
      <p class="account-label">{{ props.account.name }}</p>
      <p class="balance-hint">Текущий баланс: <strong>{{ formatPrice(props.account.balance, props.account.currency) }}</strong></p>

      <div class="field">
        <label class="field-label">Сумма ({{ props.account.currency }})</label>
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

      <button class="btn-primary" :disabled="isSaving" @click="submit">
        {{ isSaving ? 'Сохранение…' : 'Пополнить' }}
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

.account-label {
  font-weight: var(--font-semibold);
  font-size: var(--text-base);
}

.balance-hint {
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
