<script setup lang="ts">
import { computed } from 'vue'
import { RefreshCcw } from 'lucide-vue-next'

type CurrencyCode = 'USD' | 'UZS'

const props = withDefaults(defineProps<{
  modelValue: string | number
  currency: CurrencyCode
  currencies?: CurrencyCode[]
  disabled?: boolean
  placeholder?: string
  min?: string | number
  step?: string | number
  inputmode?: 'decimal' | 'numeric' | 'text'
  size?: 'md' | 'lg'
  ariaLabel?: string
}>(), {
  currencies: () => ['USD', 'UZS'],
  disabled: false,
  placeholder: '0',
  min: '0',
  step: '0.01',
  inputmode: 'decimal',
  size: 'md',
  ariaLabel: 'Сумма',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'update:currency': [value: CurrencyCode]
}>()

const normalizedCurrencies = computed<CurrencyCode[]>(() => {
  const unique = props.currencies.filter((currency, index, list) => list.indexOf(currency) === index)
  return unique.length > 0 ? unique : ['USD', 'UZS']
})

const nextCurrency = computed(() => {
  const currentIndex = normalizedCurrencies.value.indexOf(props.currency)
  const nextIndex = currentIndex >= 0 ? (currentIndex + 1) % normalizedCurrencies.value.length : 0
  return normalizedCurrencies.value[nextIndex] ?? 'USD'
})

function updateValue(event: Event): void {
  emit('update:modelValue', (event.target as HTMLInputElement).value)
}

function toggleCurrency(): void {
  if (props.disabled) return
  emit('update:currency', nextCurrency.value)
}
</script>

<template>
  <div class="money-currency-input" :class="[`money-currency-input--${size}`, { disabled }]">
    <input
      class="money-currency-input__control"
      type="number"
      :min="min"
      :step="step"
      :inputmode="inputmode"
      :placeholder="placeholder"
      :aria-label="ariaLabel"
      :value="modelValue"
      :disabled="disabled"
      @input="updateValue"
    />
    <button
      class="money-currency-input__toggle"
      type="button"
      :disabled="disabled || normalizedCurrencies.length < 2"
      :aria-label="`Сменить валюту. Сейчас ${currency}`"
      @click="toggleCurrency"
    >
      <span>{{ currency }}</span>
      <RefreshCcw :size="13" :stroke-width="2" />
    </button>
  </div>
</template>

<style scoped>
.money-currency-input {
  position: relative;
  min-width: 0;
}

.money-currency-input__control {
  width: 100%;
  min-height: 44px;
  padding: 0 92px 0 12px;
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  font: inherit;
}

.money-currency-input--lg .money-currency-input__control {
  min-height: 48px;
  padding-left: 14px;
  font-size: var(--text-base);
}

.money-currency-input__control:disabled {
  opacity: 0.72;
  background: var(--color-bg-sunken);
}

.money-currency-input__toggle {
  position: absolute;
  top: 50%;
  right: 6px;
  transform: translateY(-50%);
  min-width: 70px;
  height: 30px;
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 0 9px;
  border: 1px solid var(--color-border-default);
  border-radius: calc(var(--radius-md) - 2px);
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  line-height: 1;
}

.money-currency-input--lg .money-currency-input__toggle {
  height: 34px;
}

.money-currency-input__toggle:disabled {
  opacity: 0.62;
}

.money-currency-input.disabled {
  opacity: 0.92;
}
</style>
