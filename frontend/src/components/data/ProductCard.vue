<script setup lang="ts">
import { computed } from 'vue'
import { ShoppingCart, ChevronRight, Package } from 'lucide-vue-next'
import type { Product } from '@/types/models'
import PriceDisplay from '@/components/data/PriceDisplay.vue'

interface Props {
  product: Product
  inCartQuantity?: number
}

const props = withDefaults(defineProps<Props>(), {
  inCartQuantity: 0,
})

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

const hasImage = computed(() => false) // Images not yet in Product model

function onCardClick() {
  emit('view-detail', props.product)
}

function onActionClick(event: MouseEvent) {
  event.stopPropagation()
  if (props.product.has_variants) {
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
      <div v-if="inCartQuantity > 0" class="cart-badge" aria-label="`В корзине: ${inCartQuantity}`">
        {{ inCartQuantity }}
      </div>
    </Transition>

    <!-- Product image -->
    <div class="product-image">
      <template v-if="hasImage">
        <!-- future: <img :src="product.image_url" :alt="product.name" loading="lazy" /> -->
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
    </div>

    <!-- Action button -->
    <button
      class="product-action"
      :class="{ 'product-action--select': product.has_variants }"
      :aria-label="product.has_variants ? `Выбрать вариант ${product.name}` : `Добавить ${product.name} в корзину`"
      @click="onActionClick"
    >
      <template v-if="product.has_variants">
        <span class="action-label">Выбрать</span>
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
