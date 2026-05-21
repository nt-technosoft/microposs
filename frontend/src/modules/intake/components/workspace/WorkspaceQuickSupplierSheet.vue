<script setup lang="ts">
import { ref } from 'vue'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { createSupplier } from '@/api/suppliers'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  'update:open': [value: boolean]
  created: [supplierId: number]
}>()

const name = ref('')
const phone = ref('')
const saving = ref(false)
const error = ref('')

function reset(): void {
  name.value = ''
  phone.value = ''
  saving.value = false
  error.value = ''
}

async function onSave(): Promise<void> {
  if (!name.value.trim()) { error.value = 'Введите название'; return }
  saving.value = true
  error.value = ''
  try {
    const supplier = await createSupplier({ name: name.value.trim(), phone: phone.value.trim() || undefined })
    emit('created', supplier.id)
    emit('update:open', false)
    reset()
  } catch (err) {
    const detail = (err as any)?.response?.data?.detail
    error.value = detail ?? (err instanceof Error ? err.message : 'Ошибка создания')
  } finally {
    saving.value = false
  }
}

function onClose(): void {
  emit('update:open', false)
  reset()
}
</script>

<template>
  <AppBottomSheet :open="open" title="Новый поставщик" @close="onClose">
    <div class="form-body">
      <label class="field-label">
        Название <span class="req">*</span>
        <input
          v-model="name"
          class="input-field"
          type="text"
          placeholder="Например, ООО «Поставщик»"
          autocomplete="off"
        />
      </label>

      <label class="field-label">
        Телефон
        <input
          v-model="phone"
          class="input-field"
          type="tel"
          placeholder="+998 90 000 00 00"
        />
      </label>

      <p v-if="error" class="error-text">{{ error }}</p>

      <button
        class="save-btn"
        type="button"
        :disabled="saving || !name.trim()"
        @click="onSave"
      >
        {{ saving ? 'Сохранение…' : 'Создать поставщика' }}
      </button>
    </div>
  </AppBottomSheet>
</template>

<style scoped>
.form-body { display: grid; gap: var(--space-3); }
.field-label { display: grid; gap: var(--space-1); font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-secondary); }
.req { color: var(--color-error); }
.input-field { min-height: 44px; padding: 0 var(--space-3); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); font-size: var(--text-sm); width: 100%; }
.error-text { font-size: var(--text-sm); color: var(--color-error); margin: 0; }
.save-btn { min-height: 48px; border: 0; border-radius: var(--radius-lg); background: var(--color-brand-500); color: var(--color-text-inverse); font-weight: var(--font-semibold); font-size: var(--text-base); cursor: pointer; }
.save-btn:disabled { opacity: 0.55; cursor: default; }
</style>
