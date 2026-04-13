<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ShoppingCart, Package } from 'lucide-vue-next'
import { useProductsStore } from '@/stores/products'
import { useCartStore } from '@/stores/cart'
import type { Product } from '@/types/models'
import BaseSearch from '@/components/base/BaseSearch.vue'
import CategoryChips from '@/components/forms/CategoryChips.vue'
import ProductCard from '@/components/data/ProductCard.vue'
import AppSkeletonCard from '@/components/feedback/AppSkeletonCard.vue'
import AppEmptyState from '@/components/feedback/AppEmptyState.vue'

const router = useRouter()
const productsStore = useProductsStore()
const cartStore = useCartStore()

const searchQuery = ref('')

// Map of product id → boolean flash for "added" overlay
const flashMap = ref<Record<number, boolean>>({})
let flashTimers: Record<number, ReturnType<typeof setTimeout>> = {}

// Intersection observer for infinite scroll
const sentinelRef = ref<HTMLElement | null>(null)
let scrollObserver: IntersectionObserver | null = null

const SKELETON_COUNT = 6

const cartItemCount = computed(() => cartStore.itemCount)

function inCartQuantity(product: Product): number {
  return cartStore.items
    .filter((item) => item.product_variant.product_id === product.id)
    .reduce((sum, item) => sum + item.quantity, 0)
}

function onSearch(query: string) {
  productsStore.setSearch(query)
}

function onCategorySelect(categoryId: number | null) {
  productsStore.setCategory(categoryId)
}

function triggerFlash(productId: number) {
  if (flashTimers[productId] !== undefined) {
    clearTimeout(flashTimers[productId])
  }
  flashMap.value = { ...flashMap.value, [productId]: true }
  flashTimers[productId] = setTimeout(() => {
    const { [productId]: _removed, ...rest } = flashMap.value
    flashMap.value = rest
    delete flashTimers[productId]
  }, 1400)
}

function onAddToCart(product: Product) {
  if (product.has_variants) {
    router.push({ name: 'product-detail', params: { id: product.id } })
    return
  }

  const variant = product.variants[0] ?? null
  if (!variant) {
    router.push({ name: 'product-detail', params: { id: product.id } })
    return
  }

  const price = product.base_price ?? variant.effective_price

  cartStore.addItem({
    product_variant: variant,
    product_name: product.name,
    lot_id: null,
    quantity: 1,
    unit_price: price,
    base_price: price,
    discount_reason_id: null,
  })

  triggerFlash(product.id)
}

function onViewDetail(product: Product) {
  router.push({ name: 'product-detail', params: { id: product.id } })
}

function goToCart() {
  router.push({ name: 'cart' })
}

function resetFilters() {
  searchQuery.value = ''
  productsStore.setSearch('')
  productsStore.setCategory(null)
}

function setupInfiniteScroll() {
  if (!sentinelRef.value) return

  scrollObserver = new IntersectionObserver(
    (entries) => {
      const [entry] = entries
      if (entry.isIntersecting && productsStore.hasMore && !productsStore.isLoading) {
        productsStore.loadMore()
      }
    },
    { rootMargin: '200px' },
  )

  scrollObserver.observe(sentinelRef.value)
}

onMounted(async () => {
  await Promise.all([
    productsStore.fetchCategories(),
    productsStore.fetchProducts(true),
  ])
  setupInfiniteScroll()
})

onBeforeUnmount(() => {
  scrollObserver?.disconnect()
  Object.values(flashTimers).forEach(clearTimeout)
  flashTimers = {}
})
</script>

<template>
  <div class="catalog-page">

    <!-- ===== Sticky header ===== -->
    <header class="catalog-header">
      <h1 class="header-title">Каталог товаров</h1>

      <button
        class="cart-btn"
        :aria-label="`Корзина, ${cartItemCount} товаров`"
        @click="goToCart"
      >
        <ShoppingCart :size="22" :stroke-width="1.75" />
        <Transition name="badge-pop">
          <span v-if="cartItemCount > 0" class="cart-badge" aria-hidden="true">
            {{ cartItemCount > 99 ? '99+' : cartItemCount }}
          </span>
        </Transition>
      </button>
    </header>

    <!-- ===== Sticky search + category chips ===== -->
    <div class="sticky-filters">
      <div class="search-row">
        <BaseSearch
          v-model="searchQuery"
          placeholder="Поиск товаров..."
          :debounce="300"
          @search="onSearch"
        />
      </div>

      <CategoryChips
        :categories="productsStore.categories"
        :selected="productsStore.selectedCategory"
        @select="onCategorySelect"
      />
    </div>

    <!-- ===== Main content ===== -->
    <main class="catalog-content">

      <!-- Loading skeleton grid (initial load) -->
      <div
        v-if="productsStore.isLoading && productsStore.products.length === 0"
        class="product-grid"
        aria-label="Загрузка товаров"
        aria-busy="true"
      >
        <AppSkeletonCard v-for="n in SKELETON_COUNT" :key="n" />
      </div>

      <!-- Empty state -->
      <AppEmptyState
        v-else-if="!productsStore.isLoading && productsStore.products.length === 0"
        title="Товары не найдены"
        description="Попробуйте изменить поисковый запрос или выбрать другую категорию"
        action-label="Сбросить фильтры"
        @action="resetFilters"
      >
        <template #illustration>
          <div class="empty-icon-wrap">
            <Package :size="40" :stroke-width="1.25" class="empty-icon" />
          </div>
        </template>
      </AppEmptyState>

      <!-- Product grid -->
      <template v-else>
        <div class="product-grid" role="list" aria-label="Список товаров">
          <div
            v-for="product in productsStore.filteredProducts"
            :key="product.id"
            class="product-cell"
            role="listitem"
          >
            <!-- "Added to cart" flash overlay -->
            <Transition name="added-overlay">
              <div
                v-if="flashMap[product.id]"
                class="added-overlay"
                aria-live="polite"
                aria-atomic="true"
              >
                <svg
                  class="added-check-icon"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2.5"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  aria-hidden="true"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                <span class="added-label">Добавлено</span>
              </div>
            </Transition>

            <ProductCard
              :product="product"
              :in-cart-quantity="inCartQuantity(product)"
              @add-to-cart="onAddToCart"
              @view-detail="onViewDetail"
            />
          </div>
        </div>

        <!-- Skeleton rows while loading more (infinite scroll) -->
        <div
          v-if="productsStore.isLoading"
          class="product-grid load-more-grid"
          aria-label="Загрузка ещё товаров"
          aria-busy="true"
        >
          <AppSkeletonCard v-for="n in 2" :key="`lm-${n}`" />
        </div>

        <!-- Invisible sentinel element for IntersectionObserver -->
        <div ref="sentinelRef" class="scroll-sentinel" aria-hidden="true" />
      </template>

    </main>
  </div>
</template>

<style scoped>
/* ===== Page shell ===== */
.catalog-page {
  display: flex;
  flex-direction: column;
  min-height: 100dvh;
  background: var(--color-bg-primary);
  padding-bottom: calc(var(--bottom-nav-height) + var(--space-4));
}

/* ===== Sticky header ===== */
.catalog-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--header-height);
  padding: 0 var(--space-4);
  background: var(--color-bg-elevated);
  border-bottom: 1px solid var(--color-border-subtle);
  box-shadow: var(--shadow-sm);
}

.header-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  line-height: var(--leading-tight);
}

.cart-btn {
  position: relative;
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
  transition:
    background var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-spring);
  -webkit-tap-highlight-color: transparent;
  flex-shrink: 0;
}

.cart-btn:hover {
  background: var(--color-bg-secondary);
}

.cart-btn:active {
  transform: scale(0.88);
  background: var(--color-bg-sunken);
}

.cart-badge {
  position: absolute;
  top: 4px;
  right: 4px;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  background: var(--color-accent-400);
  color: #fff;
  border-radius: var(--radius-full);
  font-size: 10px;
  font-weight: var(--font-bold);
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  box-shadow: 0 1px 4px rgba(251, 173, 27, 0.5);
  pointer-events: none;
}

/* ===== Sticky search + chips bar ===== */
.sticky-filters {
  position: sticky;
  top: var(--header-height);
  z-index: calc(var(--z-sticky) - 1);
  background: var(--color-bg-elevated);
  border-bottom: 1px solid var(--color-border-subtle);
  padding-bottom: var(--space-2);
}

.search-row {
  padding: var(--space-3) var(--space-4) var(--space-2);
}

/* ===== Main content ===== */
.catalog-content {
  flex: 1;
  padding: var(--space-4);
}

/* ===== Product grid — 2 col mobile → 3 tablet → 4 desktop ===== */
.product-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-3);
}

@media (min-width: 768px) {
  .product-grid {
    grid-template-columns: repeat(3, 1fr);
    gap: var(--space-4);
  }
}

@media (min-width: 1024px) {
  .product-grid {
    grid-template-columns: repeat(4, 1fr);
  }
}

.load-more-grid {
  margin-top: var(--space-3);
}

/* ===== Product cell (positions the overlay) ===== */
.product-cell {
  position: relative;
}

/* ===== "Added to cart" flash overlay ===== */
.added-overlay {
  position: absolute;
  inset: 0;
  z-index: 2;
  border-radius: var(--radius-lg);
  background: rgba(27, 138, 111, 0.9);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  pointer-events: none;
}

.added-check-icon {
  width: 32px;
  height: 32px;
  color: #fff;
  stroke-dasharray: 24;
  stroke-dashoffset: 0;
}

.added-label {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: #fff;
  letter-spacing: 0.02em;
}

/* ===== Empty state icon ===== */
.empty-icon-wrap {
  width: 80px;
  height: 80px;
  border-radius: var(--radius-full);
  background: var(--color-brand-50);
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-icon {
  color: var(--color-brand-400);
}

/* ===== Infinite scroll sentinel ===== */
.scroll-sentinel {
  height: 1px;
  margin-top: var(--space-4);
}

/* ===== Transitions ===== */
.badge-pop-enter-active {
  animation: badge-pop var(--duration-fast) var(--ease-spring);
}
.badge-pop-leave-active {
  animation: badge-pop var(--duration-fast) var(--ease-in) reverse;
}

@keyframes badge-pop {
  from { transform: scale(0); opacity: 0; }
  to   { transform: scale(1); opacity: 1; }
}

.added-overlay-enter-active {
  transition:
    opacity var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-spring);
}
.added-overlay-leave-active {
  transition:
    opacity 200ms var(--ease-in),
    transform 200ms var(--ease-in);
}
.added-overlay-enter-from {
  opacity: 0;
  transform: scale(0.9);
}
.added-overlay-leave-to {
  opacity: 0;
  transform: scale(1.06);
}

/* ===== Reduced motion ===== */
@media (prefers-reduced-motion: reduce) {
  .cart-btn,
  .added-overlay,
  .added-overlay-enter-active,
  .added-overlay-leave-active {
    transition: none;
    animation: none;
  }
}
</style>
