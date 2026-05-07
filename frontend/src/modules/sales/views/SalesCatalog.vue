<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ShoppingCart, Package, Store, Wallet, ReceiptText, Clock3, LayoutGrid, Rows3, ChevronRight, Search, ChevronDown } from 'lucide-vue-next'
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
const { t, locale } = useI18n()
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
  actualCashUsd: '',
})
const openFormError = ref('')
const closeFormError = ref('')
const searchExpanded = ref(false)
const sessionDetailsExpanded = ref(false)
const catalogViewMode = ref<'grid' | 'list'>(
  typeof window !== 'undefined' && window.localStorage.getItem('sales-catalog-view') === 'list'
    ? 'list'
    : 'grid',
)

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
const cashSalesByCurrency = computed<Record<string, number>>(() => {
  const source = activeSession.value?.cash_sales_by_currency ?? {}
  const result: Record<string, number> = {}
  for (const [currency, amount] of Object.entries(source)) {
    const parsed = Number(amount)
    if (Number.isFinite(parsed)) result[currency.toUpperCase()] = parsed
  }
  if (!Object.keys(result).length && cashSalesTotal.value) result.UZS = cashSalesTotal.value
  return result
})
const expectedCashPreview = computed(() =>
  Number(activeSession.value?.opening_cash ?? 0) + (cashSalesByCurrency.value.UZS || 0),
)
const expectedCashByCurrency = computed<Record<string, number>>(() => {
  const opening = activeSession.value?.opening_cash_by_currency ?? { UZS: activeSession.value?.opening_cash ?? '0' }
  const result: Record<string, number> = {}
  for (const [currency, amount] of Object.entries(opening)) {
    const parsed = Number(amount)
    result[currency.toUpperCase()] = Number.isFinite(parsed) ? parsed : 0
  }
  for (const [currency, amount] of Object.entries(cashSalesByCurrency.value)) {
    result[currency] = (result[currency] || 0) + amount
  }
  return result
})
const openedAtLabel = computed(() => {
  if (!activeSession.value?.opened_at) return ''
  return new Intl.DateTimeFormat(locale.value === 'en' ? 'en-US' : locale.value === 'uz' ? 'uz-Latn-UZ' : 'ru-RU', {
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
const closeUsdDifference = computed(() => {
  const actualCash = Number(closeForm.value.actualCashUsd || '0')
  if (!Number.isFinite(actualCash)) return 0
  return actualCash - (expectedCashByCurrency.value.USD || 0)
})
const closeDifferenceMeta = computed(() => {
  if (closeDifference.value === 0) {
    return {
      label: t('sales.noMismatch'),
      tone: 'ok' as const,
    }
  }

  return closeDifference.value > 0
    ? { label: t('sales.surplus'), tone: 'positive' as const }
    : { label: t('sales.shortage'), tone: 'warning' as const }
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

function toggleSearch(): void {
  if (searchExpanded.value && !searchQuery.value.trim()) {
    searchExpanded.value = false
    return
  }
  searchExpanded.value = !searchExpanded.value
}

function setCatalogViewMode(mode: 'grid' | 'list') {
  catalogViewMode.value = mode
}

function toggleCatalogViewMode() {
  setCatalogViewMode(catalogViewMode.value === 'grid' ? 'list' : 'grid')
}

function getCategoryName(product: Product): string | null {
  if (product.category && typeof product.category === 'object' && 'name' in product.category) {
    return product.category.name
  }
  return product.category_name ?? null
}

function getDisplaySku(product: Product): string {
  if (product.display_sku && product.display_sku.trim()) return product.display_sku
  if (Array.isArray(product.variants) && product.variants.length > 0) {
    const sku = product.variants[0].display_sku || product.variants[0].sku
    if (sku && sku.trim()) return sku
  }
  return `P-${product.id}`
}

function productStock(product: Product): number {
  if (!activeSession.value) return productTotalStock(product)
  if (Number.isFinite(product.stock_at_location)) return Number(product.stock_at_location)
  if (Number.isFinite(product.total_stock)) return Number(product.total_stock)
  if (Array.isArray(product.variants) && product.variants.length > 0) {
    return product.variants.reduce((sum, variant) => sum + (variant.stock_quantity ?? 0), 0)
  }
  return 0
}

function productTotalStock(product: Product): number {
  if (Number.isFinite(product.total_stock_all_locations)) return Number(product.total_stock_all_locations)
  if (Number.isFinite(product.total_stock)) return Number(product.total_stock)
  return 0
}

function productShopStock(product: Product): number {
  if (activeSession.value && Number.isFinite(product.stock_at_location)) {
    return Number(product.stock_at_location)
  }
  if (Array.isArray(product.stock_by_location)) {
    return product.stock_by_location
      .filter((entry) => String(entry.warehouse_kind).toUpperCase() === 'SHOP')
      .reduce((sum, entry) => sum + Number(entry.quantity || 0), 0)
  }
  return activeSession.value ? productStock(product) : 0
}

function productAvailabilityRank(product: Product): number {
  if (productShopStock(product) > 0) return 0
  if (productTotalStock(product) > 0) return 1
  return 2
}

const sortedCatalogProducts = computed(() =>
  productsStore.filteredProducts
    .map((product, index) => ({ product, index }))
    .sort((left, right) => {
      const rankDelta = productAvailabilityRank(left.product) - productAvailabilityRank(right.product)
      return rankDelta !== 0 ? rankDelta : left.index - right.index
    })
    .map((entry) => entry.product),
)

function productPrice(product: Product): string {
  if (product.base_price) return product.base_price
  if (Array.isArray(product.variants) && product.variants.length > 0) {
    return product.variants[0].effective_price
  }
  return '0'
}

function productTrace(product: Product): string {
  const parts: string[] = []
  const categoryName = getCategoryName(product)
  if (categoryName) parts.push(categoryName)
  parts.push(`SKU ${getDisplaySku(product)}`)
  return parts.join(' · ')
}

function stockLabel(product: Product): string {
  const stock = productStock(product)
  if (!activeSession.value) {
    return stock > 0 ? t('sales.stockTotal', { count: stock }) : t('sales.outOfStock')
  }
  if (stock > 0) return t('sales.stockInShop', { count: stock })
  return productTotalStock(product) > 0 ? t('sales.warehouseOnly') : t('sales.outOfStock')
}

const viewModeButtonLabel = computed(() =>
  catalogViewMode.value === 'grid' ? t('sales.switchToList') : t('sales.switchToGrid'),
)

const viewModeButtonIcon = computed(() =>
  catalogViewMode.value === 'grid' ? Rows3 : LayoutGrid,
)

const searchVisible = computed(() => searchExpanded.value || searchQuery.value.trim().length > 0)

const sessionCompactNote = computed(() => {
  if (activeSession.value) {
    const parts = [
      sessionStore.location?.name || t('sales.salesPoint'),
      openedAtLabel.value,
    ].filter(Boolean)
    return parts.join(' · ')
  }
  return t('sales.openShiftHint')
})

const sessionToggleLabel = computed(() =>
  sessionDetailsExpanded.value ? t('sales.hideShiftDetails') : t('sales.showShiftDetails'),
)

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

  if (!activeSession.value?.location?.id) {
    toast.warning(t('sales.openShopShiftToAdd'))
    openSessionSheet()
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
      const locationId = activeSession.value.location.id
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

  const availableStock = Number(variant.stock_at_location ?? variant.stock_quantity ?? 0)
  if (availableStock <= 0) {
    router.push({ name: 'product-detail', params: { id: product.id } })
    return
  }

  if (inCartQuantity(product) >= availableStock) {
    toast.warning(t('sales.noShopStockLeft'))
    return
  }

  const price = product.base_price ?? variant.effective_price ?? variant.price ?? '0'

  cartStore.addItem({
    product_variant: variant,
    product_name: product.name,
    pricing_mode: product.pricing_mode,
    lot_id: null,
    location_id: activeSession.value.location.id,
    available_stock: availableStock,
    quantity: 1,
    operation_currency: 'UZS',
    operation_unit_price: price,
    fx_rate: '1',
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

function formatSessionCurrencyAmount(value: number | string, currency: string): string {
  return formatPrice(value, currency)
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
    toast.error(getApiErrorMessage(error, t('sales.locationsLoadFailed')))
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
  closeForm.value.actualCashUsd = formatInputNumber(expectedCashByCurrency.value.USD || 0)
  closeSheetOpen.value = true
}

function closeCloseSessionSheet(): void {
  closeSheetOpen.value = false
}

async function submitOpenSession(): Promise<void> {
  openFormError.value = ''

  if (!openForm.value.locationId) {
    openFormError.value = t('sales.chooseSalesPoint')
    return
  }

  const openingCash = Number(openForm.value.openingCash || '0')
  if (!Number.isFinite(openingCash) || openingCash < 0) {
    openFormError.value = t('sales.checkOpeningCash')
    return
  }

  try {
    await sessionStore.openSession(openForm.value.locationId, openingCash)
    closeOpenSessionSheet()
    await productsStore.fetchProducts(true)
    toast.success(t('sales.shiftOpened'))
  } catch (error: unknown) {
    openFormError.value = getApiErrorMessage(error, t('sales.shiftOpenFailed'))
  }
}

async function submitCloseSession(): Promise<void> {
  closeFormError.value = ''

  const actualCash = Number(closeForm.value.actualCash || '0')
  if (!Number.isFinite(actualCash) || actualCash < 0) {
    closeFormError.value = t('sales.checkActualCash')
    return
  }

  try {
    const actualByCurrency: Record<string, number> = { UZS: actualCash }
    const actualUsd = Number(closeForm.value.actualCashUsd || '0')
    if (Number.isFinite(actualUsd) && (actualUsd > 0 || (expectedCashByCurrency.value.USD || 0) > 0)) {
      actualByCurrency.USD = actualUsd
    }
    await sessionStore.closeSession(actualCash, actualByCurrency)
    closeCloseSessionSheet()
    await productsStore.fetchProducts(true)
    toast.success(t('sales.shiftClosed'))
  } catch (error: unknown) {
    closeFormError.value = getApiErrorMessage(error, t('sales.shiftCloseFailed'))
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

watch(catalogViewMode, (value) => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem('sales-catalog-view', value)
})

watch(
  () => sessionStore.currentSession?.location?.id ?? null,
  async (locationId) => {
    cartStore.setLocation(locationId)
    await productsStore.fetchProducts(true)
  },
)

watch(searchQuery, (value) => {
  if (value.trim()) {
    searchExpanded.value = true
  }
})

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
      <h1 class="header-title">{{ t('sales.catalogTitle') }}</h1>

      <button
        class="cart-btn"
        :aria-label="t('sales.cartAria', { count: cartItemCount })"
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
      <div class="toolbar-row">
        <div class="toolbar-chips">
          <CategoryChips
            :categories="productsStore.categories"
            :selected="productsStore.selectedCategory"
            @select="onCategorySelect"
          />
        </div>

        <div class="toolbar-actions">
          <button
            class="toolbar-icon-btn"
            :class="{ 'toolbar-icon-btn--active': searchVisible }"
            type="button"
            :aria-label="t('sales.searchPlaceholder')"
            @click="toggleSearch"
          >
            <Search :size="16" :stroke-width="2" />
          </button>
          <button
            class="toolbar-icon-btn"
            :class="{ 'toolbar-icon-btn--active': catalogViewMode === 'list' }"
            type="button"
            :aria-label="viewModeButtonLabel"
            @click="toggleCatalogViewMode"
          >
            <component :is="viewModeButtonIcon" :size="16" :stroke-width="2" />
          </button>
        </div>
      </div>

      <Transition name="toolbar-reveal">
        <div v-if="searchVisible" class="search-panel">
          <BaseSearch
            v-model="searchQuery"
            :placeholder="t('sales.searchPlaceholder')"
            :debounce="300"
            @search="onSearch"
          />
        </div>
      </Transition>
    </div>

    <!-- ===== Main content ===== -->
    <main class="catalog-content">
      <section class="session-card" aria-labelledby="session-heading">
        <div class="session-card__header">
          <div class="session-card__title-wrap">
            <h2 id="session-heading" class="session-card__title">
              {{ activeSession ? t('sales.sessionOpen') : t('sales.sessionClosed') }}
            </h2>
            <p class="session-card__compact-note">{{ sessionCompactNote }}</p>
          </div>
          <div class="session-card__header-actions">
            <span class="session-badge" :class="{ 'session-badge--open': !!activeSession }">
              {{ activeSession ? t('sales.openBadge') : t('sales.closedBadge') }}
            </span>
            <button
              class="session-toggle-btn"
              type="button"
              :aria-expanded="sessionDetailsExpanded"
              :aria-label="sessionToggleLabel"
              @click="sessionDetailsExpanded = !sessionDetailsExpanded"
            >
              <ChevronDown :size="16" :stroke-width="2" :class="{ 'session-toggle-btn__icon--open': sessionDetailsExpanded }" />
            </button>
          </div>
        </div>

        <template v-if="activeSession">
          <div class="session-action-row">
            <BaseButton
              variant="secondary"
              size="md"
              :full-width="true"
              @click="openCloseSessionSheet"
            >
              {{ t('sales.closeShift') }}
            </BaseButton>
          </div>

          <Transition name="session-collapse">
            <div v-if="sessionDetailsExpanded" class="session-details">
              <div class="session-meta">
                <span class="session-meta__item">
                  <Store :size="16" :stroke-width="1.8" />
                  {{ sessionStore.location?.name || t('sales.salesPoint') }}
                </span>
                <span class="session-meta__item">
                  <Clock3 :size="16" :stroke-width="1.8" />
                  {{ openedAtLabel }}
                </span>
              </div>

              <div class="session-stats">
                <div class="session-stat">
                  <span class="session-stat__label">{{ t('sales.startCash') }}</span>
                  <span class="session-stat__value">{{ formatSessionAmount(activeSession.opening_cash) }}</span>
                </div>
                <div class="session-stat">
                  <span class="session-stat__label">{{ t('sales.cashSales') }}</span>
                  <span class="session-stat__value">{{ formatSessionAmount(cashSalesTotal) }}</span>
                </div>
                <div class="session-stat">
                  <span class="session-stat__label">{{ t('sales.expectedCash') }}</span>
                  <span class="session-stat__value">{{ formatSessionAmount(expectedCashPreview) }}</span>
                </div>
                <div class="session-stat">
                  <span class="session-stat__label">{{ t('sales.salesCount') }}</span>
                  <span class="session-stat__value">{{ activeSession.sales_count ?? 0 }}</span>
                </div>
              </div>
            </div>
          </Transition>
        </template>

        <template v-else>
          <div class="session-action-row">
            <BaseButton
              variant="primary"
              size="md"
              :full-width="true"
              :disabled="isLoadingLocations || shopLocations.length === 0"
              @click="openSessionSheet"
            >
              {{ t('sales.openShift') }}
            </BaseButton>
          </div>

          <Transition name="session-collapse">
            <div v-if="sessionDetailsExpanded" class="session-details">
              <p class="session-card__description">
                {{ t('sales.shiftDescription') }}
              </p>
              <p v-if="!isLoadingLocations && shopLocations.length === 0" class="session-card__hint">
                {{ t('sales.noSalesPoint') }}
              </p>
            </div>
          </Transition>
        </template>
      </section>

      <!-- Loading skeleton grid (initial load) -->
      <div
        v-if="productsStore.isLoading && productsStore.products.length === 0"
        class="product-grid"
        :aria-label="t('sales.loadingProducts')"
        aria-busy="true"
      >
        <AppSkeletonCard v-for="n in SKELETON_COUNT" :key="n" />
      </div>

      <!-- Empty state -->
      <AppEmptyState
        v-else-if="!productsStore.isLoading && productsStore.products.length === 0"
        :title="t('sales.noProducts')"
        :description="t('sales.noProductsDescription')"
        :action-label="t('sales.resetFilters')"
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
        <div
          v-if="catalogViewMode === 'grid'"
          class="product-grid"
          role="list"
          :aria-label="t('sales.productList')"
        >
          <div
            v-for="product in sortedCatalogProducts"
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
                <span class="added-label">{{ t('sales.added') }}</span>
              </div>
            </Transition>

            <ProductCard
              :product="product"
              :in-cart-quantity="inCartQuantity(product)"
              :location-scoped="!!activeSession"
              @add-to-cart="onAddToCart"
              @view-detail="onViewDetail"
            />
          </div>
        </div>

        <div
          v-else
          class="product-compact-list"
          role="list"
          :aria-label="t('sales.compactProductList')"
        >
          <article
            v-for="product in sortedCatalogProducts"
            :key="product.id"
            class="compact-product-row"
            role="button"
            tabindex="0"
            @click="onViewDetail(product)"
            @keydown.enter="onViewDetail(product)"
            @keydown.space.prevent="onViewDetail(product)"
          >
            <div class="compact-product-media">
              <img
                v-if="product.photo_url"
                :src="product.photo_url"
                :alt="product.name"
                loading="lazy"
              >
              <div v-else class="compact-product-placeholder">
                <Package :size="20" :stroke-width="1.5" />
              </div>
            </div>

            <div class="compact-product-main">
              <div class="compact-product-topline">
                <strong class="compact-product-name">{{ product.name }}</strong>
                <span
                  class="compact-stock-badge"
                  :class="{ 'compact-stock-badge--empty': productStock(product) <= 0 }"
                >
                  {{ stockLabel(product) }}
                </span>
              </div>
              <span class="compact-product-trace">{{ productTrace(product) }}</span>
              <div class="compact-product-bottomline">
                <strong class="compact-product-price">{{ formatPrice(productPrice(product), 'UZS') }}</strong>
                <span v-if="inCartQuantity(product) > 0" class="compact-cart-badge">
                  {{ t('sales.inCartShort', { count: inCartQuantity(product) }) }}
                </span>
              </div>
            </div>

            <button
              class="compact-product-action"
              :class="{ 'compact-product-action--select': product.has_variants || productStock(product) <= 0 }"
              :aria-label="product.has_variants || productStock(product) <= 0 ? t('sales.openProduct', { name: product.name }) : t('sales.addToCart', { name: product.name })"
              @click.stop="product.has_variants || productStock(product) <= 0 ? onViewDetail(product) : onAddToCart(product)"
            >
              <template v-if="product.has_variants || productStock(product) <= 0">
                <ChevronRight :size="16" :stroke-width="2" />
              </template>
              <template v-else>
                <ShoppingCart :size="16" :stroke-width="1.8" />
                <span>+</span>
              </template>
            </button>
          </article>
        </div>

        <!-- Skeleton rows while loading more (infinite scroll) -->
        <div
          v-if="productsStore.isLoading"
          :class="catalogViewMode === 'grid' ? 'product-grid load-more-grid' : 'product-compact-list load-more-grid'"
          :aria-label="t('sales.loadingMoreProducts')"
          aria-busy="true"
        >
          <AppSkeletonCard v-for="n in 2" :key="`lm-${n}`" />
        </div>

        <!-- Invisible sentinel element for IntersectionObserver -->
        <div ref="sentinelRef" class="scroll-sentinel" aria-hidden="true" />
      </template>

    </main>

    <AppBottomSheet :open="openSheetOpen" :title="t('sales.openShift')" @close="closeOpenSessionSheet">
      <form class="session-sheet" @submit.prevent="submitOpenSession">
        <BaseSelect
          v-model="openForm.locationId"
          :title="t('sales.salesPoint')"
          :placeholder="t('sales.selectSalesPoint')"
          :options="locationOptions"
          :disabled="isLoadingLocations || shopLocations.length === 0"
        />
        <BaseInput
          v-model="openForm.openingCash"
          :label="t('sales.openingCash')"
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
          {{ t('sales.openShift') }}
        </BaseButton>
      </form>
    </AppBottomSheet>

    <AppBottomSheet :open="closeSheetOpen" :title="t('sales.closeShift')" @close="closeCloseSessionSheet">
      <form class="session-sheet" @submit.prevent="submitCloseSession">
        <div class="close-summary">
          <div class="close-summary__row">
            <span class="close-summary__label">
              <Store :size="16" :stroke-width="1.8" />
              {{ t('sales.point') }}
            </span>
            <span class="close-summary__value">{{ sessionStore.location?.name || t('sales.salesPoint') }}</span>
          </div>
          <div class="close-summary__row">
            <span class="close-summary__label">
              <Wallet :size="16" :stroke-width="1.8" />
              {{ t('sales.startCash') }}
            </span>
            <span class="close-summary__value">{{ formatSessionAmount(activeSession?.opening_cash ?? 0) }}</span>
          </div>
          <div class="close-summary__row">
            <span class="close-summary__label">
              <ReceiptText :size="16" :stroke-width="1.8" />
              {{ t('sales.cashSales') }}
            </span>
            <span class="close-summary__value">
              {{ formatSessionCurrencyAmount(cashSalesByCurrency.UZS || 0, 'UZS') }}
              <template v-if="cashSalesByCurrency.USD"> · {{ formatSessionCurrencyAmount(cashSalesByCurrency.USD, 'USD') }}</template>
            </span>
          </div>
          <div class="close-summary__row">
            <span class="close-summary__label">{{ t('sales.expectedCash') }}</span>
            <span class="close-summary__value">
              {{ formatSessionCurrencyAmount(expectedCashByCurrency.UZS || 0, 'UZS') }}
              <template v-if="expectedCashByCurrency.USD"> · {{ formatSessionCurrencyAmount(expectedCashByCurrency.USD, 'USD') }}</template>
            </span>
          </div>
        </div>

        <BaseInput
          v-model="closeForm.actualCash"
          :label="t('sales.actualCash')"
          type="number"
          placeholder="0"
        />
        <BaseInput
          v-if="expectedCashByCurrency.USD || closeForm.actualCashUsd"
          v-model="closeForm.actualCashUsd"
          :label="t('sales.actualCashUsd')"
          type="number"
          placeholder="0"
        />
        <div class="difference-card" :class="`difference-card--${closeDifferenceMeta.tone}`">
          <span class="difference-card__label">{{ closeDifferenceMeta.label }}</span>
          <span class="difference-card__value">
            {{ formatSessionAmount(closeDifference) }}
            <template v-if="expectedCashByCurrency.USD || closeForm.actualCashUsd"> · {{ formatSessionCurrencyAmount(closeUsdDifference, 'USD') }}</template>
          </span>
        </div>
        <p v-if="closeFormError" class="session-sheet__error">{{ closeFormError }}</p>
        <BaseButton
          variant="primary"
          size="lg"
          :full-width="true"
          :loading="sessionStore.isLoading"
        >
          {{ t('sales.closeShift') }}
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
  display: grid;
  gap: var(--space-2);
  background: var(--color-bg-elevated);
  border-bottom: 1px solid var(--color-border-subtle);
  padding: var(--space-2) var(--space-4) var(--space-3);
}

.toolbar-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  min-width: 0;
}

.toolbar-chips {
  min-width: 0;
  flex: 1;
  overflow: hidden;
}

.toolbar-chips :deep(.chips-scroll-area) {
  width: 100%;
}

.toolbar-chips :deep(.chips-track) {
  min-width: max-content;
  width: max-content;
  gap: var(--space-2);
  padding: 0;
}

.toolbar-chips :deep(.chip) {
  height: 34px;
  padding: 0 var(--space-3);
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.toolbar-icon-btn {
  width: 36px;
  height: 36px;
  display: inline-grid;
  place-items: center;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-full);
  background: var(--color-bg-primary);
  color: var(--color-text-secondary);
  flex-shrink: 0;
  transition: background var(--duration-fast) var(--ease-out),
    border-color var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-out);
}

.toolbar-icon-btn:hover {
  border-color: var(--color-border-default);
  color: var(--color-text-primary);
}

.toolbar-icon-btn:active {
  transform: scale(0.96);
}

.toolbar-icon-btn--active {
  border-color: var(--color-brand-200);
  background: var(--color-brand-50);
  color: var(--color-brand-700);
}

.search-panel {
  overflow: hidden;
}

.toolbar-reveal-enter-active,
.toolbar-reveal-leave-active {
  transition: max-height var(--duration-fast) var(--ease-out),
    opacity var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-out);
}

.toolbar-reveal-enter-from,
.toolbar-reveal-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* ===== Main content ===== */
.catalog-content {
  flex: 1;
  padding: var(--space-3) var(--space-4) var(--space-4);
}

.session-card {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-3);
  margin-bottom: var(--space-4);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
  box-shadow: var(--shadow-sm);
}

.session-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.session-card__title-wrap {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.session-card__title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  line-height: 1.25;
}

.session-card__compact-note {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: 1.35;
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

.session-card__header-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.session-toggle-btn {
  width: 30px;
  height: 30px;
  display: inline-grid;
  place-items: center;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-full);
  background: var(--color-bg-primary);
  color: var(--color-text-secondary);
  transition: border-color var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-out);
}

.session-toggle-btn:hover {
  border-color: var(--color-border-default);
  color: var(--color-text-primary);
}

.session-toggle-btn:active {
  transform: scale(0.96);
}

.session-toggle-btn__icon--open {
  transform: rotate(180deg);
}

.session-action-row {
  display: grid;
  gap: var(--space-2);
}

.session-details {
  display: grid;
  gap: var(--space-3);
  padding-top: var(--space-1);
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
  gap: var(--space-2);
}

.session-stat {
  display: grid;
  gap: 4px;
  padding: var(--space-2) var(--space-3);
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

.session-collapse-enter-active,
.session-collapse-leave-active {
  transition: opacity var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-out),
    max-height var(--duration-fast) var(--ease-out);
}

.session-collapse-enter-from,
.session-collapse-leave-to {
  opacity: 0;
  transform: translateY(-6px);
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

.product-compact-list {
  display: grid;
  gap: var(--space-2);
}

.compact-product-row {
  display: grid;
  grid-template-columns: 52px minmax(0, 1fr) auto;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
  box-shadow: var(--shadow-sm);
}

.compact-product-media {
  width: 52px;
  height: 52px;
  overflow: hidden;
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  flex-shrink: 0;
}

.compact-product-media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.compact-product-placeholder {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  color: var(--color-text-tertiary);
}

.compact-product-main {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.compact-product-topline,
.compact-product-bottomline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.compact-product-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.compact-product-trace {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}

.compact-product-price {
  color: var(--color-brand-600);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.compact-stock-badge,
.compact-cart-badge {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-full);
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  font-size: 10px;
  font-weight: var(--font-semibold);
  white-space: nowrap;
}

.compact-stock-badge--empty {
  background: var(--color-warning-bg);
  color: var(--color-warning);
}

.compact-cart-badge {
  color: var(--color-brand-700);
  background: var(--color-brand-50);
}

.compact-product-action {
  min-width: 42px;
  min-height: 42px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-md);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.compact-product-action--select {
  background: var(--color-bg-primary);
  color: var(--color-brand-700);
  border: 1px solid var(--color-border-subtle);
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
