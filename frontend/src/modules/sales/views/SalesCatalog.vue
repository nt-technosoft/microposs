<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ShoppingCart, Package, Store, Wallet, ReceiptText, Clock3 } from 'lucide-vue-next'
import { fetchProductVariants } from '@/api/catalog'
import { fetchLocations } from '@/api/inventory'
import { useProductsStore } from '@/stores/products'
import { useCartStore } from '@/stores/cart'
import { useSessionStore } from '@/stores/session'
import type { Product, ProductVariant, Location } from '@/types/models'
import { PricingMode } from '@/types/enums'
import { formatPrice } from '@/utils/currency'
import { getApiErrorMessage } from '@/utils/errors'
import BaseSearch from '@/components/base/BaseSearch.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'
import CategoryChips from '@/components/forms/CategoryChips.vue'
import ProductCard from '@/components/data/ProductCard.vue'
import AppSkeletonCard from '@/components/feedback/AppSkeletonCard.vue'
import AppEmptyState from '@/components/feedback/AppEmptyState.vue'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import { useToast } from '@/composables/useToast'

const router = useRouter()
const route = useRoute()
const productsStore = useProductsStore()
const cartStore = useCartStore()
const sessionStore = useSessionStore()
const toast = useToast()

const searchQuery = ref('')
const locations = ref<Location[]>([])
const isLoadingLocations = ref(false)
const openSheetOpen = ref(false)
const closeSheetOpen = ref(false)
const openForm = ref({
  locationId: null as number | null,
  openingCash: '0',
})
const closeForm = ref({
  actualCash: '',
})
const openFormError = ref('')
const closeFormError = ref('')

// Map of product id → boolean flash for "added" overlay
const flashMap = ref<Record<number, boolean>>({})
let flashTimers: Record<number, ReturnType<typeof setTimeout>> = {}

// Intersection observer for infinite scroll
const sentinelRef = ref<HTMLElement | null>(null)
let scrollObserver: IntersectionObserver | null = null

const SKELETON_COUNT = 6

const cartItemCount = computed(() => cartStore.itemCount)
const activeSession = computed(() => sessionStore.currentSession)
const shopLocations = computed(() =>
  locations.value.filter((location) => location.kind === 'shop' || location.location_type === 'store'),
)
const locationOptions = computed(() =>
  shopLocations.value.map((location) => ({
    value: location.id,
    label: location.name,
  })),
)
const cashSalesTotal = computed(() => Number(activeSession.value?.cash_sales_total ?? 0))
const expectedCashPreview = computed(() =>
  Number(activeSession.value?.opening_cash ?? 0) + cashSalesTotal.value,
)
const openedAtLabel = computed(() => {
  if (!activeSession.value?.opened_at) return ''
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(activeSession.value.opened_at))
})
const closeDifference = computed(() => {
  const actualCash = Number(closeForm.value.actualCash || '0')
  if (!Number.isFinite(actualCash)) return 0
  return actualCash - expectedCashPreview.value
})
const closeDifferenceMeta = computed(() => {
  if (closeDifference.value === 0) {
    return {
      label: 'Без расхождения',
      tone: 'ok' as const,
    }
  }

  return closeDifference.value > 0
    ? { label: 'Излишек', tone: 'positive' as const }
    : { label: 'Недостача', tone: 'warning' as const }
})

function inCartQuantity(product: Product): number {
  const resolveVariantProductId = (variant: ProductVariant): number | null => {
    if (typeof variant.product_id === 'number') return variant.product_id
    if (typeof variant.product === 'number') return variant.product
    return null
  }

  return cartStore.items
    .filter((item) => resolveVariantProductId(item.product_variant) === product.id)
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

async function onAddToCart(product: Product | null | undefined) {
  if (!product || typeof product.id !== 'number') {
    return
  }

  const supportsQuickAdd = !product.has_variants && product.pricing_mode === PricingMode.FIXED
  if (!supportsQuickAdd) {
    router.push({ name: 'product-detail', params: { id: product.id } })
    return
  }

  const localVariants = Array.isArray(product.variants) ? product.variants : []
  let variant: ProductVariant | null = localVariants[0] ?? null
  if (!variant) {
    try {
      const locationId = sessionStore.currentSession?.location?.id
      const loadedVariants = await fetchProductVariants(product.id, {
        location_id: locationId,
      })
      variant = Array.isArray(loadedVariants) ? (loadedVariants[0] ?? null) : null
    } catch {
      variant = null
    }
  }

  if (!variant) {
    router.push({ name: 'product-detail', params: { id: product.id } })
    return
  }

  if ((variant.stock_quantity ?? 0) <= 0) {
    router.push({ name: 'product-detail', params: { id: product.id } })
    return
  }

  const price = product.base_price ?? variant.effective_price ?? variant.price ?? '0'

  cartStore.addItem({
    product_variant: variant,
    product_name: product.name,
    pricing_mode: product.pricing_mode,
    lot_id: null,
    quantity: 1,
    unit_price: price,
    base_price: price,
    price_changed: false,
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

function formatSessionAmount(value: number | string): string {
  return formatPrice(value, 'UZS')
}

function formatInputNumber(value: number): string {
  if (!Number.isFinite(value)) return '0'
  const normalized = value.toFixed(2)
  return normalized.endsWith('.00') ? normalized.slice(0, -3) : normalized
}

async function loadLocations(): Promise<void> {
  isLoadingLocations.value = true
  try {
    locations.value = await fetchLocations()
    if (shopLocations.value.length === 1 && openForm.value.locationId === null) {
      openForm.value.locationId = shopLocations.value[0].id
    }
  } catch (error: unknown) {
    toast.error(getApiErrorMessage(error, 'Не удалось загрузить точки продаж'))
  } finally {
    isLoadingLocations.value = false
  }
}

function clearOpenSessionQuery(): void {
  if (!('openSession' in route.query)) return
  const nextQuery = { ...route.query }
  delete nextQuery.openSession
  router.replace({ query: nextQuery })
}

function openSessionSheet(): void {
  openFormError.value = ''
  if (shopLocations.value.length === 1 && openForm.value.locationId === null) {
    openForm.value.locationId = shopLocations.value[0].id
  }
  openSheetOpen.value = true
}

function closeOpenSessionSheet(): void {
  openSheetOpen.value = false
  clearOpenSessionQuery()
}

function openCloseSessionSheet(): void {
  if (!activeSession.value) return
  closeFormError.value = ''
  closeForm.value.actualCash = formatInputNumber(expectedCashPreview.value)
  closeSheetOpen.value = true
}

function closeCloseSessionSheet(): void {
  closeSheetOpen.value = false
}

async function submitOpenSession(): Promise<void> {
  openFormError.value = ''

  if (!openForm.value.locationId) {
    openFormError.value = 'Выбери точку продаж'
    return
  }

  const openingCash = Number(openForm.value.openingCash || '0')
  if (!Number.isFinite(openingCash) || openingCash < 0) {
    openFormError.value = 'Проверь стартовую наличность'
    return
  }

  try {
    await sessionStore.openSession(openForm.value.locationId, openingCash)
    closeOpenSessionSheet()
    toast.success('Смена открыта')
  } catch (error: unknown) {
    openFormError.value = getApiErrorMessage(error, 'Не удалось открыть смену')
  }
}

async function submitCloseSession(): Promise<void> {
  closeFormError.value = ''

  const actualCash = Number(closeForm.value.actualCash || '0')
  if (!Number.isFinite(actualCash) || actualCash < 0) {
    closeFormError.value = 'Проверь фактическую наличность'
    return
  }

  try {
    await sessionStore.closeSession(actualCash)
    closeCloseSessionSheet()
    toast.success('Смена закрыта')
  } catch (error: unknown) {
    closeFormError.value = getApiErrorMessage(error, 'Не удалось закрыть смену')
  }
}

watch(
  () => route.query.openSession,
  (value) => {
    if (value === '1' && sessionStore.isOpen) {
      clearOpenSessionQuery()
      return
    }

    if (value === '1' && !sessionStore.isOpen) {
      openSessionSheet()
    }
  },
  { immediate: true },
)

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
    loadLocations(),
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
      <section class="session-card" aria-labelledby="session-heading">
        <div class="session-card__header">
          <div class="session-card__title-wrap">
            <p class="session-card__eyebrow">Смена</p>
            <h2 id="session-heading" class="session-card__title">
              {{ activeSession ? 'Смена открыта' : 'Смена не открыта' }}
            </h2>
          </div>
          <span class="session-badge" :class="{ 'session-badge--open': !!activeSession }">
            {{ activeSession ? 'Открыта' : 'Закрыта' }}
          </span>
        </div>

        <template v-if="activeSession">
          <div class="session-meta">
            <span class="session-meta__item">
              <Store :size="16" :stroke-width="1.8" />
              {{ sessionStore.location?.name || 'Точка продаж' }}
            </span>
            <span class="session-meta__item">
              <Clock3 :size="16" :stroke-width="1.8" />
              {{ openedAtLabel }}
            </span>
          </div>

          <div class="session-stats">
            <div class="session-stat">
              <span class="session-stat__label">Старт</span>
              <span class="session-stat__value">{{ formatSessionAmount(activeSession.opening_cash) }}</span>
            </div>
            <div class="session-stat">
              <span class="session-stat__label">Наличные продажи</span>
              <span class="session-stat__value">{{ formatSessionAmount(cashSalesTotal) }}</span>
            </div>
            <div class="session-stat">
              <span class="session-stat__label">Ожидается в кассе</span>
              <span class="session-stat__value">{{ formatSessionAmount(expectedCashPreview) }}</span>
            </div>
            <div class="session-stat">
              <span class="session-stat__label">Продаж</span>
              <span class="session-stat__value">{{ activeSession.sales_count ?? 0 }}</span>
            </div>
          </div>

          <BaseButton
            variant="secondary"
            size="md"
            :full-width="true"
            @click="openCloseSessionSheet"
          >
            Закрыть смену
          </BaseButton>
        </template>

        <template v-else>
          <p class="session-card__description">
            Открой кассовую смену, чтобы оформлять продажи и видеть сверку по кассе.
          </p>
          <p v-if="!isLoadingLocations && shopLocations.length === 0" class="session-card__hint">
            Нет активной точки продаж. Сначала создай или включи магазин в локациях.
          </p>
          <BaseButton
            variant="primary"
            size="md"
            :full-width="true"
            :disabled="isLoadingLocations || shopLocations.length === 0"
            @click="openSessionSheet"
          >
            Открыть смену
          </BaseButton>
        </template>
      </section>

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

    <AppBottomSheet :open="openSheetOpen" title="Открыть смену" @close="closeOpenSessionSheet">
      <form class="session-sheet" @submit.prevent="submitOpenSession">
        <BaseSelect
          v-model="openForm.locationId"
          title="Точка продаж"
          placeholder="Выберите точку продаж"
          :options="locationOptions"
          :disabled="isLoadingLocations || shopLocations.length === 0"
        />
        <BaseInput
          v-model="openForm.openingCash"
          label="Стартовая наличность"
          type="number"
          placeholder="0"
        />
        <p v-if="openFormError" class="session-sheet__error">{{ openFormError }}</p>
        <BaseButton
          variant="primary"
          size="lg"
          :full-width="true"
          :loading="sessionStore.isLoading"
        >
          Открыть смену
        </BaseButton>
      </form>
    </AppBottomSheet>

    <AppBottomSheet :open="closeSheetOpen" title="Закрыть смену" @close="closeCloseSessionSheet">
      <form class="session-sheet" @submit.prevent="submitCloseSession">
        <div class="close-summary">
          <div class="close-summary__row">
            <span class="close-summary__label">
              <Store :size="16" :stroke-width="1.8" />
              Точка
            </span>
            <span class="close-summary__value">{{ sessionStore.location?.name || 'Точка продаж' }}</span>
          </div>
          <div class="close-summary__row">
            <span class="close-summary__label">
              <Wallet :size="16" :stroke-width="1.8" />
              Старт
            </span>
            <span class="close-summary__value">{{ formatSessionAmount(activeSession?.opening_cash ?? 0) }}</span>
          </div>
          <div class="close-summary__row">
            <span class="close-summary__label">
              <ReceiptText :size="16" :stroke-width="1.8" />
              Наличные продажи
            </span>
            <span class="close-summary__value">{{ formatSessionAmount(cashSalesTotal) }}</span>
          </div>
          <div class="close-summary__row">
            <span class="close-summary__label">Ожидается в кассе</span>
            <span class="close-summary__value">{{ formatSessionAmount(expectedCashPreview) }}</span>
          </div>
        </div>

        <BaseInput
          v-model="closeForm.actualCash"
          label="Фактическая наличность"
          type="number"
          placeholder="0"
        />
        <div class="difference-card" :class="`difference-card--${closeDifferenceMeta.tone}`">
          <span class="difference-card__label">{{ closeDifferenceMeta.label }}</span>
          <span class="difference-card__value">{{ formatSessionAmount(closeDifference) }}</span>
        </div>
        <p v-if="closeFormError" class="session-sheet__error">{{ closeFormError }}</p>
        <BaseButton
          variant="primary"
          size="lg"
          :full-width="true"
          :loading="sessionStore.isLoading"
        >
          Закрыть смену
        </BaseButton>
      </form>
    </AppBottomSheet>
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

.session-card {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  margin-bottom: var(--space-4);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
  box-shadow: var(--shadow-sm);
}

.session-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}

.session-card__title-wrap {
  display: grid;
  gap: 2px;
}

.session-card__eyebrow {
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--color-text-tertiary);
  text-transform: uppercase;
}

.session-card__title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  line-height: 1.2;
}

.session-card__description {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: 1.45;
}

.session-card__hint {
  font-size: var(--text-sm);
  color: var(--color-warning);
  line-height: 1.45;
}

.session-badge {
  flex-shrink: 0;
  min-height: 28px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-full);
  background: var(--color-warning-bg);
  color: var(--color-warning);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.session-badge--open {
  background: var(--color-brand-50);
  color: var(--color-brand-600);
}

.session-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2) var(--space-3);
}

.session-meta__item {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.session-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}

.session-stat {
  display: grid;
  gap: 4px;
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
}

.session-stat__label {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.session-stat__value {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  line-height: 1.25;
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

.session-sheet {
  display: grid;
  gap: var(--space-3);
  padding-bottom: var(--space-4);
}

.session-sheet__error {
  font-size: var(--text-sm);
  color: var(--color-error);
}

.close-summary {
  display: grid;
  gap: var(--space-2);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
}

.close-summary__row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.close-summary__label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.close-summary__value {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  text-align: right;
}

.difference-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-subtle);
  background: var(--color-bg-secondary);
}

.difference-card--ok {
  background: var(--color-brand-50);
  border-color: var(--color-brand-200);
}

.difference-card--positive {
  background: #edf8f2;
  border-color: #9fd0b3;
}

.difference-card--warning {
  background: var(--color-warning-bg);
  border-color: var(--color-warning);
}

.difference-card__label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
}

.difference-card__value {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  text-align: right;
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
