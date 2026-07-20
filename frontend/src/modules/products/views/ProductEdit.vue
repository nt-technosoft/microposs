<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, Plus, X, Upload, Image as ImageIcon } from 'lucide-vue-next'
import api from '@/api/client'
import {
  deleteProductPhoto,
  fetchCategories,
  fetchProduct,
  updateProduct,
  uploadProductPhoto,
} from '@/api/catalog'
import type { Category, Product } from '@/types/models'
import { PricingMode } from '@/types/enums'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { useToast } from '@/composables/useToast'
import PageChrome from '@/components/layout/PageChrome.vue'
import PageContainer from '@/components/layout/PageContainer.vue'

interface CharacteristicRow {
  key: number
  name: string
  value: string
}

const route = useRoute()
const router = useRouter()
const toast = useToast()
const { t } = useI18n()

const product = ref<Product | null>(null)
const categories = ref<Category[]>([])
const isLoading = ref(true)
const isSaving = ref(false)
const errorMessage = ref('')

const name = ref('')
const description = ref('')
const selectedCategory = ref<number | null>(null)
const pricingMode = ref<PricingMode>(PricingMode.DEFAULT_EDITABLE)
const basePrice = ref('')
const isActive = ref(true)
const characteristics = ref<CharacteristicRow[]>([])
const photoPreview = ref<string | null>(null)
const photoFile = ref<File | null>(null)
let rowKey = 1

const pricingModeOptions = computed<Array<{ value: PricingMode; label: string }>>(() => [
  { value: PricingMode.FIXED_LOCKED, label: t('products.pricingFixed') },
  { value: PricingMode.DEFAULT_EDITABLE, label: t('products.pricingDefaultEditable') },
  { value: PricingMode.ASK_EACH_SALE, label: t('products.pricingAskEachSaleLong') },
])

const categoryOptions = computed(() => ([
  { value: null, label: t('products.noCategory') },
  ...categories.value.map((category) => ({
    value: category.id,
    label: category.name,
  })),
]))

const showBasePrice = computed(() => pricingMode.value !== PricingMode.ASK_EACH_SALE)

function parseCategoryId(rawCategory: unknown): number | null {
  if (typeof rawCategory === 'number' && Number.isFinite(rawCategory)) return rawCategory
  if (rawCategory && typeof rawCategory === 'object' && 'id' in rawCategory) {
    const id = Number((rawCategory as { id?: unknown }).id)
    return Number.isFinite(id) ? id : null
  }
  return null
}

function addCharacteristic(nameValue = '', valueValue = ''): void {
  characteristics.value = [
    ...characteristics.value,
    {
      key: rowKey++,
      name: nameValue,
      value: valueValue,
    },
  ]
}

function removeCharacteristic(key: number): void {
  characteristics.value = characteristics.value.filter((row) => row.key !== key)
}

function onPhotoChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  photoFile.value = file
  if (photoPreview.value && photoPreview.value.startsWith('blob:')) {
    URL.revokeObjectURL(photoPreview.value)
  }
  photoPreview.value = file ? URL.createObjectURL(file) : (product.value?.photo_url ?? null)
}

async function removePhoto(): Promise<void> {
  const id = Number(route.params.id)
  if (!Number.isFinite(id)) return
  try {
    await deleteProductPhoto(id)
    photoFile.value = null
    photoPreview.value = null
    toast.success(t('products.photoDeleted'))
  } catch {
    toast.error(t('products.photoDeleteFailed'))
  }
}

async function loadData(): Promise<void> {
  const id = Number(route.params.id)
  if (!Number.isFinite(id)) {
    errorMessage.value = t('products.invalidProductId')
    isLoading.value = false
    return
  }

  isLoading.value = true
  errorMessage.value = ''
  try {
    const [loadedProduct, loadedCategories] = await Promise.all([
      fetchProduct(id),
      fetchCategories(),
    ])

    product.value = loadedProduct
    categories.value = loadedCategories
    name.value = loadedProduct.name
    description.value = loadedProduct.description ?? ''
    selectedCategory.value = parseCategoryId(loadedProduct.category)
    pricingMode.value = loadedProduct.pricing_mode
    basePrice.value = loadedProduct.base_price ?? ''
    isActive.value = Boolean(loadedProduct.is_active)
    photoPreview.value = loadedProduct.photo_url ?? null

    characteristics.value = (loadedProduct.characteristics ?? []).map((row: { name: string; value: string }, index: number) => ({
      key: rowKey++ + index,
      name: row.name,
      value: row.value,
    }))
    if (characteristics.value.length === 0) {
      addCharacteristic()
    }
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : t('products.productLoadFailed')
  } finally {
    isLoading.value = false
  }
}

function validate(): boolean {
  if (!name.value.trim()) {
    errorMessage.value = t('products.nameRequired')
    return false
  }
  if (showBasePrice.value) {
    const parsed = Number.parseFloat(basePrice.value)
    if (!Number.isFinite(parsed) || parsed < 0) {
      errorMessage.value = t('products.priceInvalid')
      return false
    }
  }
  return true
}

async function saveProduct(): Promise<void> {
  if (!validate()) return
  const id = Number(route.params.id)
  if (!Number.isFinite(id)) return

  isSaving.value = true
  errorMessage.value = ''
  try {
    await updateProduct(id, {
      name: name.value.trim(),
      description: description.value.trim(),
      category: selectedCategory.value,
      pricing_mode: pricingMode.value,
      base_price: showBasePrice.value ? basePrice.value : null,
      is_active: isActive.value,
    })
    const payload = characteristics.value
      .map((item) => ({
        name: item.name.trim(),
        value: item.value.trim(),
      }))
      .filter((item) => item.name.length > 0)
    await apiPatchCharacteristics(id, payload)

    if (photoFile.value) {
      await uploadProductPhoto(id, photoFile.value)
    }

    toast.success(t('products.saveSuccess'))
    router.push({ name: 'products' })
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : t('products.saveFailed')
  } finally {
    isSaving.value = false
  }
}

async function apiPatchCharacteristics(
  id: number,
  payload: Array<{ name: string; value: string }>,
): Promise<void> {
  await api.patch(`/api/v1/catalog/products/${id}/`, {
    characteristics: payload,
  })
}

onMounted(loadData)
</script>

<template>
  <div class="edit-page">
    <PageChrome :title="t('products.editTitle')">
      <template #back>
        <button class="back-btn" type="button" :aria-label="t('common.back')" @click="router.back()">
          <ArrowLeft :size="18" :stroke-width="2" />
        </button>
      </template>
    </PageChrome>

    <PageContainer size="wide">
      <div v-if="isLoading" class="loading-wrap" aria-busy="true">
        <div class="skeleton skeleton-line" />
        <div class="skeleton skeleton-line" />
        <div class="skeleton skeleton-line-lg" />
      </div>

    <form v-else class="form" @submit.prevent="saveProduct">
      <div v-if="errorMessage" class="error-banner" role="alert">
        <span>{{ errorMessage }}</span>
      </div>

      <div class="form-details">
        <BaseInput v-model="name" :label="`${t('products.nameLabel')} *`" :placeholder="t('products.namePlaceholder')" />

        <div class="field-group">
          <label class="input-label">{{ t('products.description') }}</label>
          <textarea
            v-model="description"
            class="textarea-field"
            rows="3"
            :placeholder="t('products.descriptionPlaceholder')"
          />
        </div>

        <div class="field-group">
          <label class="input-label">{{ t('products.categoryFilter') }}</label>
          <BaseSelect
            v-model="selectedCategory"
            :options="categoryOptions"
            :title="t('products.chooseCategory')"
            :placeholder="t('products.noCategory')"
          />
        </div>

        <div class="field-group">
          <label class="input-label">{{ t('products.priceType') }}</label>
          <BaseSelect
            v-model="pricingMode"
            :options="pricingModeOptions"
            :title="t('products.choosePriceType')"
            :placeholder="t('products.priceType')"
          />
        </div>

        <BaseInput
          v-if="showBasePrice"
          v-model="basePrice"
          :label="t('products.basePrice')"
          type="number"
          placeholder="0"
        />
      </div>

      <div class="photo-block">
        <label class="input-label">{{ t('products.productPhoto') }}</label>
        <div class="photo-preview">
          <img v-if="photoPreview" :src="photoPreview" :alt="t('products.productPhoto')">
          <ImageIcon v-else :size="32" :stroke-width="1.5" />
        </div>
        <label class="photo-upload">
          <Upload :size="16" :stroke-width="2" />
          <span>{{ t('products.uploadNewPhoto') }}</span>
          <input type="file" accept="image/*" class="hidden-file" @change="onPhotoChange">
        </label>
        <button v-if="photoPreview" type="button" class="remove-photo" @click="removePhoto">
          {{ t('products.deletePhoto') }}
        </button>
      </div>

      <div class="section-title-row">
        <span class="input-label">{{ t('products.templateCharacteristics') }}</span>
        <button type="button" class="tiny-btn" @click="addCharacteristic()">
          <Plus :size="14" :stroke-width="2" />
          {{ t('common.add') }}
        </button>
      </div>

      <div v-for="row in characteristics" :key="row.key" class="characteristic-row">
        <BaseInput v-model="row.name" :label="t('products.characteristicName')" :placeholder="t('products.materialPlaceholder')" />
        <BaseInput v-model="row.value" :label="t('products.characteristicValue')" :placeholder="t('products.leatherPlaceholder')" />
        <button type="button" class="tiny-remove" @click="removeCharacteristic(row.key)">
          <X :size="14" :stroke-width="2" />
        </button>
      </div>

      <label class="toggle-row">
        <span class="toggle-label">{{ t('products.productActive') }}</span>
        <input v-model="isActive" class="toggle-input" type="checkbox">
      </label>

      <BaseButton
        type="submit"
        variant="primary"
        size="lg"
        :full-width="true"
        :loading="isSaving"
        :disabled="isSaving"
      >
        {{ t('common.save') }}
      </BaseButton>
    </form>
    </PageContainer>
  </div>
</template>

<style scoped>
.edit-page {
  min-height: 100%;
  background: var(--color-bg-primary);
  position: relative;
}

.back-btn {
  display: inline-flex;
  width: 40px;
  height: 40px;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
}

.form {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  padding-bottom: calc(var(--bottom-nav-height) + var(--space-8));
}

.form-details {
  display: grid;
  gap: var(--space-3);
}

.field-group {
  display: grid;
  gap: var(--space-1);
}

.input-label {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

.textarea-field {
  width: 100%;
  min-height: 88px;
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  padding: var(--space-3) var(--space-4);
  font-size: var(--text-base);
  line-height: 1.4;
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

.photo-block {
  display: grid;
  gap: var(--space-2);
}

.photo-preview {
  width: 100%;
  aspect-ratio: 4 / 3;
  border-radius: var(--radius-md);
  border: 1px dashed var(--color-border-default);
  background: var(--color-bg-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-tertiary);
  overflow: hidden;
}

.photo-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.photo-upload {
  min-height: 40px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-default);
  padding: 0 var(--space-3);
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  width: fit-content;
}

.hidden-file {
  display: none;
}

.remove-photo {
  width: fit-content;
  min-height: 32px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-default);
  padding: 0 var(--space-2);
  color: var(--color-text-secondary);
}

.section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.tiny-btn,
.tiny-remove {
  min-height: 32px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  padding: 0 var(--space-2);
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-xs);
}

.characteristic-row {
  display: grid;
  gap: var(--space-2);
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
  height: 88px;
}

@keyframes shimmer {
  from { background-position: 0 0; }
  to { background-position: 200% 0; }
}

@media (min-width: 768px) {
  .edit-page {
    min-height: 0;
    padding-bottom: var(--space-8);
  }

  .form,
  .loading-wrap {
    max-width: 1120px;
    margin-inline: auto;
  }

  .form {
    grid-template-columns: minmax(0, 1.2fr) minmax(280px, 0.8fr);
    align-items: start;
    gap: var(--space-5);
    padding-top: var(--space-6);
    padding-bottom: var(--space-6);
  }

  .error-banner,
  .section-title-row,
  .characteristic-row,
  .toggle-row,
  .form > :last-child {
    grid-column: 1 / -1;
  }

  .form-details {
    grid-column: 1;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    align-items: start;
    gap: var(--space-4);
  }

  .form-details > :first-child,
  .form-details > :nth-child(2) {
    grid-column: 1 / -1;
  }

  .photo-block {
    grid-column: 2;
    grid-row: 2 / span 2;
  }

  .photo-preview {
    width: min(100%, 280px);
    aspect-ratio: 1 / 1;
  }

  .characteristic-row {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
    align-items: end;
  }

  .form > :last-child {
    width: min(280px, 100%);
    justify-self: end;
  }
}
</style>
