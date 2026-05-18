<script setup lang="ts">
import { AlertCircle } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'
import type { SelectOption } from './types'

defineProps<{
  open: boolean
  name: string
  categoryId: number | null
  basePrice: string
  categoryOptions: SelectOption<number | null>[]
  error: string | null
  saving: boolean
}>()

const emit = defineEmits<{
  close: []
  updateName: [value: string]
  updateCategoryId: [value: number | null]
  updateBasePrice: [value: string]
  submit: []
}>()
</script>

<template>
  <AppBottomSheet :open="open" title="Быстрое создание товара" @close="emit('close')">
    <form class="sheet-body" @submit.prevent="emit('submit')">
      <div v-if="error" class="error-box">
        <AlertCircle :size="18" :stroke-width="1.75" />
        <span>{{ error }}</span>
      </div>

      <label class="field-group">
        <span class="field-label">Название *</span>
        <input
          class="input-field"
          type="text"
          placeholder="Например, iPhone 15 Pro"
          :value="name"
          @input="emit('updateName', ($event.target as HTMLInputElement).value)"
        />
      </label>

      <label class="field-group">
        <span class="field-label">Категория</span>
        <BaseSelect
          :model-value="categoryId"
          :options="categoryOptions"
          title="Категория товара"
          placeholder="Без категории"
          @update:model-value="(value) => emit('updateCategoryId', value === null ? null : Number(value))"
        />
      </label>

      <label class="field-group">
        <span class="field-label">Базовая цена</span>
        <input
          class="input-field"
          type="number"
          min="0"
          placeholder="0"
          :value="basePrice"
          @input="emit('updateBasePrice', ($event.target as HTMLInputElement).value)"
        />
      </label>

      <button class="primary-action" type="submit" :disabled="saving">
        {{ saving ? 'Создание…' : 'Создать и добавить' }}
      </button>
    </form>
  </AppBottomSheet>
</template>

<style scoped>
.sheet-body,
.field-group {
  display: grid;
  gap: 10px;
}

.field-group {
  gap: 6px;
}

.field-label {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.input-field {
  width: 100%;
  min-height: 44px;
  padding: 0 12px;
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
}

.error-box {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-md);
  background: var(--color-danger-bg);
  color: var(--color-danger);
  font-size: var(--text-sm);
  line-height: 1.4;
}

.primary-action {
  min-height: 48px;
  border: 0;
  border-radius: var(--radius-lg);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  font-weight: var(--font-semibold);
}

.primary-action:disabled {
  opacity: 0.62;
}
</style>
