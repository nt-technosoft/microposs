<script setup lang="ts">
import { computed } from 'vue'
import { formatPrice } from '@/utils/currency'

interface Props {
  amount: string | number
  currency?: string
  size?: 'sm' | 'md' | 'lg' | 'xl'
  negative?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  currency: 'UZS',
  size: 'md',
  negative: false,
})

const formatted = computed(() => formatPrice(props.amount, props.currency))
</script>

<template>
  <span
    class="price tabular-nums"
    :class="[`price--${size}`, { 'price--negative': negative }]"
  >
    {{ formatted }}
  </span>
</template>

<style scoped>
.price {
  font-family: var(--font-mono);
  font-weight: var(--font-bold);
  font-variant-numeric: tabular-nums;
  color: var(--color-text-primary);
}

.price--sm { font-size: var(--text-sm); }
.price--md { font-size: var(--text-base); }
.price--lg { font-size: var(--text-xl); }
.price--xl { font-size: var(--text-3xl); }

.price--negative {
  color: var(--color-error);
}
</style>
