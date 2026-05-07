<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { CheckCircle, ShoppingCart, History } from 'lucide-vue-next'
import BaseButton from '@/components/base/BaseButton.vue'
import PriceDisplay from '@/components/data/PriceDisplay.vue'

interface Props {
  totalAmount: string
}

defineProps<Props>()
const { t } = useI18n()

const emit = defineEmits<{
  newSale: []
  history: []
}>()
</script>

<template>
  <div class="success-screen">
    <div class="success-screen__body">
      <div class="success-checkmark" aria-hidden="true">
        <CheckCircle :size="80" :stroke-width="1.5" class="success-checkmark__icon" />
      </div>
      <h1 class="success-title">{{ t('sales.saleSuccessTitle') }}</h1>
      <p class="success-subtitle">{{ t('sales.saleSuccessSubtitle') }}</p>
      <PriceDisplay :amount="totalAmount" size="xl" class="success-amount" />
    </div>
    <div class="success-screen__actions">
      <BaseButton variant="primary" size="lg" :full-width="true" @click="emit('newSale')">
        <ShoppingCart :size="18" :stroke-width="2" />
        {{ t('sales.newSale') }}
      </BaseButton>
      <BaseButton variant="ghost" size="md" :full-width="true" @click="emit('history')">
        <History :size="18" :stroke-width="1.75" />
        {{ t('sales.history') }}
      </BaseButton>
    </div>
  </div>
</template>

<style scoped>
.success-screen {
  position: fixed;
  inset: 0;
  background: var(--color-bg-primary);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-8) var(--space-6);
  padding-bottom: calc(var(--space-8) + env(safe-area-inset-bottom, 0px));
  z-index: var(--z-modal);
}

.success-screen__body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-4);
  flex: 1;
  justify-content: center;
  text-align: center;
}

.success-checkmark {
  color: var(--color-success);
  animation: success-pop var(--duration-slow) var(--ease-spring) both;
}

.success-checkmark__icon {
  filter: drop-shadow(0 4px 16px rgba(45, 159, 111, 0.35));
}

.success-title {
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  color: var(--color-text-primary);
  margin: 0;
  line-height: var(--leading-tight);
}

.success-subtitle {
  font-size: var(--text-base);
  color: var(--color-text-secondary);
  margin: 0;
}

.success-amount {
  margin-top: var(--space-2);
}

.success-screen__actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  width: 100%;
  max-width: 360px;
}

@keyframes success-pop {
  0% {
    opacity: 0;
    transform: scale(0.4);
  }
  70% {
    transform: scale(1.12);
  }
  100% {
    opacity: 1;
    transform: scale(1);
  }
}

@media (prefers-reduced-motion: reduce) {
  .success-checkmark {
    animation: none;
  }
}
</style>
