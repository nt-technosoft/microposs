<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Plus, X, Upload, Image as ImageIcon } from 'lucide-vue-next'
import api from '@/api/client'
import {
  createProduct,
  fetchCategories,
  fetchCategory,
  uploadProductPhoto,
} from '@/api/catalog'
import type { Attribute, Category } from '@/types/models'
import { PricingMode } from '@/types/enums'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'
import { useToast } from '@/composables/useToast'

interface SelectedAttribute {
  attributeId: number
  attributeName: string
  selectedValues: string[]
  customInput: string
}

interface CharacteristicRow {
  key: number
  name: string
  value: string
}

const router = useRouter()
const toast = useToast()

const categories = ref<Category[]>([])
const attributes = ref<Attribute[]>([])
const isSubmitting = ref(false)
const isGeneratingVariants = ref(false)
const errorMessage = ref('')

const productName = ref('')
const description = ref('')
const selectedCategory = ref<number | null>(null)
const pricingMode = ref<PricingMode>(PricingMode.DEFAULT_EDITABLE)
const basePrice = ref('')
const hasVariants = ref(false)
const selectedAttributes = ref<SelectedAttribute[]>([])
const characteristics = ref<CharacteristicRow[]>([])
const photoFile = ref<File | null>(null)
const photoPreview = ref<string | null>(null)
const touchedPricingMode = ref(false)
let rowKey = 1

const errors = ref<Record<string, string>>({})

const pricingModeOptions: Array<{ value: PricingMode; label: string }> = [
  { value: PricingMode.FIXED_LOCKED, label: 'Фиксированная' },
  { value: PricingMode.DEFAULT_EDITABLE, label: 'По умолчанию, можно менять' },
  { value: PricingMode.ASK_EACH_SALE, label: 'Всегда спрашивать на продаже' },
]

const categoryOptions = computed(() => ([
  { value: null, label: 'Без категории' },
  ...categories.value.map((category) => ({
    value: category.id,
    label: category.name,
  })),
]))

const availableAttributes = computed(() =>
  attributes.value.filter(
    (attr) => !selectedAttributes.value.some((sa) => sa.attributeId === attr.id),
  ),
)

const canGenerateVariants = computed(() =>
  selectedAttributes.value.length > 0
  && selectedAttributes.value.every((sa) => sa.selectedValues.length > 0),
)

function normalizeAttributesPayload(data: unknown): Attribute[] {
  if (Array.isArray(data)) return data as Attribute[]
  if (data && typeof data === 'object' && Array.isArray((data as { results?: unknown }).results)) {
    return (data as { results: Attribute[] }).results
  }
  return []
}

async function loadBootstrapData(): Promise<void> {
  try {
    const [categoryData, attributesResponse] = await Promise.all([
      fetchCategories(),
      api.get('/api/v1/catalog/attributes/'),
    ])
    categories.value = categoryData
    attributes.value = normalizeAttributesPayload(attributesResponse.data)
  } catch {
    errorMessage.value = 'Не удалось загрузить справочники для формы'
  }
}

function addCharacteristic(): void {
  characteristics.value = [
    ...characteristics.value,
    {
      key: rowKey++,
      name: '',
      value: '',
    },
  ]
}

function removeCharacteristic(key: number): void {
  characteristics.value = characteristics.value.filter((row) => row.key !== key)
}

function addAttribute(attr: Attribute): void {
  selectedAttributes.value = [
    ...selectedAttributes.value,
    {
      attributeId: attr.id,
      attributeName: attr.name,
      selectedValues: [],
      customInput: '',
    },
  ]
}

function removeAttribute(attrId: number): void {
  selectedAttributes.value = selectedAttributes.value.filter((sa) => sa.attributeId !== attrId)
}

function toggleValue(attrId: number, value: string): void {
  selectedAttributes.value = selectedAttributes.value.map((sa) => {
    if (sa.attributeId !== attrId) return sa
    const exists = sa.selectedValues.includes(value)
    return {
      ...sa,
      selectedValues: exists
        ? sa.selectedValues.filter((item) => item !== value)
        : [...sa.selectedValues, value],
    }
  })
}

function addCustomValue(attrId: number): void {
  selectedAttributes.value = selectedAttributes.value.map((sa) => {
    if (sa.attributeId !== attrId) return sa
    const value = sa.customInput.trim()
    if (!value || sa.selectedValues.includes(value)) {
      return { ...sa, customInput: '' }
    }
    return {
      ...sa,
      selectedValues: [...sa.selectedValues, value],
      customInput: '',
    }
  })
}

function updateCustomInput(attrId: number, value: string): void {
  selectedAttributes.value = selectedAttributes.value.map((sa) =>
    sa.attributeId === attrId ? { ...sa, customInput: value } : sa,
  )
}

function onCustomInputKeydown(event: KeyboardEvent, attrId: number): void {
  if (event.key === 'Enter') {
    event.preventDefault()
    addCustomValue(attrId)
  }
}

function getAttributeValues(attrId: number) {
  return attributes.value.find((item) => item.id === attrId)?.values ?? []
}

function onPhotoChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  photoFile.value = file
  if (photoPreview.value) {
    URL.revokeObjectURL(photoPreview.value)
    photoPreview.value = null
  }
  if (file) {
    photoPreview.value = URL.createObjectURL(file)
  }
}

function clearPhoto(): void {
  photoFile.value = null
  if (photoPreview.value) {
    URL.revokeObjectURL(photoPreview.value)
    photoPreview.value = null
  }
}

function validate(): boolean {
  const nextErrors: Record<string, string> = {}
  if (!productName.value.trim()) {
    nextErrors.name = 'Введите название товара'
  }
  if (pricingMode.value !== PricingMode.ASK_EACH_SALE) {
    const parsed = Number.parseFloat(basePrice.value)
    if (!Number.isFinite(parsed) || parsed < 0) {
      nextErrors.price = 'Проверьте базовую цену'
    }
  }
  errors.value = nextErrors
  return Object.keys(nextErrors).length === 0
}

watch(selectedCategory, async (categoryId) => {
  if (categoryId === null) return
  try {
    const category = await fetchCategory(categoryId)
    if (!touchedPricingMode.value) {
      pricingMode.value = category.default_pricing_mode
    }
    const templateChars = Array.isArray(category.template_characteristics)
      ? category.template_characteristics
      : []
    if (templateChars.length > 0) {
      characteristics.value = templateChars.map((item, index) => ({
        key: rowKey++ + index,
        name: item.name,
        value: item.default_value ?? '',
      }))
    }
  } catch {
    // keep manual values when template load fails
  }
})

async function handleSubmit(): Promise<void> {
  if (!validate()) return

  isSubmitting.value = true
  errorMessage.value = ''
  try {
    const createdProduct = await createProduct({
      name: productName.value.trim(),
      category_id: selectedCategory.value,
      pricing_mode: pricingMode.value,
      base_price: pricingMode.value === PricingMode.ASK_EACH_SALE ? null : basePrice.value,
      description: description.value.trim(),
      characteristics: characteristics.value
        .map((row) => ({
          name: row.name.trim(),
          value: row.value.trim(),
        }))
        .filter((row) => row.name.length > 0),
    })

    if (photoFile.value) {
      await uploadProductPhoto(createdProduct.id, photoFile.value)
    }

    if (hasVariants.value && canGenerateVariants.value) {
      isGeneratingVariants.value = true
      try {
        await api.post(`/api/v1/catalog/products/${createdProduct.id}/generate-variants/`, {
          attributes: selectedAttributes.value.map((sa) => ({
            attribute_id: sa.attributeId,
            values: sa.selectedValues,
          })),
        })
      } finally {
        isGeneratingVariants.value = false
      }
    }

    toast.success('Товар успешно создан')
    router.push({ name: 'products' })
  } catch (error: unknown) {
    const apiError = error as { response?: { data?: { detail?: string } } }
    errorMessage.value = apiError.response?.data?.detail ?? 'Не удалось создать товар'
  } finally {
    isSubmitting.value = false
  }
}

onMounted(async () => {
  await loadBootstrapData()
  addCharacteristic()
})
</script>

<template>
  <div class="create-page">
    <header class="page-header">
      <button class="back-btn" type="button" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="20" :stroke-width="1.75" />
      </button>
      <h1 class="page-title">Новый товар</h1>
      <div class="header-spacer" aria-hidden="true" />
    </header>

    <form class="form-content" @submit.prevent="handleSubmit">
      <div v-if="errorMessage" class="error-banner" role="alert">
        {{ errorMessage }}
      </div>

      <section class="form-section">
        <BaseInput
          v-model="productName"
          label="Название *"
          placeholder="Введите название товара"
          :error="errors.name"
        />

        <div class="input-group">
          <label class="input-label">Категория</label>
          <BaseSelect
            v-model="selectedCategory"
            :options="categoryOptions"
            title="Выбор категории"
            placeholder="Без категории"
          />
        </div>

        <div class="input-group">
          <label class="input-label">Тип цены</label>
          <BaseSelect
            v-model="pricingMode"
            :options="pricingModeOptions"
            title="Тип цены"
            placeholder="Выберите режим"
            @update:model-value="touchedPricingMode = true"
          />
        </div>

        <BaseInput
          v-if="pricingMode !== PricingMode.ASK_EACH_SALE"
          v-model="basePrice"
          label="Базовая цена *"
          type="number"
          placeholder="0"
          :error="errors.price"
        />

        <div class="input-group">
          <label class="input-label">Описание</label>
          <textarea
            v-model="description"
            class="description-field"
            rows="3"
            placeholder="Описание товара"
          />
        </div>

        <div class="photo-block">
          <label class="input-label">Фото товара</label>
          <div class="photo-preview">
            <img v-if="photoPreview" :src="photoPreview" alt="Предпросмотр фото">
            <ImageIcon v-else :size="32" :stroke-width="1.5" />
          </div>
          <label class="photo-upload">
            <Upload :size="16" :stroke-width="2" />
            <span>Загрузить фото</span>
            <input type="file" accept="image/*" class="hidden-file" @change="onPhotoChange">
          </label>
          <button v-if="photoFile" type="button" class="remove-photo" @click="clearPhoto">
            Удалить фото
          </button>
        </div>
      </section>

      <section class="form-section">
        <div class="section-title-row">
          <span class="section-title">Характеристики</span>
          <button type="button" class="tiny-btn" @click="addCharacteristic">
            <Plus :size="14" :stroke-width="2" />
            Добавить
          </button>
        </div>

        <div v-for="row in characteristics" :key="row.key" class="characteristic-row">
          <BaseInput v-model="row.name" label="Название" placeholder="Материал" />
          <BaseInput v-model="row.value" label="Значение" placeholder="Кожа" />
          <button type="button" class="remove-btn" @click="removeCharacteristic(row.key)">
            <X :size="16" :stroke-width="2" />
          </button>
        </div>
      </section>

      <section class="form-section">
        <div class="toggle-row">
          <div class="toggle-text">
            <span class="toggle-title">Есть варианты</span>
            <span class="toggle-desc">Размеры, цвета и другие атрибуты</span>
          </div>
          <button
            type="button"
            class="toggle-switch"
            :class="{ 'toggle-switch--on': hasVariants }"
            @click="hasVariants = !hasVariants"
          >
            <span class="toggle-knob" />
          </button>
        </div>

        <div v-if="hasVariants" class="variants-config">
          <div
            v-for="sa in selectedAttributes"
            :key="sa.attributeId"
            class="attribute-block"
          >
            <div class="attribute-header">
              <span class="attribute-name">{{ sa.attributeName }}</span>
              <button type="button" class="remove-btn" @click="removeAttribute(sa.attributeId)">
                <X :size="14" :stroke-width="2" />
              </button>
            </div>

            <div class="value-chips">
              <button
                v-for="value in getAttributeValues(sa.attributeId)"
                :key="value.id"
                type="button"
                class="value-chip"
                :class="{ 'value-chip--selected': sa.selectedValues.includes(value.value) }"
                @click="toggleValue(sa.attributeId, value.value)"
              >
                {{ value.value }}
              </button>
            </div>

            <div class="custom-value-row">
              <input
                :value="sa.customInput"
                type="text"
                class="custom-input"
                placeholder="Свое значение"
                @input="updateCustomInput(sa.attributeId, ($event.target as HTMLInputElement).value)"
                @keydown="onCustomInputKeydown($event, sa.attributeId)"
              >
              <button type="button" class="tiny-btn" @click="addCustomValue(sa.attributeId)">
                Добавить
              </button>
            </div>
          </div>

          <div class="add-attributes">
            <button
              v-for="attr in availableAttributes"
              :key="attr.id"
              type="button"
              class="tiny-btn"
              @click="addAttribute(attr)"
            >
              <Plus :size="12" :stroke-width="2" />
              {{ attr.name }}
            </button>
          </div>
        </div>
      </section>

      <div class="footer-actions">
        <BaseButton type="button" variant="secondary" :full-width="true" @click="router.back()">
          Отмена
        </BaseButton>
        <BaseButton type="submit" variant="primary" :full-width="true" :loading="isSubmitting || isGeneratingVariants">
          Создать товар
        </BaseButton>
      </div>
    </form>
  </div>
</template>

<style scoped>
.create-page {
  min-height: 100dvh;
  background: var(--color-bg-primary);
  padding-bottom: calc(var(--bottom-nav-height) + var(--space-8));
}

.page-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 0 var(--space-4);
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border-subtle);
  height: var(--header-height);
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
  border-radius: var(--radius-full);
  color: var(--color-text-secondary);
}

.page-title {
  flex: 1;
  text-align: center;
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.form-content {
  display: grid;
  gap: var(--space-4);
  padding: var(--space-4);
}

.form-section {
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-bg-elevated);
  padding: var(--space-4);
  display: grid;
  gap: var(--space-3);
}

.error-banner {
  border: 1px solid var(--color-error);
  border-radius: var(--radius-md);
  background: var(--color-error-bg);
  color: var(--color-error);
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
}

.input-group {
  display: grid;
  gap: var(--space-1);
}

.input-label {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.description-field {
  width: 100%;
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  min-height: 88px;
  padding: var(--space-3);
  background: var(--color-bg-elevated);
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

.section-title {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.characteristic-row {
  display: grid;
  gap: var(--space-2);
}

.remove-btn {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-default);
  color: var(--color-text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.tiny-btn {
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

.toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.toggle-text {
  display: grid;
  gap: 2px;
}

.toggle-title {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.toggle-desc {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.toggle-switch {
  width: 48px;
  height: 28px;
  border-radius: var(--radius-full);
  background: var(--color-bg-secondary);
  border: 1px solid var(--color-border-default);
  position: relative;
  padding: 2px;
}

.toggle-switch--on {
  background: var(--color-brand-100);
  border-color: var(--color-brand-300);
}

.toggle-knob {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #fff;
  position: absolute;
  left: 2px;
  top: 2px;
  transition: transform var(--duration-fast) var(--ease-out);
}

.toggle-switch--on .toggle-knob {
  transform: translateX(20px);
}

.variants-config {
  display: grid;
  gap: var(--space-3);
}

.attribute-block {
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  display: grid;
  gap: var(--space-2);
}

.attribute-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.attribute-name {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

.value-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.value-chip {
  min-height: 30px;
  padding: 0 var(--space-2);
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border-default);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.value-chip--selected {
  border-color: var(--color-brand-500);
  background: var(--color-brand-50);
  color: var(--color-brand-600);
}

.custom-value-row {
  display: flex;
  gap: var(--space-2);
}

.custom-input {
  flex: 1;
  min-height: 34px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-default);
  padding: 0 var(--space-2);
}

.add-attributes {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.footer-actions {
  display: grid;
  gap: var(--space-2);
  margin-top: var(--space-2);
}
</style>
