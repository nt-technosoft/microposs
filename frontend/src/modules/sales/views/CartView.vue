<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ShoppingBag, ShoppingCart, ArrowLeft, Trash2, CircleAlert } from 'lucide-vue-next'
import { useCartStore } from '@/stores/cart'
import { useSessionStore } from '@/stores/session'
import { formatPrice } from '@/utils/currency'
import BaseButton from '@/components/base/BaseButton.vue'
import QuantityControl from '@/components/forms/QuantityControl.vue'
import PriceDisplay from '@/components/data/PriceDisplay.vue'

const router = useRouter()
const cartStore = useCartStore()
const sessionStore = useSessionStore()

const removingIndex = ref<number | null>(null)
const showClearConfirm = ref(false)

const lineTotal = computed(() =>
  (index: number): number => {
    const item = cartStore.items[index]
    if (!item) return 0
    return parseFloat(item.unit_price) * item.quantity
  },
)

function goBack(): void {
  router.push('/sales')
}

function goToCheckout(): void {
  router.push('/sales/checkout')
}

function handleQuantityChange(index: number, qty: number): void {
  cartStore.updateQuantity(index, qty)
}

function handleRemove(index: number): void {
  removingIndex.value = index
  setTimeout(() => {
    cartStore.removeItem(index)
    removingIndex.value = null
  }, 250)
}

function handleClearRequest(): void {
  showClearConfirm.value = true
}

function confirmClear(): void {
  cartStore.clear()
  showClearConfirm.value = false
}

function cancelClear(): void {
  showClearConfirm.value = false
}
</script>

<template>
  <div class="cart-view">
    <!-- Header -->
    <header class="cart-header">
      <button class="back-btn" aria-label="Назад" @click="goBack">
        <ArrowLeft :size="20" :stroke-width="2" />
      </button>
      <h1 class="cart-title">Корзина</h1>
      <button
        v-if="!cartStore.isEmpty"
        class="clear-btn"
        aria-label="Очистить корзину"
        @click="handleClearRequest"
      >
        <Trash2 :size="18" :stroke-width="1.75" />
        <span>Очистить</span>
      </button>
      <div v-else class="header-spacer" />
    </header>

    <!-- No session warning -->
    <div v-if="!sessionStore.isOpen" class="session-warning">
      <div class="session-warning__icon">
        <CircleAlert :size="18" :stroke-width="2" />
      </div>
      <div class="session-warning__body">
        <p class="session-warning__title">Нет открытой смены</p>
        <p class="session-warning__text">Откройте кассовую смену, чтобы оформлять продажи</p>
      </div>
      <BaseButton variant="secondary" size="sm" @click="router.push('/sales')">
        В каталог
      </BaseButton>
    </div>

    <!-- Cart content -->
    <main class="cart-content">
      <!-- Empty state -->
      <div v-if="cartStore.isEmpty" class="empty-state">
        <div class="empty-state__icon-wrap">
          <ShoppingCart :size="56" :stroke-width="1.25" class="empty-state__icon" />
        </div>
        <h2 class="empty-state__title">Корзина пуста</h2>
        <p class="empty-state__subtitle">Добавьте товары из каталога</p>
        <BaseButton variant="primary" size="md" @click="goBack">
          Перейти в каталог
        </BaseButton>
      </div>

      <!-- Items list -->
      <TransitionGroup
        v-else
        name="cart-item"
        tag="ul"
        class="cart-list"
        aria-label="Товары в корзине"
      >
        <li
          v-for="(item, index) in cartStore.items"
          :key="`${item.product_variant.id}-${item.lot_id}-${item.unit_price}`"
          class="cart-item"
          :class="{ 'cart-item--removing': removingIndex === index }"
        >
          <!-- Item header row -->
          <div class="cart-item__header">
            <div class="cart-item__icon-wrap" aria-hidden="true">
              <ShoppingBag :size="20" :stroke-width="1.75" />
            </div>
            <div class="cart-item__info">
              <span class="cart-item__name">{{ item.product_name }}</span>
              <span class="cart-item__unit-price">
                {{ formatPrice(item.unit_price) }} / шт.
              </span>
            </div>
            <button
              class="cart-item__remove"
              aria-label="`Удалить ${item.product_name}`"
              @click="handleRemove(index)"
            >
              ×
            </button>
          </div>

          <!-- Item controls row -->
          <div class="cart-item__controls">
            <QuantityControl
              :model-value="item.quantity"
              :min="1"
              :max="9999"
              @update:model-value="handleQuantityChange(index, $event)"
            />
            <PriceDisplay
              :amount="lineTotal(index)"
              size="md"
              class="cart-item__line-total"
            />
          </div>
        </li>
      </TransitionGroup>
    </main>

    <!-- Sticky bottom bar -->
    <footer v-if="!cartStore.isEmpty" class="cart-footer">
      <div class="cart-footer__summary">
        <span class="cart-footer__label">Итого</span>
        <PriceDisplay :amount="cartStore.total" size="lg" />
      </div>
      <BaseButton
        variant="primary"
        size="lg"
        :full-width="true"
        :disabled="!sessionStore.isOpen"
        @click="goToCheckout"
      >
        Оформить заказ →
      </BaseButton>
    </footer>

    <!-- Clear confirm dialog -->
    <Teleport to="body">
      <Transition name="overlay">
        <div v-if="showClearConfirm" class="confirm-overlay" @click.self="cancelClear">
          <div class="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-title">
            <h3 id="confirm-title" class="confirm-dialog__title">Очистить корзину?</h3>
            <p class="confirm-dialog__text">Все добавленные товары будут удалены.</p>
            <div class="confirm-dialog__actions">
              <BaseButton variant="ghost" size="md" @click="cancelClear">
                Отмена
              </BaseButton>
              <BaseButton variant="danger" size="md" @click="confirmClear">
                Очистить
              </BaseButton>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
/* ==============================
   Layout
   ============================== */
.cart-view {
  display: flex;
  flex-direction: column;
  min-height: 100dvh;
  background: var(--color-bg-primary);
}

/* ==============================
   Header
   ============================== */
.cart-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  height: var(--header-height);
  padding: 0 var(--space-4);
  background: var(--color-bg-elevated);
  border-bottom: 1px solid var(--color-border-subtle);
  box-shadow: var(--shadow-sm);
}

.back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  flex-shrink: 0;
  transition: background var(--duration-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
}

.back-btn:hover {
  background: var(--color-bg-secondary);
}

.cart-title {
  flex: 1;
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--color-text-primary);
  line-height: var(--leading-tight);
}

.clear-btn {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-error);
  transition: background var(--duration-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
}

.clear-btn:hover {
  background: var(--color-error-bg);
}

.header-spacer {
  width: 40px;
  flex-shrink: 0;
}

/* ==============================
   Session warning
   ============================== */
.session-warning {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin: var(--space-4);
  padding: var(--space-4);
  background: var(--color-warning-bg);
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-lg);
}

.session-warning__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--color-warning);
  flex-shrink: 0;
}

.session-warning__body {
  flex: 1;
  min-width: 0;
}

.session-warning__title {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.session-warning__text {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  margin-top: var(--space-1);
  line-height: var(--leading-normal);
}

/* ==============================
   Content
   ============================== */
.cart-content {
  flex: 1;
  padding: var(--space-4);
  padding-bottom: calc(
    var(--space-4) + 140px + var(--bottom-nav-height) + env(safe-area-inset-bottom, 0px)
  ); /* room for footer + bottom nav */
}

/* ==============================
   Empty state
   ============================== */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--space-16) var(--space-8);
  gap: var(--space-4);
}

.empty-state__icon-wrap {
  width: 96px;
  height: 96px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-brand-50);
  border-radius: var(--radius-full);
  color: var(--color-brand-400);
}

.empty-state__title {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--color-text-primary);
  margin: 0;
}

.empty-state__subtitle {
  font-size: var(--text-base);
  color: var(--color-text-secondary);
  margin: 0;
}

/* ==============================
   Cart list
   ============================== */
.cart-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  list-style: none;
  margin: 0;
  padding: 0;
}

/* ==============================
   Cart item card
   ============================== */
.cart-item {
  background: var(--color-bg-elevated);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  border: 1px solid var(--color-border-subtle);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  transition:
    opacity var(--duration-fast) var(--ease-in),
    transform var(--duration-fast) var(--ease-in);
}

.cart-item--removing {
  opacity: 0;
  transform: translateX(40px);
}

.cart-item__header {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
}

.cart-item__icon-wrap {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  background: var(--color-brand-50);
  color: var(--color-brand-500);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.cart-item__info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.cart-item__name {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  line-height: var(--leading-tight);
  /* Truncate long names */
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cart-item__unit-price {
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
  font-family: var(--font-mono);
}

.cart-item__remove {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  font-size: var(--text-xl);
  font-weight: var(--font-normal);
  color: var(--color-text-tertiary);
  line-height: 1;
  flex-shrink: 0;
  transition:
    background var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
}

.cart-item__remove:hover {
  background: var(--color-error-bg);
  color: var(--color-error);
}

.cart-item__controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: var(--space-2);
  border-top: 1px solid var(--color-border-subtle);
}

.cart-item__line-total {
  font-size: var(--text-lg) !important;
  color: var(--color-brand-600) !important;
}

/* ==============================
   Footer
   ============================== */
.cart-footer {
  position: fixed;
  bottom: calc(var(--bottom-nav-height) + env(safe-area-inset-bottom, 0px));
  left: 0;
  right: 0;
  z-index: var(--z-sticky);
  background: var(--color-bg-elevated);
  border-top: 1px solid var(--color-border-default);
  box-shadow: var(--shadow-lg);
  padding: var(--space-4) var(--space-4);
  padding-bottom: calc(var(--space-4) + env(safe-area-inset-bottom, 0px));
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  max-width: 540px;
  margin: 0 auto;
}

.cart-footer__summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.cart-footer__label {
  font-size: var(--text-base);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
}

/* ==============================
   Confirm dialog overlay
   ============================== */
.confirm-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  z-index: var(--z-modal);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--space-6);
}

.confirm-dialog {
  background: var(--color-bg-elevated);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-xl);
  padding: var(--space-6);
  width: 100%;
  max-width: 340px;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.confirm-dialog__title {
  font-size: var(--text-lg);
  font-weight: var(--font-bold);
  color: var(--color-text-primary);
  margin: 0;
}

.confirm-dialog__text {
  font-size: var(--text-base);
  color: var(--color-text-secondary);
  margin: 0;
  line-height: var(--leading-normal);
}

.confirm-dialog__actions {
  display: flex;
  gap: var(--space-3);
  justify-content: flex-end;
}

/* ==============================
   Transitions
   ============================== */
.cart-item-enter-active {
  transition:
    opacity var(--duration-normal) var(--ease-out),
    transform var(--duration-normal) var(--ease-spring);
}

.cart-item-leave-active {
  transition:
    opacity var(--duration-fast) var(--ease-in),
    transform var(--duration-fast) var(--ease-in);
  position: absolute;
  width: 100%;
}

.cart-item-enter-from {
  opacity: 0;
  transform: translateY(-12px);
}

.cart-item-leave-to {
  opacity: 0;
  transform: translateX(40px);
}

.cart-item-move {
  transition: transform var(--duration-normal) var(--ease-out);
}

.overlay-enter-active,
.overlay-leave-active {
  transition: opacity var(--duration-fast) var(--ease-out);
}

.overlay-enter-from,
.overlay-leave-to {
  opacity: 0;
}

.overlay-enter-active .confirm-dialog {
  animation: dialog-in var(--duration-normal) var(--ease-spring);
}

@keyframes dialog-in {
  from {
    opacity: 0;
    transform: scale(0.92) translateY(8px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

/* ==============================
   Responsive
   ============================== */
@media (min-width: 768px) {
  .cart-view {
    max-width: 540px;
    margin: 0 auto;
  }

  .cart-footer {
    left: 50%;
    transform: translateX(-50%);
    border-radius: var(--radius-xl) var(--radius-xl) 0 0;
  }
}

@media (min-width: 1024px) {
  .cart-content {
    padding-bottom: calc(var(--space-4) + 140px);
  }

  .cart-footer {
    bottom: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .cart-item-enter-active,
  .cart-item-leave-active,
  .cart-item-move,
  .cart-item--removing,
  .overlay-enter-active,
  .overlay-leave-active {
    transition: none;
    animation: none;
  }
}
</style>
