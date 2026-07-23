<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useCartStore } from '@/stores/cart'
import { ShoppingCart } from 'lucide-vue-next'
import { formatPrice } from '@/utils/currency'

const router = useRouter()
const { t } = useI18n()
const cart = useCartStore()

const isVisible = computed(() => !cart.isEmpty)

const displayTotal = computed(() => formatPrice(cart.total))

function goToCart() {
  router.push('/sales/cart')
}
</script>

<template>
  <Transition name="cart-float">
    <button
      v-if="isVisible"
      class="floating-cart"
      :aria-label="t('sales.cart')"
      @click="goToCart"
    >
      <ShoppingCart :size="20" :stroke-width="1.75" />
      <span class="cart-count">{{ cart.itemCount }}</span>
      <span class="cart-divider" aria-hidden="true"></span>
      <span class="cart-total tabular-nums">{{ displayTotal }}</span>
    </button>
  </Transition>
</template>

<style scoped>
.floating-cart {
  position: fixed;
  bottom: calc(var(--bottom-nav-height) + env(safe-area-inset-bottom, 0px) + var(--space-4));
  right: var(--space-4);
  z-index: var(--z-float);

  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-5);
  height: 52px;

  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  border: none;
  border-radius: var(--radius-full);
  box-shadow: var(--shadow-float);

  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  white-space: nowrap;
  cursor: pointer;

  transition: transform var(--duration-fast) var(--ease-spring),
              background var(--duration-fast) var(--ease-out);
}

@media (min-width: 768px) {
  .floating-cart {
    bottom: var(--space-6);
    right: var(--space-6);
  }
}

.floating-cart:hover {
  background: var(--color-brand-600);
}

.floating-cart:active {
  transform: scale(0.96);
}

.cart-count {
  font-weight: var(--font-bold);
  font-size: var(--text-base);
}

.cart-divider {
  width: 1px;
  height: 20px;
  background: rgba(255, 255, 255, 0.3);
}

.cart-total {
  font-family: var(--font-mono);
  font-size: var(--text-sm);
}

/* Entry/exit animation */
.cart-float-enter-active {
  animation: cart-enter var(--duration-normal) var(--ease-spring);
}

.cart-float-leave-active {
  animation: cart-leave var(--duration-fast) var(--ease-in);
}

@keyframes cart-enter {
  0% {
    opacity: 0;
    transform: translateY(20px) scale(0.8);
  }
  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes cart-leave {
  0% {
    opacity: 1;
    transform: scale(1);
  }
  100% {
    opacity: 0;
    transform: scale(0.8);
  }
}
</style>
