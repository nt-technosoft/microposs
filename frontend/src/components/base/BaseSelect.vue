<script setup lang="ts">
import { computed, ref } from 'vue'
import { Check, ChevronDown } from 'lucide-vue-next'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'

type SelectValue = string | number | boolean | null

interface SelectOption {
  value: SelectValue
  label: string
  disabled?: boolean
}

interface Props {
  modelValue: SelectValue
  options: SelectOption[]
  placeholder?: string
  title?: string
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: 'Выберите значение',
  title: '',
  disabled: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: SelectValue]
}>()

const open = ref(false)

const selectedOption = computed(() =>
  props.options.find((option) => Object.is(option.value, props.modelValue)) ?? null,
)

const displayLabel = computed(() => selectedOption.value?.label ?? props.placeholder)
const sheetTitle = computed(() => props.title || props.placeholder)

function openSheet(): void {
  if (!props.disabled) {
    open.value = true
  }
}

function closeSheet(): void {
  open.value = false
}

function chooseOption(option: SelectOption): void {
  if (option.disabled) return
  emit('update:modelValue', option.value)
  closeSheet()
}
</script>

<template>
  <div class="base-select">
    <button
      class="select-trigger"
      :class="{ 'select-trigger--placeholder': !selectedOption }"
      type="button"
      :disabled="disabled"
      @click="openSheet"
    >
      <span class="select-label">{{ displayLabel }}</span>
      <ChevronDown :size="16" :stroke-width="2" aria-hidden="true" />
    </button>

    <AppBottomSheet :open="open" :title="sheetTitle" @close="closeSheet">
      <div class="options-list" role="listbox">
        <button
          v-for="option in options"
          :key="String(option.value) + option.label"
          class="option-item"
          :class="{ 'option-item--active': Object.is(option.value, modelValue) }"
          type="button"
          :disabled="option.disabled"
          @click="chooseOption(option)"
        >
          <span class="option-label">{{ option.label }}</span>
          <Check
            v-if="Object.is(option.value, modelValue)"
            :size="16"
            :stroke-width="2.25"
            class="option-check"
            aria-hidden="true"
          />
        </button>
      </div>
    </AppBottomSheet>
  </div>
</template>

<style scoped>
.base-select {
  width: 100%;
  min-width: 0;
}

.select-trigger {
  width: 100%;
  min-height: 48px;
  padding: 0 var(--space-4);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  font-size: max(16px, var(--text-base));
  line-height: 1.25;
  transition:
    border-color var(--duration-fast) var(--ease-out),
    box-shadow var(--duration-fast) var(--ease-out);
}

.select-trigger:focus-visible {
  border-color: var(--color-border-focus);
  box-shadow: 0 0 0 2px var(--color-brand-100);
  outline: none;
}

.select-trigger:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.select-trigger--placeholder {
  color: var(--color-text-secondary);
}

.select-label {
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.options-list {
  display: grid;
  gap: var(--space-2);
}

.option-item {
  min-height: 46px;
  width: 100%;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-subtle);
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  padding: 0 var(--space-4);
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  text-align: left;
  transition:
    border-color var(--duration-fast) var(--ease-out),
    background var(--duration-fast) var(--ease-out);
}

.option-item:hover:not(:disabled),
.option-item--active {
  border-color: var(--color-brand-300);
  background: var(--color-brand-50);
}

.option-item:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.option-label {
  font-size: var(--text-base);
  line-height: 1.25;
}

.option-check {
  color: var(--color-brand-600);
}
</style>
