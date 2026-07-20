<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ShoppingBag, ShoppingCart, ArrowLeft, Trash2, CircleAlert } from 'lucide-vue-next'
import { useCartStore } from '@/stores/cart'
import { useSessionStore } from '@/stores/session'
import { useFxRate } from '@/composables/useFxRate'
import { useToast } from '@/composables/useToast'
import { intlLocale } from '@/i18n/format'
import { formatPrice } from '@/utils/currency'
import BaseButton from '@/components/base/BaseButton.vue'
import QuantityControl from '@/components/forms/QuantityControl.vue'
import PageChrome from '@/components/layout/PageChrome.vue'
import PageContainer from '@/components/layout/PageContainer.vue'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

const router = useRouter()
const cartStore = useCartStore()
const sessionStore = useSessionStore()
const toast = useToast()
const { t, locale } = useI18n()
const {
  rate: latestUsdRate,
  error: latestUsdRateError,
  load: loadUsdRate,
} = useFxRate({ baseCurrency: 'USD', quoteCurrency: 'UZS' })

const removingIndex = ref<number | null>(null)
const showClearConfirm = ref(false)

const lineNativeTotal = computed(() =>
  (index: number): number => {
    const item = cartStore.items[index]
    if (!item) return 0
    return parseFloat(item.operation_unit_price ?? item.unit_price) * item.quantity
  },
)

const cartBlocked = computed(() =>
  !sessionStore.isOpen || cartStore.hasAvailabilityIssues || cartStore.hasLocationMismatch,
)

const cartBlockReason = computed(() => {
  if (!sessionStore.isOpen) return t('sales.cartBlockedNoSession')
  if (cartStore.hasLocationMismatch) return t('sales.cartBlockedLocation')
  if (cartStore.hasAvailabilityIssues) return t('sales.cartBlockedStock')
  return ''
})

function itemAvailableStock(index: number): number {
  const stock = cartStore.items[index]?.available_stock
  return typeof stock === 'number' && Number.isFinite(stock) ? stock : 9999
}

function goBack(): void {
  router.push('/sales')
}

function goToCheckout(): void {
  router.push('/sales/checkout')
}

function openSession(): void {
  router.push({ name: 'sales-catalog', query: { openSession: '1' } })
}

function handleQuantityChange(index: number, qty: number): void {
  cartStore.updateQuantity(index, qty)
}

async function setLineCurrency(index: number, currency: 'UZS' | 'USD'): Promise<void> {
  if (currency === 'USD' && !latestUsdRate.value) {
    try {
      await loadUsdRate()
    } catch {
      toast.error(latestUsdRateError.value || t('products.usdRateMissing'))
      return
    }
  }
  cartStore.updateItemCurrency(index, currency, currency === 'USD' ? latestUsdRate.value : '1')
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

function updateClearConfirm(open: boolean): void {
  showClearConfirm.value = open
}
</script>

<template>
  <div class="cart-view">
    <PageChrome class="desktop-page-chrome" :title="t('sales.cart')">
      <template #primary>
        <div class="desktop-header-actions">
          <button class="back-btn" :aria-label="t('common.back')" @click="goBack">
            <ArrowLeft :size="20" :stroke-width="2" />
          </button>
          <button
            v-if="!cartStore.isEmpty"
            class="clear-btn"
            :aria-label="t('sales.clearCart')"
            @click="handleClearRequest"
          >
            <Trash2 :size="18" :stroke-width="1.75" />
            <span>{{ t('sales.clearCart') }}</span>
          </button>
        </div>
      </template>
    </PageChrome>

    <!-- Header -->
    <header class="cart-header">
      <button class="back-btn" :aria-label="t('common.back')" @click="goBack">
        <ArrowLeft :size="20" :stroke-width="2" />
      </button>
      <h1 class="cart-title">{{ t('sales.cart') }}</h1>
      <button
        v-if="!cartStore.isEmpty"
        class="clear-btn"
        :aria-label="t('sales.clearCart')"
        @click="handleClearRequest"
      >
        <Trash2 :size="18" :stroke-width="1.75" />
        <span>{{ t('sales.clearCart') }}</span>
      </button>
      <div v-else class="header-spacer" />
    </header>

    <PageContainer class="cart-container" size="wide" :padded="false">
    <!-- No session warning -->
    <div v-if="!sessionStore.isOpen" class="session-warning">
      <div class="session-warning__icon">
        <CircleAlert :size="18" :stroke-width="2" />
      </div>
      <div class="session-warning__body">
        <p class="session-warning__title">{{ t('sales.noOpenShift') }}</p>
        <p class="session-warning__text">{{ t('sales.cartOpenShiftHint') }}</p>
      </div>
      <BaseButton variant="secondary" size="sm" @click="openSession">
        {{ t('sales.openShift') }}
      </BaseButton>
    </div>

    <div class="cart-workspace">
    <!-- Cart content -->
    <main class="cart-content">
      <!-- Empty state -->
      <div v-if="cartStore.isEmpty" class="empty-state">
        <div class="empty-state__icon-wrap">
          <ShoppingCart :size="56" :stroke-width="1.25" class="empty-state__icon" />
        </div>
        <h2 class="empty-state__title">{{ t('sales.emptyCart') }}</h2>
        <p class="empty-state__subtitle">{{ t('sales.addFromCatalog') }}</p>
        <BaseButton variant="primary" size="md" @click="goBack">
          {{ t('sales.goToCatalog') }}
        </BaseButton>
      </div>

      <!-- Items list -->
      <TransitionGroup
        v-else
        name="cart-item"
        tag="ul"
        class="cart-list"
        :aria-label="t('sales.cartItemsAria')"
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
                {{ formatPrice(item.operation_unit_price ?? item.unit_price, item.operation_currency ?? 'UZS') }} / {{ t('common.pieces') }}
              </span>
              <span
                v-if="item.operation_currency === 'USD'"
                class="cart-item__price-change"
              >
                {{ formatPrice(item.unit_price, 'UZS') }} · {{ t('finance.rate') }} {{ Number(item.fx_rate || 0).toLocaleString(intlLocale(locale), { maximumFractionDigits: 2 }) }}
              </span>
              <span v-if="item.price_changed" class="cart-item__price-change">
                {{ t('common.base') }}: {{ formatPrice(item.base_price) }}
              </span>
            </div>
            <button
              class="cart-item__remove"
              :aria-label="t('sales.removeProduct', { name: item.product_name })"
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
              :max="itemAvailableStock(index)"
              @update:model-value="handleQuantityChange(index, $event)"
            />
            <div class="cart-item__money">
              <div class="line-currency-toggle">
                <button
                  type="button"
                  :class="{ active: (item.operation_currency ?? 'UZS') === 'UZS' }"
                  @click="setLineCurrency(index, 'UZS')"
                >
                  UZS
                </button>
                <button
                  type="button"
                  :class="{ active: item.operation_currency === 'USD' }"
                  @click="setLineCurrency(index, 'USD')"
                >
                  USD
                </button>
              </div>
              <strong class="cart-item__line-total">
                {{ formatPrice(lineNativeTotal(index), item.operation_currency ?? 'UZS') }}
              </strong>
            </div>
          </div>
        </li>
      </TransitionGroup>
    </main>

    <!-- Sticky bottom bar -->
    <footer v-if="!cartStore.isEmpty" class="cart-footer">
      <div class="cart-footer__summary">
        <span class="cart-footer__label">{{ t('common.total') }}</span>
        <div class="cart-footer__totals">
          <strong
            v-for="total in cartStore.totalsByCurrency"
            :key="total.currency"
          >
            {{ formatPrice(total.amount, total.currency) }}
          </strong>
        </div>
      </div>
      <p v-if="cartBlockReason" class="cart-footer__warning">
        {{ cartBlockReason }}
      </p>
      <BaseButton
        variant="primary"
        size="lg"
        :full-width="true"
        :disabled="cartBlocked"
        @click="goToCheckout"
      >
        {{ t('sales.checkoutOrder') }} →
      </BaseButton>
    </footer>
    </div>
    </PageContainer>

    <!-- Clear confirm dialog -->
    <Dialog :open="showClearConfirm" @update:open="updateClearConfirm">
      <DialogContent class="confirm-dialog">
        <DialogHeader>
          <DialogTitle>{{ t('sales.clearCartQuestion') }}</DialogTitle>
          <DialogDescription>{{ t('sales.clearCartText') }}</DialogDescription>
        </DialogHeader>
        <DialogFooter class="confirm-dialog__actions">
          <BaseButton variant="ghost" size="md" @click="cancelClear">
            {{ t('common.cancel') }}
          </BaseButton>
          <BaseButton variant="danger" size="md" @click="confirmClear">
            {{ t('sales.clearCart') }}
          </BaseButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
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

.desktop-page-chrome {
  display: none;
}

.desktop-header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
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

.cart-item__price-change {
  font-size: 10px;
  color: var(--color-warning);
  text-transform: uppercase;
  letter-spacing: 0.04em;
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
  gap: var(--space-3);
  padding-top: var(--space-2);
  border-top: 1px solid var(--color-border-subtle);
}

.cart-item__money {
  display: grid;
  justify-items: end;
  gap: var(--space-2);
  min-width: 128px;
}

.line-currency-toggle {
  display: inline-flex;
  padding: 2px;
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-subtle);
}

.line-currency-toggle button {
  min-width: 42px;
  height: 26px;
  padding: 0 var(--space-1);
  border-radius: calc(var(--radius-md) - 2px);
  color: var(--color-text-secondary);
  font-size: 11px;
  font-weight: var(--font-semibold);
}

.line-currency-toggle button.active {
  background: var(--color-bg-elevated);
  color: var(--color-brand-700);
  box-shadow: var(--shadow-sm);
}

.cart-item__line-total {
  color: var(--color-brand-600);
  font-size: var(--text-base);
  font-weight: var(--font-bold);
  white-space: nowrap;
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
  gap: var(--space-3);
}

.cart-footer__totals {
  display: grid;
  justify-items: end;
  gap: 2px;
  color: var(--color-text-primary);
  font-size: var(--text-lg);
  line-height: var(--leading-tight);
}

.cart-footer__warning {
  margin: calc(var(--space-2) * -1) 0 0;
  color: var(--color-warning);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
}

.cart-footer__label {
  font-size: var(--text-base);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
}

.confirm-dialog {
  max-width: 380px;
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

/* ==============================
   Responsive
   ============================== */
@media (min-width: 768px) {
  .cart-view {
    min-height: 100%;
  }

  .desktop-page-chrome {
    display: block;
  }

  .cart-header {
    display: none;
  }

  .cart-container {
    padding: var(--space-6) clamp(var(--space-5), 3vw, var(--space-8));
  }

  .session-warning {
    margin: 0 0 var(--space-5);
  }

  .cart-workspace {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(280px, 340px);
    align-items: start;
    gap: clamp(var(--space-5), 3vw, var(--space-8));
  }

  .cart-content {
    min-width: 0;
    padding: 0;
  }

  .cart-list {
    gap: 0;
    overflow: hidden;
    border: 1px solid var(--color-border-subtle);
    border-radius: var(--radius-xl);
    background: var(--color-bg-elevated);
  }

  .cart-item {
    border: 0;
    border-bottom: 1px solid var(--color-border-subtle);
    border-radius: 0;
    box-shadow: none;
  }

  .cart-item:last-child {
    border-bottom: 0;
  }

  .cart-footer {
    position: sticky;
    top: calc(var(--sticky-offset) + var(--space-4));
    right: auto;
    bottom: auto;
    left: auto;
    width: 100%;
    max-width: none;
    margin: 0;
    border: 1px solid var(--color-border-subtle);
    border-radius: var(--radius-xl);
    box-shadow: var(--shadow-sm);
    padding: var(--space-5);
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
