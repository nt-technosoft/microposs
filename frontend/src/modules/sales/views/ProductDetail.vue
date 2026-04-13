<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Package, ShoppingCart, Check } from 'lucide-vue-next'
import { fetchProduct, fetchProductVariants } from '@/api/catalog'
import { useCartStore } from '@/stores/cart'
import type { Product, ProductVariant } from '@/types/models'
import QuantityControl from '@/components/forms/QuantityControl.vue'
import PriceDisplay from '@/components/data/PriceDisplay.vue'

// ===== Route + store =====
const route = useRoute()
const router = useRouter()
const cartStore = useCartStore()

// ===== State =====
const product = ref<Product | null>(null)
const variants = ref<ProductVariant[]>([])
const isLoading = ref(true)
const loadError = ref<string | null>(null)

// User's selection: attribute_name → chosen value string
const selectedAttributes = ref<Record<string, string>>({})
const quantity = ref(1)
const isAdded = ref(false)
let addedTimer: ReturnType<typeof setTimeout> | null = null

// ===== Derived attribute groups =====

/** All unique attribute names across all variants */
const attributeNames = computed((): string[] => {
  const names = new Set<string>()
  variants.value.forEach((v) =>
    v.attribute_values.forEach((av) => names.add(av.attribute_name)),
  )
  return [...names]
})

/** All unique values for each attribute name */
const attributeOptions = computed((): Record<string, string[]> => {
  const result: Record<string, string[]> = {}
  attributeNames.value.forEach((name) => {
    const values = new Set<string>()
    variants.value.forEach((v) => {
      const match = v.attribute_values.find((av) => av.attribute_name === name)
      if (match) values.add(match.value)
    })
    result[name] = [...values]
  })
  return result
})

/** Find variant that exactly matches all currently selected attributes */
const matchedVariant = computed((): ProductVariant | null => {
  if (attributeNames.value.length === 0) return variants.value[0] ?? null

  const selectedKeys = Object.keys(selectedAttributes.value)
  if (selectedKeys.length !== attributeNames.value.length) return null

  return (
    variants.value.find((v) =>
      attributeNames.value.every((name) => {
        const av = v.attribute_values.find((a) => a.attribute_name === name)
        return av?.value === selectedAttributes.value[name]
      }),
    ) ?? null
  )
})

/** Is a given attribute value selectable (leads to ≥1 active variant)? */
function isValueAvailable(attrName: string, value: string): boolean {
  // Build hypothetical selection with this value applied
  const hypothetical: Record<string, string> = {
    ...selectedAttributes.value,
    [attrName]: value,
  }

  return variants.value.some((v) => {
    if (!v.is_active) return false
    return Object.entries(hypothetical).every(([name, val]) => {
      const av = v.attribute_values.find((a) => a.attribute_name === name)
      return av?.value === val
    })
  })
}

function isValueSelected(attrName: string, value: string): boolean {
  return selectedAttributes.value[attrName] === value
}

function selectAttribute(attrName: string, value: string) {
  if (!isValueAvailable(attrName, value)) return
  selectedAttributes.value = { ...selectedAttributes.value, [attrName]: value }
}

// ===== Effective price & stock =====

const effectivePrice = computed((): string => {
  if (matchedVariant.value) return matchedVariant.value.effective_price
  if (product.value?.base_price) return product.value.base_price
  if (variants.value.length > 0) return variants.value[0].effective_price
  return '0'
})

const stockQuantity = computed((): number | null => {
  if (matchedVariant.value?.stock_quantity !== undefined) {
    return matchedVariant.value.stock_quantity
  }
  return null
})

const canAddToCart = computed((): boolean => {
  if (!product.value) return false
  if (product.value.has_variants && !matchedVariant.value) return false
  if (stockQuantity.value !== null && stockQuantity.value <= 0) return false
  return true
})

const addButtonLabel = computed((): string => {
  if (!product.value?.has_variants || matchedVariant.value) {
    return `В корзину`
  }
  return 'Выберите вариант'
})

// ===== Add to cart =====

function addToCart() {
  if (!canAddToCart.value || !product.value) return

  const variant =
    matchedVariant.value ?? (product.value.has_variants ? null : variants.value[0] ?? null)

  if (!variant) return

  const price = effectivePrice.value

  cartStore.addItem({
    product_variant: variant,
    product_name: product.value.name,
    lot_id: null,
    quantity: quantity.value,
    unit_price: price,
    base_price: price,
    discount_reason_id: null,
  })

  isAdded.value = true
  if (addedTimer !== null) clearTimeout(addedTimer)
  addedTimer = setTimeout(() => {
    isAdded.value = false
    addedTimer = null
    router.back()
  }, 900)
}

function goBack() {
  router.back()
}

// ===== Load data =====

async function loadProduct() {
  const id = Number(route.params.id)
  if (Number.isNaN(id)) {
    loadError.value = 'Неверный идентификатор товара'
    isLoading.value = false
    return
  }

  isLoading.value = true
  loadError.value = null

  try {
    const [productData, variantsData] = await Promise.all([
      fetchProduct(id),
      fetchProductVariants(id),
    ])

    product.value = productData
    variants.value = variantsData

    // Pre-select first available value for each attribute
    if (productData.has_variants) {
      const firstVariant = variantsData.find((v) => v.is_active) ?? variantsData[0]
      if (firstVariant) {
        const preselect: Record<string, string> = {}
        firstVariant.attribute_values.forEach((av) => {
          preselect[av.attribute_name] = av.value
        })
        selectedAttributes.value = preselect
      }
    }
  } catch {
    loadError.value = 'Не удалось загрузить товар. Попробуйте ещё раз.'
  } finally {
    isLoading.value = false
  }
}

onMounted(() => {
  loadProduct()
})
</script>

<template>
  <div class="detail-page">

    <!-- ===== Header ===== -->
    <header class="detail-header">
      <button class="back-btn" aria-label="Назад" @click="goBack">
        <ArrowLeft :size="20" :stroke-width="2" />
      </button>
      <h1 class="header-title">
        {{ product?.name ?? 'Товар' }}
      </h1>
      <div class="header-spacer" aria-hidden="true" />
    </header>

    <!-- ===== Loading state ===== -->
    <div v-if="isLoading" class="detail-loading" aria-busy="true" aria-label="Загрузка товара">
      <div class="skeleton-hero" />
      <div class="skeleton-body">
        <div class="skeleton-line skeleton-line--title" />
        <div class="skeleton-line skeleton-line--meta" />
        <div class="skeleton-chips-group">
          <div v-for="n in 4" :key="n" class="skeleton-chip" />
        </div>
        <div class="skeleton-line skeleton-line--price" />
        <div class="skeleton-line skeleton-line--btn" />
      </div>
    </div>

    <!-- ===== Error state ===== -->
    <div v-else-if="loadError" class="detail-error" role="alert">
      <Package :size="48" :stroke-width="1.25" class="error-icon" />
      <p class="error-message">{{ loadError }}</p>
      <button class="error-retry-btn" @click="loadProduct">
        Попробовать снова
      </button>
    </div>

    <!-- ===== Product content ===== -->
    <template v-else-if="product">
      <div class="detail-body">

        <!-- Product image / hero area -->
        <div class="product-hero">
          <div class="product-hero-inner">
            <Package :size="56" :stroke-width="1" class="hero-icon" />
          </div>
        </div>

        <!-- Info section -->
        <div class="product-info-section">

          <!-- Name -->
          <h2 class="product-name">{{ product.name }}</h2>

          <!-- Category + SKU row -->
          <div class="product-meta">
            <span v-if="product.category" class="meta-category">
              {{ product.category.name }}
            </span>
            <span
              v-if="product.category && matchedVariant?.sku"
              class="meta-separator"
              aria-hidden="true"
            >·</span>
            <span v-if="matchedVariant?.sku" class="meta-sku">
              {{ matchedVariant.sku }}
            </span>
          </div>

          <!-- Description -->
          <p v-if="product.description" class="product-description">
            {{ product.description }}
          </p>

        </div>

        <!-- ===== Variant selection ===== -->
        <template v-if="product.has_variants && attributeNames.length > 0">
          <div class="variants-section">
            <div
              v-for="attrName in attributeNames"
              :key="attrName"
              class="attr-group"
            >
              <p class="attr-name">{{ attrName }}</p>
              <div class="attr-chips" role="group" :aria-label="`Выбор: ${attrName}`">
                <button
                  v-for="value in attributeOptions[attrName]"
                  :key="value"
                  class="attr-chip"
                  :class="{
                    'attr-chip--selected': isValueSelected(attrName, value),
                    'attr-chip--disabled': !isValueAvailable(attrName, value),
                  }"
                  :aria-pressed="isValueSelected(attrName, value)"
                  :disabled="!isValueAvailable(attrName, value)"
                  @click="selectAttribute(attrName, value)"
                >
                  {{ value }}
                </button>
              </div>
            </div>
          </div>
        </template>

        <!-- ===== Price + stock ===== -->
        <div class="price-stock-section">
          <div class="price-row">
            <span class="price-label">Цена</span>
            <PriceDisplay :amount="effectivePrice" size="lg" />
          </div>

          <div v-if="stockQuantity !== null" class="stock-row">
            <span class="stock-label">В наличии</span>
            <span
              class="stock-value"
              :class="{ 'stock-value--empty': stockQuantity <= 0 }"
            >
              {{ stockQuantity > 0 ? `${stockQuantity} шт` : 'Нет в наличии' }}
            </span>
          </div>
        </div>

        <!-- ===== Quantity + add to cart ===== -->
        <div class="cart-section">
          <div class="qty-row">
            <span class="qty-label">Количество</span>
            <QuantityControl
              v-model="quantity"
              :min="1"
              :max="stockQuantity ?? 9999"
            />
          </div>

          <button
            class="add-to-cart-btn"
            :class="{
              'add-to-cart-btn--added': isAdded,
              'add-to-cart-btn--disabled': !canAddToCart,
            }"
            :disabled="!canAddToCart"
            :aria-label="addButtonLabel"
            @click="addToCart"
          >
            <Transition name="btn-icon" mode="out-in">
              <Check v-if="isAdded" :key="'check'" :size="20" :stroke-width="2.5" />
              <ShoppingCart v-else :key="'cart'" :size="20" :stroke-width="1.75" />
            </Transition>
            <span class="btn-label">
              <Transition name="btn-text" mode="out-in">
                <span v-if="isAdded" key="added">Добавлено!</span>
                <span v-else-if="!canAddToCart && product.has_variants && !matchedVariant" key="select">
                  Выберите вариант
                </span>
                <span v-else key="price">
                  {{ addButtonLabel }}&nbsp;—&nbsp;<PriceDisplay
                    :amount="(parseFloat(effectivePrice) * quantity).toFixed(2)"
                    size="md"
                    class="btn-price"
                  />
                </span>
              </Transition>
            </span>
          </button>
        </div>

      </div>
    </template>

  </div>
</template>

<style scoped>
/* ===== Page shell ===== */
.detail-page {
  display: flex;
  flex-direction: column;
  min-height: 100dvh;
  background: var(--color-bg-primary);
  padding-bottom: calc(var(--bottom-nav-height) + var(--space-4));
}

/* ===== Header ===== */
.detail-header {
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
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  flex-shrink: 0;
  transition:
    background var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-spring);
  -webkit-tap-highlight-color: transparent;
}

.back-btn:hover {
  background: var(--color-bg-secondary);
}

.back-btn:active {
  transform: scale(0.88);
  background: var(--color-bg-sunken);
}

.header-title {
  flex: 1;
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  line-height: var(--leading-tight);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-spacer {
  width: 44px;
  flex-shrink: 0;
}

/* ===== Loading skeleton ===== */
.detail-loading {
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.55; }
}

.skeleton-hero {
  width: 100%;
  padding-top: 56.25%; /* 16:9 */
  background: var(--color-bg-secondary);
}

.skeleton-body {
  padding: var(--space-5) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.skeleton-line {
  background: var(--color-bg-sunken);
  border-radius: var(--radius-sm);
}

.skeleton-line--title  { height: 1.5rem;  width: 70%; }
.skeleton-line--meta   { height: 0.875rem; width: 45%; }
.skeleton-line--price  { height: 1.75rem;  width: 40%; }
.skeleton-line--btn    { height: 52px;     width: 100%; border-radius: var(--radius-lg); }

.skeleton-chips-group {
  display: flex;
  gap: var(--space-2);
}

.skeleton-chip {
  height: 36px;
  width: 64px;
  background: var(--color-bg-sunken);
  border-radius: var(--radius-full);
}

/* ===== Error state ===== */
.detail-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-4);
  padding: var(--space-12) var(--space-6);
  text-align: center;
}

.error-icon {
  color: var(--color-text-tertiary);
}

.error-message {
  font-size: var(--text-base);
  color: var(--color-text-secondary);
  max-width: 300px;
}

.error-retry-btn {
  height: 44px;
  padding: 0 var(--space-6);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  transition: background var(--duration-fast) var(--ease-out);
}

.error-retry-btn:hover { background: var(--color-brand-600); }
.error-retry-btn:active { transform: scale(0.97); }

/* ===== Product body ===== */
.detail-body {
  display: flex;
  flex-direction: column;
}

/* ===== Hero image area — 16:9 ===== */
.product-hero {
  position: relative;
  width: 100%;
  padding-top: 56.25%;
  background: var(--color-bg-secondary);
  overflow: hidden;
  flex-shrink: 0;
}

.product-hero-inner {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(
    160deg,
    var(--color-brand-50) 0%,
    var(--color-bg-secondary) 100%
  );
}

.hero-icon {
  color: var(--color-brand-200);
}

/* ===== Info section ===== */
.product-info-section {
  padding: var(--space-5) var(--space-4) var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.product-name {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--color-text-primary);
  line-height: var(--leading-tight);
}

.product-meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.meta-category {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-brand-500);
  background: var(--color-brand-50);
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
}

.meta-separator {
  color: var(--color-text-tertiary);
  font-size: var(--text-sm);
}

.meta-sku {
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
  font-family: var(--font-mono);
}

.product-description {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: var(--leading-relaxed);
  margin-top: var(--space-1);
}

/* ===== Variant chips ===== */
.variants-section {
  padding: 0 var(--space-4) var(--space-2);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  border-top: 1px solid var(--color-border-subtle);
  padding-top: var(--space-4);
}

.attr-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.attr-name {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.attr-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.attr-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 36px;
  min-width: 44px;
  padding: 0 var(--space-4);
  border-radius: var(--radius-full);
  border: 1.5px solid var(--color-border-default);
  background: var(--color-bg-elevated);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  white-space: nowrap;
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease-out),
    border-color var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-spring),
    opacity var(--duration-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
  user-select: none;
}

.attr-chip:active:not(:disabled) {
  transform: scale(0.93);
}

.attr-chip--selected {
  background: var(--color-brand-500);
  border-color: var(--color-brand-500);
  color: var(--color-text-inverse);
}

.attr-chip--selected:active {
  background: var(--color-brand-600);
  border-color: var(--color-brand-600);
}

.attr-chip--disabled {
  opacity: 0.35;
  cursor: not-allowed;
  text-decoration: line-through;
}

/* ===== Price + stock ===== */
.price-stock-section {
  margin: 0 var(--space-4);
  padding: var(--space-4);
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.price-row,
.stock-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.price-label,
.stock-label {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  font-weight: var(--font-medium);
}

.price-row :deep(.price) {
  color: var(--color-brand-500);
}

.stock-value {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-success);
}

.stock-value--empty {
  color: var(--color-error);
}

/* ===== Cart section ===== */
.cart-section {
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.qty-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.qty-label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
}

/* ===== Add-to-cart button ===== */
.add-to-cart-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  width: 100%;
  height: 52px;
  padding: 0 var(--space-5);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  border-radius: var(--radius-lg);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  box-shadow: var(--shadow-float);
  transition:
    background var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-spring),
    box-shadow var(--duration-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
}

.add-to-cart-btn:hover {
  background: var(--color-brand-600);
}

.add-to-cart-btn:active {
  transform: scale(0.97);
  box-shadow: none;
}

.add-to-cart-btn--added {
  background: var(--color-success);
  box-shadow: 0 6px 20px rgba(45, 159, 111, 0.3);
}

.add-to-cart-btn--disabled {
  background: var(--color-bg-sunken);
  color: var(--color-text-tertiary);
  box-shadow: none;
  cursor: not-allowed;
}

.add-to-cart-btn--disabled:hover {
  background: var(--color-bg-sunken);
}

.btn-label {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  overflow: hidden;
  white-space: nowrap;
}

.add-to-cart-btn :deep(.btn-price) {
  color: inherit;
  font-size: inherit;
  font-weight: inherit;
}

/* ===== Button icon/text transitions ===== */
.btn-icon-enter-active,
.btn-icon-leave-active {
  transition:
    opacity var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-spring);
}
.btn-icon-enter-from { opacity: 0; transform: scale(0.5) rotate(-30deg); }
.btn-icon-leave-to   { opacity: 0; transform: scale(0.5) rotate(30deg); }

.btn-text-enter-active,
.btn-text-leave-active {
  transition: opacity var(--duration-fast) var(--ease-out);
}
.btn-text-enter-from,
.btn-text-leave-to { opacity: 0; }

/* ===== Responsive ===== */
@media (min-width: 768px) {
  .product-hero {
    max-height: 360px;
    padding-top: 0;
    height: 360px;
  }
}

@media (min-width: 1024px) {
  .detail-body {
    display: grid;
    grid-template-columns: 1fr 400px;
    grid-template-rows: auto auto auto auto;
    gap: 0;
    max-width: var(--max-content-width);
    margin: 0 auto;
    padding: var(--space-6);
    align-items: start;
  }

  .product-hero {
    grid-column: 1;
    grid-row: 1 / 3;
    border-radius: var(--radius-xl);
    overflow: hidden;
    padding-top: 56.25%;
    height: auto;
    max-height: unset;
    margin-right: var(--space-6);
  }

  .product-info-section {
    grid-column: 2;
    grid-row: 1;
    padding: 0 0 var(--space-4);
    border-top: none;
  }

  .variants-section {
    grid-column: 2;
    grid-row: 2;
    border-top: 1px solid var(--color-border-subtle);
    padding: var(--space-4) 0;
  }

  .price-stock-section {
    grid-column: 2;
    grid-row: 3;
    margin: 0;
  }

  .cart-section {
    grid-column: 2;
    grid-row: 4;
    padding: var(--space-4) 0 0;
  }
}

/* ===== Reduced motion ===== */
@media (prefers-reduced-motion: reduce) {
  .add-to-cart-btn,
  .attr-chip,
  .back-btn,
  .btn-icon-enter-active,
  .btn-icon-leave-active,
  .btn-text-enter-active,
  .btn-text-leave-active {
    transition: none;
    animation: none;
  }
}
</style>
