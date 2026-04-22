<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  modelValue: string | number
  label?: string
  placeholder?: string
  type?: string
  error?: string
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  label: '',
  placeholder: '',
  type: 'text',
  error: '',
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string | number]
}>()

const hasError = computed(() => !!props.error)

function onInput(event: Event) {
  const target = event.target as HTMLInputElement
  emit('update:modelValue', target.value)
}
</script>

<template>
  <div class="input-group" :class="{ 'has-error': hasError }">
    <label v-if="label" class="input-label">{{ label }}</label>
    <input
      class="input-field"
      :type="type"
      :inputmode="type === 'number' ? 'decimal' : undefined"
      :value="modelValue"
      :placeholder="placeholder"
      :disabled="disabled"
      @input="onInput"
    />
    <span v-if="hasError" class="input-error" role="alert">{{ error }}</span>
  </div>
</template>

<style scoped>
.input-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.input-label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
}

.input-field {
  height: 48px;
  padding: 0 var(--space-4);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  font-size: var(--text-base);
  color: var(--color-text-primary);
  transition:
    border-color var(--duration-fast) var(--ease-out),
    box-shadow var(--duration-fast) var(--ease-out);
  outline: none;
}

.input-field::placeholder {
  color: var(--color-text-tertiary);
}

.input-field:focus {
  border-color: var(--color-border-focus);
  box-shadow: 0 0 0 2px var(--color-brand-100);
}

.input-field:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: var(--color-bg-sunken);
}

.has-error .input-field {
  border-color: var(--color-error);
}

.has-error .input-field:focus {
  box-shadow: 0 0 0 2px var(--color-error-bg);
}

.input-error {
  font-size: var(--text-xs);
  color: var(--color-error);
}
</style>
