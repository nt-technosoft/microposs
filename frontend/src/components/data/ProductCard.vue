<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ShoppingCart, ChevronRight, Package } from 'lucide-vue-next'
import type { Product } from '@/types/models'
import PriceDisplay from '@/components/data/PriceDisplay.vue'

interface Props {
  product: Product
  inCartQuantity?: number
  locationScoped?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  inCartQuantity: 0,
  locationScoped: true,
})
const { t } = useI18n()

const emit = defineEmits<{
  'add-to-cart': [product: Product]
  'view-detail': [product: Product]
}>()

const productVariants = computed(() => (
  Array.isArray(props.product.variants) ? props.product.variants : []
))

const effectivePrice = computed((): string => {
  if (props.product.base_price) return props.product.base_price
  if (productVariants.value.length > 0) {
    return productVariants.value[0].effective_price
  }
  return '0'
})

const hasImage = computed(() =>
  Boolean(props.product.photo_url && props.product.photo_url.trim().length > 0),
)

const totalStock = computed(() => {
  if (Number.isFinite(props.product.total_stock_all_locations)) {
    return Number(props.product.total_stock_all_locations)
  }
  if (Number.isFinite(props.product.total_stock)) {
    return Number(props.product.total_stock)
  }
  return 0
})

const stockAtLocation = computed(() => {
  if (!props.locationScoped) {
    return totalStock.value
  }
  if (props.product.availability_state === 'warehouse_only') {
    return 0
  }
  if (Number.isFinite(props.product.stock_at_location)) {
    return Number(props.product.stock_at_location)
  }
  if (Number.isFinite(props.product.total_stock)) {
    return Number(props.product.total_stock)
  }
  if (productVariants.value.length > 0) {
    return productVariants.value.reduce((sum, variant) => sum + (variant.stock_quantity ?? 0), 0)
  }
  return 0
})

const stockStatusLabel = computed(() => {
  if (!props.locationScoped) {
    return totalStock.value > 0
      ? t('sales.stockTotal', { count: totalStock.value })
      : t('sales.outOfStock')
  }
  if (stockAtLocation.value > 0) return t('sales.stockInShop', { count: stockAtLocation.value })
  if (totalStock.value > 0) return t('sales.warehouseOnly')
  return t('sales.outOfStock')
})

const isUnavailableForSale = computed(() => stockAtLocation.value <= 0)

function onCardClick() {
  emit('view-detail', props.product)
}

function onActionClick(event: MouseEvent) {
  event.stopPropagation()
  if (props.product.has_variants || isUnavailableForSale.value) {
    emit('view-detail', props.product)
  } else {
    emit('add-to-cart', props.product)
  }
}
</script>

<template>
  <article
    class="product-card"
    :aria-label="product.name"
    role="button"
    tabindex="0"
    @click="onCardClick"
    @keydown.enter="onCardClick"
    @keydown.space.prevent="onCardClick"
  >
    <!-- In-cart indicator chip -->
    <Transition name="cart-badge">
      <div v-if="inCartQuantity > 0" class="cart-badge" :aria-label="t('sales.inCart', { count: inCartQuantity })">
        {{ inCartQuantity }}
      </div>
    </Transition>

    <!-- Product image -->
    <div class="product-image">
      <template v-if="hasImage">
        <img :src="product.photo_url!" :alt="product.name" loading="lazy">
      </template>
      <template v-else>
        <div class="product-image-placeholder">
          <Package :size="32" :stroke-width="1.5" class="placeholder-icon" />
        </div>
      </template>
    </div>

    <!-- Product info -->
    <div class="product-info">
      <h3 class="product-name">{{ product.name }}</h3>

      <div class="product-price">
        <PriceDisplay :amount="effectivePrice" size="md" />
      </div>

      <div class="product-meta">
        <span
          class="meta-pill"
          :class="{
            'meta-pill--warning': totalStock <= 0,
            'meta-pill--storage': stockAtLocation <= 0 && totalStock > 0,
          }"
        >
          {{ stockStatusLabel }}
        </span>
        <span v-if="product.has_variants" class="meta-pill">
          {{ t('sales.variableProduct') }}
        </span>
      </div>
    </div>

    <!-- Action button -->
    <button
      class="product-action"
      :class="{ 'product-action--select': product.has_variants || isUnavailableForSale }"
      :aria-label="product.has_variants || isUnavailableForSale ? t('sales.openProduct', { name: product.name }) : t('sales.addToCart', { name: product.name })"
      @click="onActionClick"
    >
      <template v-if="product.has_variants || isUnavailableForSale">
        <span class="action-label">{{ product.has_variants ? t('sales.choose') : t('common.details') }}</span>
        <ChevronRight :size="16" :stroke-width="2" />
      </template>
      <template v-else>
        <ShoppingCart :size="16" :stroke-width="1.75" />
        <span class="action-plus" aria-hidden="true">+</span>
      </template>
    </button>
  </article>
</template>

<style scoped>
.product-card {
  position: relative;
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  transition:
    box-shadow var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
  user-select: none;
}

.product-card:hover {
  box-shadow: var(--shadow-md);
}

.product-card:active {
  transform: scale(0.97);
  transition-duration: var(--duration-fast);
}

/* Cart badge — top-right amber chip */
.cart-badge {
  position: absolute;
  top: var(--space-2);
  right: var(--space-2);
  z-index: 1;
  min-width: 22px;
  height: 22px;
  padding: 0 var(--space-1);
  background: var(--color-accent-400);
  color: var(--color-text-primary);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-bold);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 6px rgba(251, 173, 27, 0.4);
  pointer-events: none;
}

/* Product image: 4:3 aspect ratio */
.product-image {
  width: 100%;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  background: var(--color-bg-secondary);
  flex-shrink: 0;
}

.product-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.product-image-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-bg-secondary);
}

.placeholder-icon {
  color: var(--color-text-tertiary);
}

/* Info area */
.product-info {
  padding: var(--space-3) var(--space-3) var(--space-2);
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.product-name {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-primary);
  line-height: var(--leading-tight);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.product-price :deep(.price) {
  color: var(--color-brand-500);
}

.product-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  margin-top: var(--space-1);
}

.meta-pill {
  height: 20px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border-subtle);
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  font-size: 10px;
  font-weight: var(--font-medium);
  display: inline-flex;
  align-items: center;
}

.meta-pill--warning {
  border-color: var(--color-warning);
  color: var(--color-warning);
  background: var(--color-warning-bg);
}

.meta-pill--storage {
  border-color: rgba(217, 119, 6, 0.22);
  color: var(--color-warning);
  background: var(--color-warning-bg);
}

/* Action button */
.product-action {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  width: calc(100% - var(--space-3) * 2);
  margin: 0 var(--space-3) var(--space-3);
  height: 40px;
  min-height: 44px;
  padding: 0 var(--space-3);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  transition:
    background var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-spring);
  -webkit-tap-highlight-color: transparent;
  flex-shrink: 0;
}

.product-action:hover {
  background: var(--color-brand-600);
}

.product-action:active {
  transform: scale(0.95);
  background: var(--color-brand-700);
}

.product-action--select {
  background: transparent;
  color: var(--color-brand-500);
  border: 1.5px solid var(--color-brand-500);
}

.product-action--select:hover {
  background: var(--color-brand-50);
}

.product-action--select:active {
  background: var(--color-brand-100);
}

.action-label {
  font-size: var(--text-sm);
}

.action-plus {
  font-size: var(--text-base);
  font-weight: var(--font-bold);
  line-height: 1;
  margin-left: -2px;
}

/* Cart badge transition */
.cart-badge-enter-active {
  animation: pop-in var(--duration-fast) var(--ease-spring);
}
.cart-badge-leave-active {
  animation: pop-in var(--duration-fast) var(--ease-in) reverse;
}

@keyframes pop-in {
  from { transform: scale(0); opacity: 0; }
  to   { transform: scale(1); opacity: 1; }
}
</style>
