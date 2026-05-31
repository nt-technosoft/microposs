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
/* E10: aligned to the OKLCH design system (matches shadcn Input height/bg/border). */
.money-currency-input {
  position: relative;
  min-width: 0;
}

.money-currency-input__control {
  width: 100%;
  height: 44px;
  padding: 0 88px 0 14px;
  border: 1px solid var(--neutral-200);
  border-radius: 10px;
  background: var(--surface);
  color: var(--neutral-900);
  font: inherit;
  font-size: 1rem;
  font-variant-numeric: tabular-nums;
  outline: none;
  transition: border-color 120ms ease-out;
}

.money-currency-input__control:focus {
  border-color: var(--green-400);
}

.money-currency-input__control::placeholder {
  color: var(--neutral-400);
}

.money-currency-input--lg .money-currency-input__control {
  height: 48px;
  font-size: var(--text-base);
}

.money-currency-input__control:disabled {
  opacity: 0.6;
  background: var(--neutral-50);
}

.money-currency-input__toggle {
  position: absolute;
  top: 50%;
  right: 6px;
  transform: translateY(-50%);
  min-width: 72px;
  height: 32px;
  box-sizing: border-box;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 0 10px;
  border: 1px solid var(--neutral-200);
  border-radius: 8px;
  background: var(--neutral-50);
  color: var(--neutral-700);
  font-size: var(--text-sm);
  font-weight: 600;
  line-height: 1;
  cursor: pointer;
}

.money-currency-input--lg .money-currency-input__toggle {
  height: 36px;
}

.money-currency-input__toggle:disabled {
  opacity: 0.62;
  cursor: default;
}

.money-currency-input.disabled {
  opacity: 0.92;
}
</style>
