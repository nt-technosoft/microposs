<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, AlertCircle } from 'lucide-vue-next'
import { fetchProduct } from '@/api/catalog'
import api from '@/api/client'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { useToast } from '@/composables/useToast'

const route = useRoute()
const router = useRouter()
const toast = useToast()

const isLoading = ref(true)
const isSaving = ref(false)
const errorMessage = ref('')

const name = ref('')
const basePrice = ref('')
const isActive = ref(true)

async function loadProduct(): Promise<void> {
  const id = Number(route.params.id)
  if (!Number.isFinite(id)) {
    errorMessage.value = 'Некорректный ID товара'
    isLoading.value = false
    return
  }

  isLoading.value = true
  errorMessage.value = ''

  try {
    const product = await fetchProduct(id)
    name.value = product.name || ''
    basePrice.value = product.base_price || ''
    isActive.value = Boolean(product.is_active)
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить товар'
  } finally {
    isLoading.value = false
  }
}

async function saveProduct(): Promise<void> {
  if (!name.value.trim()) {
    errorMessage.value = 'Введите название товара'
    return
  }

  const id = Number(route.params.id)
  if (!Number.isFinite(id)) return

  isSaving.value = true
  errorMessage.value = ''

  try {
    await api.patch(`/api/v1/catalog/products/${id}/`, {
      name: name.value.trim(),
      base_price: basePrice.value ? Number(basePrice.value) : null,
      is_active: isActive.value,
    })
    toast.success('Товар сохранён')
    router.push({ name: 'products' })
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось сохранить товар'
  } finally {
    isSaving.value = false
  }
}

onMounted(loadProduct)
</script>

<template>
  <div class="edit-page">
    <header class="page-header">
      <button class="back-btn" type="button" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>
      <h1 class="page-title">Редактирование товара</h1>
      <div class="header-spacer" />
    </header>

    <div v-if="isLoading" class="loading-wrap" aria-busy="true">
      <div class="skeleton skeleton-line" />
      <div class="skeleton skeleton-line" />
      <div class="skeleton skeleton-line-lg" />
    </div>

    <form v-else class="form" @submit.prevent="saveProduct">
      <div v-if="errorMessage" class="error-banner" role="alert">
        <AlertCircle :size="16" :stroke-width="1.75" />
        <span>{{ errorMessage }}</span>
      </div>

      <BaseInput v-model="name" label="Название товара *" placeholder="Введите название" />

      <BaseInput
        v-model="basePrice"
        label="Базовая цена"
        type="number"
        placeholder="0"
      />

      <label class="toggle-row">
        <span class="toggle-label">Товар активен</span>
        <input v-model="isActive" class="toggle-input" type="checkbox" />
      </label>

      <BaseButton
        type="submit"
        variant="primary"
        size="lg"
        :full-width="true"
        :loading="isSaving"
        :disabled="isSaving"
      >
        Сохранить
      </BaseButton>
    </form>
  </div>
</template>

<style scoped>
.edit-page {
  min-height: 100%;
  background: var(--color-bg-primary);
}

.page-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  height: var(--header-height);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-bg-primary);
}

.page-title {
  flex: 1;
  color: var(--color-text-primary);
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
}

.back-btn,
.header-spacer {
  width: 40px;
  height: 40px;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
}

.form {
  display: grid;
  gap: var(--space-4);
  padding: var(--space-4);
  padding-bottom: calc(var(--bottom-nav-height) + var(--space-8));
}

.error-banner {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  border: 1px solid var(--color-error);
  color: var(--color-error);
  border-radius: var(--radius-md);
  background: var(--color-error-bg);
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
}

.toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  min-height: 48px;
  padding: 0 var(--space-3);
}

.toggle-label {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

.toggle-input {
  width: 18px;
  height: 18px;
  accent-color: var(--color-brand-500);
}

.loading-wrap {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
}

.skeleton {
  border-radius: var(--radius-md);
  background: linear-gradient(
    90deg,
    var(--color-bg-secondary) 0%,
    var(--color-bg-elevated) 50%,
    var(--color-bg-secondary) 100%
  );
  background-size: 200% 100%;
  animation: shimmer 1.1s linear infinite;
}

.skeleton-line {
  height: 48px;
}

.skeleton-line-lg {
  height: 60px;
}

@keyframes shimmer {
  from { background-position: 0 0; }
  to { background-position: 200% 0; }
}
</style>
