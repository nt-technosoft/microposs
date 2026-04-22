<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Package, Plus, ChevronRight, FolderTree, ArrowRightLeft } from 'lucide-vue-next'
import { fetchProducts, fetchCategories } from '@/api/catalog'
import type { Product, Category } from '@/types/models'
import BaseSearch from '@/components/base/BaseSearch.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'
import BaseBadge from '@/components/base/BaseBadge.vue'
import AppEmptyState from '@/components/feedback/AppEmptyState.vue'

const router = useRouter()

// --- State ---
const products = ref<Product[]>([])
const categories = ref<Category[]>([])
const searchQuery = ref('')
const selectedCategory = ref<number | ''>('')
const isLoading = ref(false)
const isLoadingMore = ref(false)
const hasMore = ref(false)
const currentPage = ref(1)
const errorMessage = ref('')

const PAGE_SIZE = 20

// --- Computed ---
const isEmpty = computed(() => !isLoading.value && products.value.length === 0)

const categoryOptions = computed(() => ([
  { value: '' as const, label: 'Все категории' },
  ...categories.value.map((category) => ({
    value: category.id,
    label: category.name,
  })),
]))

function getCategoryName(product: Product): string | null {
  if (product.category && typeof product.category === 'object' && 'name' in product.category) {
    return product.category.name
  }
  const fallback = (product as Product & { category_name?: string | null }).category_name
  return fallback ?? null
}

function getVariantCount(product: Product): number {
  if (Array.isArray(product.variants)) return product.variants.length
  const fallback = (product as Product & { variants_count?: number }).variants_count
  return Number.isFinite(fallback) ? Number(fallback) : 0
}

function getDisplaySku(product: Product): string {
  const explicitSku = (product as Product & { display_sku?: string }).display_sku
  if (explicitSku && explicitSku.trim()) return explicitSku
  if (Array.isArray(product.variants) && product.variants.length > 0) {
    const fromVariant = product.variants[0].display_sku || product.variants[0].sku
    if (fromVariant && fromVariant.trim()) return fromVariant
  }
  return `P-${product.id}`
}

function stockBadgeVariant(stock: number): 'error' | 'warning' | null {
  if (stock === 0) return 'error'
  if (stock < 5) return 'warning'
  return null
}

function stockBadgeLabel(stock: number): string {
  if (stock === 0) return 'Нет в наличии'
  if (stock < 5) return 'Мало'
  return ''
}

function productStock(product: Product): number {
  if (Array.isArray(product.variants) && product.variants.length > 0) {
    return product.variants.reduce((sum, v) => sum + (v.stock_quantity ?? 0), 0)
  }

  const fallback = (product as Product & { total_stock?: number }).total_stock
  return Number.isFinite(fallback) ? Number(fallback) : 0
}

function formatPrice(price: string | null): string {
  if (!price) return '—'
  const num = parseFloat(price)
  if (isNaN(num)) return price
  return num.toLocaleString('ru-RU') + ' сум'
}

// --- Data fetching ---
async function loadCategories(): Promise<void> {
  try {
    const result = await fetchCategories()
    categories.value = [...result]
  } catch (error: unknown) {
    // Non-critical, silently fail
  }
}

async function loadProducts(reset = false): Promise<void> {
  if (reset) {
    currentPage.value = 1
    products.value = []
    hasMore.value = false
  }

  if (reset) {
    isLoading.value = true
  } else {
    isLoadingMore.value = true
  }
  errorMessage.value = ''

  try {
    const response = await fetchProducts({
      search: searchQuery.value || undefined,
      category: selectedCategory.value !== '' ? Number(selectedCategory.value) : undefined,
      page: currentPage.value,
      page_size: PAGE_SIZE,
    })

    const incoming = response.results
    products.value = reset ? [...incoming] : [...products.value, ...incoming]
    hasMore.value = response.next !== null
  } catch (error: unknown) {
    errorMessage.value = 'Не удалось загрузить товары. Попробуйте ещё раз.'
  } finally {
    isLoading.value = false
    isLoadingMore.value = false
  }
}

async function loadMore(): Promise<void> {
  if (!hasMore.value || isLoadingMore.value) return
  currentPage.value = currentPage.value + 1
  await loadProducts(false)
}

function onSearch(query: string): void {
  searchQuery.value = query
  loadProducts(true)
}

function onCategoryChange(): void {
  loadProducts(true)
}

function navigateToProduct(product: Product): void {
  router.push({ name: 'product-edit', params: { id: product.id } })
}

function navigateToCreate(): void {
  router.push({ name: 'product-create' })
}

function navigateToCategories(): void {
  router.push({ name: 'categories' })
}

function navigateToTransfers(): void {
  router.push({ name: 'stock-transfers' })
}

onMounted(async () => {
  await Promise.all([loadCategories(), loadProducts(true)])
})
</script>

<template>
  <div class="product-list-page">
    <!-- Header -->
    <header class="page-header">
      <h1 class="page-title">Товары</h1>
      <div class="header-actions">
        <button
          class="header-icon-btn"
          aria-label="Управление категориями"
          @click="navigateToCategories"
        >
          <FolderTree :size="18" :stroke-width="2" />
        </button>
        <button
          class="header-icon-btn"
          aria-label="Перемещения между точками"
          @click="navigateToTransfers"
        >
          <ArrowRightLeft :size="18" :stroke-width="2" />
        </button>
        <button
          class="header-add-btn"
          aria-label="Добавить товар"
          @click="navigateToCreate"
        >
          <Plus :size="20" :stroke-width="2" />
          <span class="header-add-label">Добавить</span>
        </button>
      </div>
    </header>

    <!-- Filters -->
    <div class="filters-bar">
      <BaseSearch
        v-model="searchQuery"
        placeholder="Поиск товаров..."
        :debounce="300"
        @search="onSearch"
      />
      <BaseSelect
        v-model="selectedCategory"
        class="category-select"
        :options="categoryOptions"
        title="Фильтр по категории"
        placeholder="Все категории"
        @update:model-value="onCategoryChange"
      />
    </div>

    <!-- Error -->
    <div v-if="errorMessage" class="error-banner" role="alert">
      {{ errorMessage }}
    </div>

    <!-- Loading skeletons -->
    <ul v-if="isLoading" class="product-list" aria-busy="true">
      <li v-for="n in 8" :key="n" class="product-row skeleton-row">
        <div class="skeleton-icon" />
        <div class="skeleton-content">
          <div class="skeleton-line skeleton-line--name" />
          <div class="skeleton-line skeleton-line--sub" />
        </div>
        <div class="skeleton-chevron" />
      </li>
    </ul>

    <!-- Empty state -->
    <AppEmptyState
      v-else-if="isEmpty"
      title="Товаров нет"
      description="Добавьте первый товар в каталог"
      action-label="Добавить товар"
      @action="navigateToCreate"
    >
      <template #illustration>
        <div class="empty-icon-wrap">
          <Package :size="40" :stroke-width="1.25" />
        </div>
      </template>
    </AppEmptyState>

    <!-- Product list -->
    <ul v-else class="product-list">
      <li
        v-for="product in products"
        :key="product.id"
        class="product-row"
        :class="{ 'product-row--inactive': !product.is_active }"
        role="button"
        tabindex="0"
        :aria-label="`${product.name}, перейти к редактированию`"
        @click="navigateToProduct(product)"
        @keydown.enter="navigateToProduct(product)"
        @keydown.space.prevent="navigateToProduct(product)"
      >
        <!-- Icon -->
        <div
          class="product-icon"
          :class="product.is_active ? 'product-icon--active' : 'product-icon--inactive'"
          aria-hidden="true"
        >
          <Package :size="20" :stroke-width="1.5" />
        </div>

        <!-- Info -->
        <div class="product-info">
          <div class="product-name">{{ product.name }}</div>
          <div class="product-meta">
            <span v-if="getCategoryName(product)" class="product-category">
              {{ getCategoryName(product) }}
            </span>
            <span v-if="getCategoryName(product) && product.has_variants" class="meta-sep">•</span>
            <span v-if="product.has_variants" class="product-variants">
              {{ getVariantCount(product) }}
              {{ getVariantCount(product) === 1 ? 'вариант' : getVariantCount(product) < 5 ? 'варианта' : 'вариантов' }}
            </span>
            <span v-if="!product.has_variants && !getCategoryName(product)" class="product-no-variants">
              нет вариантов
            </span>
          </div>
          <div class="product-bottom">
            <span class="product-price">{{ formatPrice(product.base_price) }}</span>
            <span class="product-stock">
              {{ productStock(product) }} в наличии
            </span>
            <BaseBadge
              v-if="stockBadgeVariant(productStock(product))"
              :variant="stockBadgeVariant(productStock(product))!"
              size="sm"
            >
              {{ stockBadgeLabel(productStock(product)) }}
            </BaseBadge>
          </div>
          <div class="product-sku">SKU: {{ getDisplaySku(product) }}</div>
        </div>

        <!-- Chevron -->
        <ChevronRight
          class="product-chevron"
          :size="18"
          :stroke-width="1.75"
          aria-hidden="true"
        />
      </li>
    </ul>

    <!-- Load more -->
    <div v-if="hasMore && !isLoading" class="load-more-wrap">
      <button
        class="load-more-btn"
        :disabled="isLoadingMore"
        @click="loadMore"
      >
        <span v-if="isLoadingMore" class="load-more-spinner" aria-hidden="true" />
        <span v-else>Загрузить ещё</span>
      </button>
    </div>

    <!-- FAB -->
    <button
      class="fab"
      aria-label="Добавить товар"
      @click="navigateToCreate"
    >
      <Plus :size="24" :stroke-width="2" />
    </button>
  </div>
</template>

<style scoped>
.product-list-page {
  min-height: 100dvh;
  background: var(--color-bg-primary);
  padding-bottom: calc(var(--bottom-nav-height) + var(--space-8) + 72px);
}

/* Header */
.page-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4) var(--space-5);
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border-subtle);
  min-height: var(--header-height);
}

.page-title {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--color-text-primary);
  line-height: var(--leading-tight);
}

.header-add-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  height: 36px;
  padding: 0 var(--space-3);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  white-space: nowrap;
  transition: background var(--duration-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
}

.header-add-btn:hover {
  background: var(--color-brand-600);
}

.header-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}

.header-icon-btn {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.header-add-btn:active {
  transform: scale(0.96);
}

.header-add-label {
  display: none;
}

@media (min-width: 480px) {
  .header-add-label {
    display: inline;
  }
}

/* Filters */
.filters-bar {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-5) var(--space-3);
}

@media (min-width: 640px) {
  .filters-bar {
    flex-direction: row;
    align-items: center;
  }

  .filters-bar > :first-child {
    flex: 1;
  }
}

.category-select {
  min-width: 160px;
}

.category-select :deep(.select-trigger) {
  height: 44px;
  padding: 0 var(--space-4);
  background: var(--color-bg-secondary);
  border: 1.5px solid transparent;
  border-radius: var(--radius-full);
  font-size: max(16px, var(--text-base));
  line-height: 1.25;
  color: var(--color-text-primary);
  cursor: pointer;
  outline: none;
  transition:
    border-color var(--duration-fast) var(--ease-out),
    box-shadow var(--duration-fast) var(--ease-out);
}

.category-select :deep(.select-trigger):focus-visible {
  border-color: var(--color-border-focus);
  box-shadow: 0 0 0 3px var(--color-brand-100);
}

/* Error */
.error-banner {
  margin: 0 var(--space-5) var(--space-4);
  padding: var(--space-3) var(--space-4);
  background: var(--color-error-bg);
  color: var(--color-error);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

/* Product list */
.product-list {
  list-style: none;
  padding: 0 var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.product-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
  background: var(--color-bg-elevated);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease-out),
    box-shadow var(--duration-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
  box-shadow: var(--shadow-sm);
  min-height: 72px;
}

.product-row:hover {
  background: var(--color-bg-secondary);
  box-shadow: var(--shadow-md);
}

.product-row:active {
  transform: scale(0.99);
}

.product-row:focus-visible {
  outline: 2px solid var(--color-border-focus);
  outline-offset: 2px;
}

.product-row--inactive {
  opacity: 0.5;
}

/* Product icon */
.product-icon {
  width: 44px;
  height: 44px;
  min-width: 44px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.product-icon--active {
  background: var(--color-brand-50);
  color: var(--color-brand-500);
}

.product-icon--inactive {
  background: var(--color-bg-sunken);
  color: var(--color-text-tertiary);
}

/* Product info */
.product-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.product-name {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: var(--leading-tight);
}

.product-meta {
  display: flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.meta-sep {
  color: var(--color-text-tertiary);
}

.product-bottom {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
  margin-top: var(--space-1);
}

.product-sku {
  margin-top: 2px;
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  font-family: var(--font-mono);
}

.product-price {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-brand-600);
}

.product-stock {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

/* Chevron */
.product-chevron {
  color: var(--color-text-tertiary);
  flex-shrink: 0;
  transition: color var(--duration-fast) var(--ease-out);
}

.product-row:hover .product-chevron {
  color: var(--color-text-secondary);
}

/* Skeleton */
.skeleton-row {
  cursor: default;
  pointer-events: none;
}

.skeleton-icon {
  width: 44px;
  height: 44px;
  min-width: 44px;
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  animation: pulse 1.4s ease-in-out infinite;
}

.skeleton-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.skeleton-line {
  height: 12px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-secondary);
  animation: pulse 1.4s ease-in-out infinite;
}

.skeleton-line--name {
  width: 60%;
}

.skeleton-line--sub {
  width: 40%;
  animation-delay: 0.1s;
}

.skeleton-chevron {
  width: 18px;
  height: 18px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-secondary);
  animation: pulse 1.4s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* Empty icon */
.empty-icon-wrap {
  width: 80px;
  height: 80px;
  border-radius: var(--radius-full);
  background: var(--color-brand-50);
  color: var(--color-brand-400);
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Load more */
.load-more-wrap {
  display: flex;
  justify-content: center;
  padding: var(--space-5);
}

.load-more-btn {
  height: 44px;
  padding: 0 var(--space-6);
  border: 1.5px solid var(--color-border-default);
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
  background: var(--color-bg-elevated);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  transition:
    background var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out);
}

.load-more-btn:hover:not(:disabled) {
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
}

.load-more-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.load-more-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--color-border-default);
  border-top-color: var(--color-brand-500);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* FAB */
.fab {
  position: fixed;
  right: var(--space-5);
  bottom: calc(var(--bottom-nav-height) + var(--space-5));
  width: 56px;
  height: 56px;
  border-radius: var(--radius-full);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-float);
  z-index: var(--z-float);
  transition:
    background var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-spring),
    box-shadow var(--duration-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
}

.fab:hover {
  background: var(--color-brand-600);
  box-shadow: var(--shadow-lg);
}

.fab:active {
  transform: scale(0.93);
}

@media (prefers-reduced-motion: reduce) {
  .fab,
  .product-row,
  .skeleton-line,
  .skeleton-icon,
  .skeleton-chevron {
    animation: none;
    transition: none;
  }
}
</style>
