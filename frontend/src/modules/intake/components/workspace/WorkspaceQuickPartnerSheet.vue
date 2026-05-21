<script setup lang="ts">
import { ref } from 'vue'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { createPartner, type Partner } from '@/api/core'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  'update:open': [value: boolean]
  created: [partner: Partner]
}>()

const displayName = ref('')
const saving = ref(false)
const error = ref('')

function reset(): void {
  displayName.value = ''
  saving.value = false
  error.value = ''
}

async function onSave(): Promise<void> {
  if (!displayName.value.trim()) { error.value = 'Введите имя инвестора'; return }
  saving.value = true
  error.value = ''
  try {
    const partner = await createPartner({ display_name: displayName.value.trim(), role: 'INVESTOR' })
    emit('created', partner)
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
  <AppBottomSheet :open="open" title="Новый инвестор" @close="onClose">
    <div class="form-body">
      <label class="field-label">
        Имя / название <span class="req">*</span>
        <input
          v-model="displayName"
          class="input-field"
          type="text"
          placeholder="Например, Иванов А.А."
          autocomplete="off"
        />
      </label>

      <p class="hint-text">Роль: Инвестор. После создания инвестор сразу появится в списке договора.</p>

      <p v-if="error" class="error-text">{{ error }}</p>

      <button
        class="save-btn"
        type="button"
        :disabled="saving || !displayName.trim()"
        @click="onSave"
      >
        {{ saving ? 'Сохранение…' : 'Создать инвестора' }}
      </button>
    </div>
  </AppBottomSheet>
</template>

<style scoped>
.form-body { display: grid; gap: var(--space-3); }
.field-label { display: grid; gap: var(--space-1); font-size: var(--text-sm); font-weight: var(--font-semibold); color: var(--color-text-secondary); }
.req { color: var(--color-error); }
.input-field { min-height: 44px; padding: 0 var(--space-3); border: 1px solid var(--color-border-default); border-radius: var(--radius-md); background: var(--color-bg-primary); color: var(--color-text-primary); font-size: var(--text-sm); width: 100%; }
.hint-text { margin: 0; font-size: var(--text-xs); color: var(--color-text-secondary); }
.error-text { font-size: var(--text-sm); color: var(--color-error); margin: 0; }
.save-btn { min-height: 48px; border: 0; border-radius: var(--radius-lg); background: var(--color-brand-500); color: var(--color-text-inverse); font-weight: var(--font-semibold); font-size: var(--text-base); cursor: pointer; }
.save-btn:disabled { opacity: 0.55; cursor: default; }
</style>
