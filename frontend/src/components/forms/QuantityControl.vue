<script setup lang="ts">
import { Minus, Plus } from 'lucide-vue-next'

interface Props {
  modelValue: number
  min?: number
  max?: number
}

const props = withDefaults(defineProps<Props>(), {
  min: 1,
  max: 9999,
})

const emit = defineEmits<{
  'update:modelValue': [value: number]
}>()

function decrement() {
  if (props.modelValue > props.min) {
    emit('update:modelValue', props.modelValue - 1)
  }
}

function increment() {
  if (props.modelValue < props.max) {
    emit('update:modelValue', props.modelValue + 1)
  }
}
</script>

<template>
  <div class="qty-control">
    <button
      class="qty-btn"
      :disabled="modelValue <= min"
      aria-label="Уменьшить"
      @click="decrement"
    >
      <Minus :size="16" :stroke-width="2" />
    </button>
    <span class="qty-value tabular-nums">{{ modelValue }}</span>
    <button
      class="qty-btn"
      :disabled="modelValue >= max"
      aria-label="Увеличить"
      @click="increment"
    >
      <Plus :size="16" :stroke-width="2" />
    </button>
  </div>
</template>

<style scoped>
.qty-control {
  display: inline-flex;
  align-items: center;
  gap: 0;
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  overflow: hidden;
}

.qty-btn {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-primary);
  transition: background var(--duration-fast) var(--ease-out);
}

.qty-btn:hover:not(:disabled) {
  background: var(--color-bg-secondary);
}

.qty-btn:active:not(:disabled) {
  background: var(--color-bg-sunken);
}

.qty-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.qty-value {
  min-width: 40px;
  text-align: center;
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  border-left: 1px solid var(--color-border-default);
  border-right: 1px solid var(--color-border-default);
  padding: 0 var(--space-2);
  line-height: 36px;
}
</style>
