<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Banknote, CreditCard, FileText, Check, UserPlus, User } from 'lucide-vue-next'
import { useCartStore } from '@/stores/cart'
import { useSessionStore } from '@/stores/session'
import { useSalesStore } from '@/stores/sales'
import { useCustomersStore } from '@/stores/customers'
import { useIdempotency } from '@/composables/useIdempotency'
import { useToast } from '@/composables/useToast'
import { PaymentMethod } from '@/types/enums'
import type { Customer } from '@/types/models'
import BaseButton from '@/components/base/BaseButton.vue'
import PriceDisplay from '@/components/data/PriceDisplay.vue'
import SaleSuccessScreen from '../components/SaleSuccessScreen.vue'
import CustomerSelectSheet from '../components/CustomerSelectSheet.vue'

// ==============================
// Stores & composables
// ==============================

const router = useRouter()
const cartStore = useCartStore()
const sessionStore = useSessionStore()
const salesStore = useSalesStore()
const customersStore = useCustomersStore()
const { generateRequestId } = useIdempotency()
const toast = useToast()

// ==============================
// View state
// ==============================

type ViewState = 'checkout' | 'success'
const viewState = ref<ViewState>('checkout')
const completedSaleTotal = ref<string>('0')

// ==============================
// Payment method
// ==============================

interface PaymentOption {
  value: PaymentMethod
  label: string
  icon: typeof Banknote
}

const paymentOptions: PaymentOption[] = [
  { value: PaymentMethod.CASH,   label: 'Наличные', icon: Banknote },
  { value: PaymentMethod.CARD,   label: 'Карта',    icon: CreditCard },
  { value: PaymentMethod.CREDIT, label: 'В долг',   icon: FileText },
]

const selectedMethod = ref<PaymentMethod>(PaymentMethod.CASH)
const creditRequired = computed(() => selectedMethod.value === PaymentMethod.CREDIT)

function selectPaymentMethod(method: PaymentMethod): void {
  selectedMethod.value = method
  if (method !== PaymentMethod.CREDIT) {
    selectedCustomer.value = null
  }
}

// ==============================
// Customer
// ==============================

const selectedCustomer = ref<Customer | null>(null)
const showCustomerSheet = ref(false)

async function openCustomerSheet(): Promise<void> {
  showCustomerSheet.value = true
  if (customersStore.customers.length === 0) {
    await customersStore.fetchCustomers()
  }
}

function onCustomerSelected(customer: Customer): void {
  selectedCustomer.value = { ...customer }
  showCustomerSheet.value = false
}

function deselectCustomer(): void {
  selectedCustomer.value = null
}

// ==============================
// Submit
// ==============================

const canSubmit = computed(
  () => !cartStore.isEmpty && sessionStore.isOpen && !(creditRequired.value && !selectedCustomer.value),
)

async function confirmSale(): Promise<void> {
  if (creditRequired.value && !selectedCustomer.value) {
    toast.error('Выберите покупателя для продажи в долг')
    return
  }

  if (!sessionStore.currentSession) {
    toast.error('Нет активной кассовой смены')
    return
  }

  const lines = cartStore.items.map((item) => ({
    product_variant_id: item.product_variant.id,
    quantity: item.quantity,
    unit_price: parseFloat(item.unit_price),
    ...(item.lot_id !== null ? { lot_id: item.lot_id } : {}),
  }))

  try {
    const sale = await salesStore.createSale({
      client_request_id: generateRequestId(),
      pos_session_id: sessionStore.currentSession.id,
      payment_method: selectedMethod.value,
      ...(selectedCustomer.value ? { customer_id: selectedCustomer.value.id } : {}),
      lines,
    })
    completedSaleTotal.value = sale.total_amount
    cartStore.clear()
    viewState.value = 'success'
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Не удалось оформить продажу'
    toast.error(message)
  }
}

// ==============================
// Navigation
// ==============================

function goBack(): void {
  router.push('/sales/cart')
}

function startNewSale(): void {
  router.push('/sales')
}

function goToHistory(): void {
  router.push('/sales/history')
}
</script>

<template>
  <div class="checkout-view">
    <!-- Success screen overlay -->
    <Transition name="success-screen">
      <SaleSuccessScreen
        v-if="viewState === 'success'"
        :total-amount="completedSaleTotal"
        @new-sale="startNewSale"
        @history="goToHistory"
      />
    </Transition>

    <!-- Checkout flow -->
    <template v-if="viewState === 'checkout'">
      <!-- Header -->
      <header class="checkout-header">
        <button class="back-btn" aria-label="Назад" @click="goBack">
          <ArrowLeft :size="20" :stroke-width="2" />
        </button>
        <h1 class="checkout-title">Оформление</h1>
        <div class="header-spacer" />
      </header>

      <main class="checkout-content">
        <!-- Amount hero -->
        <section class="amount-section" aria-label="Сумма к оплате">
          <p class="amount-label">Сумма к оплате</p>
          <PriceDisplay :amount="cartStore.total" size="xl" />
          <p class="amount-meta">
            {{ cartStore.itemCount }}
            {{
              cartStore.itemCount === 1
                ? 'товар'
                : cartStore.itemCount < 5
                  ? 'товара'
                  : 'товаров'
            }}
          </p>
        </section>

        <!-- Payment method -->
        <section class="section" aria-labelledby="payment-heading">
          <h2 id="payment-heading" class="section-heading">Способ оплаты</h2>
          <div class="payment-grid" role="radiogroup" aria-label="Способ оплаты">
            <button
              v-for="option in paymentOptions"
              :key="option.value"
              class="payment-card"
              :class="{ 'payment-card--selected': selectedMethod === option.value }"
              role="radio"
              :aria-checked="selectedMethod === option.value"
              @click="selectPaymentMethod(option.value)"
            >
              <div class="payment-card__icon-wrap" aria-hidden="true">
                <component :is="option.icon" :size="24" :stroke-width="1.75" />
              </div>
              <span class="payment-card__label">{{ option.label }}</span>
              <div v-if="selectedMethod === option.value" class="payment-card__check" aria-hidden="true">
                <Check :size="14" :stroke-width="2.5" />
              </div>
            </button>
          </div>
        </section>

        <!-- Customer -->
        <section class="section" aria-labelledby="customer-heading">
          <h2 id="customer-heading" class="section-heading">
            Покупатель
            <span v-if="creditRequired" class="required-badge">обязательно</span>
          </h2>

          <!-- Selected customer chip -->
          <div v-if="selectedCustomer" class="selected-customer">
            <div class="selected-customer__avatar" aria-hidden="true">
              <User :size="18" :stroke-width="1.75" />
            </div>
            <div class="selected-customer__info">
              <span class="selected-customer__name">{{ selectedCustomer.name }}</span>
              <span v-if="selectedCustomer.phone" class="selected-customer__phone">
                {{ selectedCustomer.phone }}
              </span>
            </div>
            <button
              class="selected-customer__remove"
              aria-label="Убрать покупателя"
              @click="deselectCustomer"
            >
              ×
            </button>
          </div>

          <!-- Select button -->
          <button
            v-else
            class="customer-select-btn"
            :class="{ 'customer-select-btn--required': creditRequired }"
            @click="openCustomerSheet"
          >
            <UserPlus :size="20" :stroke-width="1.75" aria-hidden="true" />
            <span>
              {{ creditRequired ? 'Выберите покупателя' : 'Добавить покупателя (опционально)' }}
            </span>
          </button>
        </section>

        <!-- Order summary -->
        <section class="section" aria-labelledby="order-heading">
          <h2 id="order-heading" class="section-heading">Состав заказа</h2>
          <ul class="order-lines" aria-label="Позиции заказа">
            <li
              v-for="(item, index) in cartStore.items"
              :key="`${item.product_variant.id}-${index}`"
              class="order-line"
            >
              <span class="order-line__name">{{ item.product_name }}</span>
              <span class="order-line__qty">× {{ item.quantity }}</span>
              <PriceDisplay
                :amount="parseFloat(item.unit_price) * item.quantity"
                size="sm"
              />
            </li>
          </ul>
          <div class="order-total-row">
            <span class="order-total-label">Итого</span>
            <PriceDisplay :amount="cartStore.total" size="md" />
          </div>
        </section>
      </main>

      <!-- Submit footer -->
      <footer class="checkout-footer">
        <BaseButton
          variant="primary"
          size="lg"
          :full-width="true"
          :loading="salesStore.isCreating"
          :disabled="!canSubmit"
          @click="confirmSale"
        >
          <Check :size="18" :stroke-width="2.5" aria-hidden="true" />
          Подтвердить продажу
        </BaseButton>
      </footer>
    </template>

    <!-- Customer selection sheet -->
    <CustomerSelectSheet
      :open="showCustomerSheet"
      :selected-customer-id="selectedCustomer?.id ?? null"
      @close="showCustomerSheet = false"
      @select="onCustomerSelected"
    />
  </div>
</template>

<style scoped>
/* ==============================
   Layout
   ============================== */
.checkout-view {
  display: flex;
  flex-direction: column;
  min-height: 100dvh;
  background: var(--color-bg-primary);
}

/* ==============================
   Header
   ============================== */
.checkout-header {
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

.checkout-title {
  flex: 1;
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--color-text-primary);
  line-height: var(--leading-tight);
}

.header-spacer {
  width: 40px;
  flex-shrink: 0;
}

/* ==============================
   Content
   ============================== */
.checkout-content {
  flex: 1;
  padding: var(--space-4);
  padding-bottom: calc(var(--space-4) + 88px);
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

/* ==============================
   Amount section
   ============================== */
.amount-section {
  background: var(--color-bg-elevated);
  border-radius: var(--radius-xl);
  padding: var(--space-6) var(--space-5);
  text-align: center;
  box-shadow: var(--shadow-md);
  border: 1px solid var(--color-border-subtle);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
}

.amount-label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin: 0;
}

.amount-meta {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  margin: 0;
}

/* ==============================
   Sections
   ============================== */
.section {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.section-heading {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  margin: 0;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.required-badge {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--color-error);
  background: var(--color-error-bg);
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
}

/* ==============================
   Payment method grid
   ============================== */
.payment-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-3);
}

.payment-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-4) var(--space-3);
  background: var(--color-bg-elevated);
  border: 2px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition:
    border-color var(--duration-fast) var(--ease-out),
    background var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-out),
    box-shadow var(--duration-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
  user-select: none;
}

.payment-card:hover {
  border-color: var(--color-brand-300);
  background: var(--color-brand-50);
}

.payment-card:active {
  transform: scale(0.96);
}

.payment-card--selected {
  border-color: var(--color-brand-500);
  background: var(--color-brand-50);
  box-shadow: 0 0 0 3px var(--color-brand-100);
}

.payment-card__icon-wrap {
  color: var(--color-text-secondary);
  transition: color var(--duration-fast) var(--ease-out);
}

.payment-card--selected .payment-card__icon-wrap {
  color: var(--color-brand-500);
}

.payment-card__label {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  text-align: center;
  line-height: var(--leading-tight);
}

.payment-card__check {
  position: absolute;
  top: var(--space-2);
  right: var(--space-2);
  width: 20px;
  height: 20px;
  background: var(--color-brand-500);
  border-radius: var(--radius-full);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}

/* ==============================
   Customer
   ============================== */
.customer-select-btn {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  width: 100%;
  padding: var(--space-4);
  background: var(--color-bg-elevated);
  border: 2px dashed var(--color-border-default);
  border-radius: var(--radius-lg);
  font-size: var(--text-base);
  color: var(--color-text-secondary);
  cursor: pointer;
  text-align: left;
  transition:
    border-color var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out),
    background var(--duration-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
}

.customer-select-btn:hover {
  border-color: var(--color-brand-400);
  color: var(--color-brand-500);
  background: var(--color-brand-50);
}

.customer-select-btn--required {
  border-color: var(--color-error);
  color: var(--color-error);
}

.customer-select-btn--required:hover {
  background: var(--color-error-bg);
}

.selected-customer {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--color-brand-50);
  border: 1.5px solid var(--color-brand-200);
  border-radius: var(--radius-lg);
}

.selected-customer__avatar {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-full);
  background: var(--color-brand-100);
  color: var(--color-brand-600);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.selected-customer__info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.selected-customer__name {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.selected-customer__phone {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.selected-customer__remove {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  font-size: var(--text-xl);
  color: var(--color-text-tertiary);
  line-height: 1;
  flex-shrink: 0;
  transition:
    background var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
}

.selected-customer__remove:hover {
  background: var(--color-error-bg);
  color: var(--color-error);
}

/* ==============================
   Order summary
   ============================== */
.order-lines {
  list-style: none;
  padding: 0;
  margin: 0;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.order-line {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--color-border-subtle);
}

.order-line:last-child {
  border-bottom: none;
}

.order-line__name {
  flex: 1;
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.order-line__qty {
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
  white-space: nowrap;
  flex-shrink: 0;
}

.order-total-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  margin-top: var(--space-1);
}

.order-total-label {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-secondary);
}

/* ==============================
   Footer
   ============================== */
.checkout-footer {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: var(--z-sticky);
  background: var(--color-bg-elevated);
  border-top: 1px solid var(--color-border-default);
  box-shadow: var(--shadow-lg);
  padding: var(--space-4);
  padding-bottom: calc(var(--space-4) + env(safe-area-inset-bottom, 0px));
  max-width: 540px;
  margin: 0 auto;
}

/* ==============================
   Success screen transition
   ============================== */
.success-screen-enter-active {
  animation: success-screen-in var(--duration-slow) var(--ease-out);
}

.success-screen-leave-active {
  animation: success-screen-in var(--duration-fast) var(--ease-in) reverse;
}

@keyframes success-screen-in {
  from {
    opacity: 0;
    transform: translateY(24px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ==============================
   Responsive
   ============================== */
@media (min-width: 768px) {
  .checkout-view {
    max-width: 540px;
    margin: 0 auto;
  }

  .checkout-footer {
    left: 50%;
    transform: translateX(-50%);
    border-radius: var(--radius-xl) var(--radius-xl) 0 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .success-screen-enter-active,
  .success-screen-leave-active {
    animation: none;
  }
}
</style>
