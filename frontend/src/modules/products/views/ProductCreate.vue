<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Plus, X, Tag, Layers, AlertCircle } from 'lucide-vue-next'
import api from '@/api/client'
import { fetchCategories } from '@/api/catalog'
import type { Category, Attribute } from '@/types/models'
import { PricingMode } from '@/types/enums'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import { useToast } from '@/composables/useToast'

const router = useRouter()
const toast = useToast()

// --- State ---
const categories = ref<Category[]>([])
const attributes = ref<Attribute[]>([])
const isSubmitting = ref(false)
const isGeneratingVariants = ref(false)
const errorMessage = ref('')

// Form fields
const productName = ref('')
const selectedCategory = ref<number | ''>('')
const pricingMode = ref<PricingMode>(PricingMode.FIXED_LOCKED)
const basePrice = ref('')
const hasVariants = ref(false)

// Variants: each attribute with chosen values
interface SelectedAttribute {
  attributeId: number
  attributeName: string
  selectedValues: string[]
  customInput: string
}

const selectedAttributes = ref<SelectedAttribute[]>([])

// Validation errors
const errors = ref<Record<string, string>>({})

// --- Computed ---
const availableAttributes = computed(() =>
  attributes.value.filter(
    (attr) => !selectedAttributes.value.some((sa) => sa.attributeId === attr.id)
  )
)

const canGenerateVariants = computed(() =>
  selectedAttributes.value.length > 0 &&
  selectedAttributes.value.every((sa) => sa.selectedValues.length > 0)
)

const pricingModeOptions: Array<{ value: PricingMode; label: string }> = [
  { value: PricingMode.FIXED_LOCKED, label: 'Фиксированная' },
  { value: PricingMode.DEFAULT_EDITABLE, label: 'Гибкая' },
  { value: PricingMode.ASK_EACH_SALE, label: 'Спрашивать' },
]

// --- Validation ---
function validate(): boolean {
  const newErrors: Record<string, string> = {}

  if (!productName.value.trim()) {
    newErrors.name = 'Введите название товара'
  } else if (productName.value.trim().length < 2) {
    newErrors.name = 'Название должно быть не менее 2 символов'
  }

  if (pricingMode.value !== PricingMode.ASK_EACH_SALE) {
    if (!basePrice.value) {
      newErrors.price = 'Введите базовую цену'
    } else if (parseFloat(basePrice.value) < 0) {
      newErrors.price = 'Цена не может быть отрицательной'
    }
  }

  errors.value = { ...newErrors }
  return Object.keys(newErrors).length === 0
}

// --- Data loading ---
async function loadCategories(): Promise<void> {
  try {
    categories.value = await fetchCategories()
  } catch {
    // Non-critical — category stays empty
  }
}

async function loadAttributes(): Promise<void> {
  try {
    const { data } = await api.get<Attribute[]>('/api/v1/catalog/attributes/')
    attributes.value = [...data]
  } catch {
    // Non-critical
  }
}

// --- Attribute management ---
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
  selectedAttributes.value = selectedAttributes.value.filter(
    (sa) => sa.attributeId !== attrId
  )
}

function toggleValue(attrId: number, value: string): void {
  selectedAttributes.value = selectedAttributes.value.map((sa) => {
    if (sa.attributeId !== attrId) return sa
    const already = sa.selectedValues.includes(value)
    return {
      ...sa,
      selectedValues: already
        ? sa.selectedValues.filter((v) => v !== value)
        : [...sa.selectedValues, value],
    }
  })
}

function addCustomValue(attrId: number): void {
  selectedAttributes.value = selectedAttributes.value.map((sa) => {
    if (sa.attributeId !== attrId) return sa
    const trimmed = sa.customInput.trim()
    if (!trimmed || sa.selectedValues.includes(trimmed)) {
      return { ...sa, customInput: '' }
    }
    return {
      ...sa,
      selectedValues: [...sa.selectedValues, trimmed],
      customInput: '',
    }
  })
}

function onCustomInputKeydown(event: KeyboardEvent, attrId: number): void {
  if (event.key === 'Enter') {
    event.preventDefault()
    addCustomValue(attrId)
  }
}

function updateCustomInput(attrId: number, value: string): void {
  selectedAttributes.value = selectedAttributes.value.map((sa) =>
    sa.attributeId === attrId ? { ...sa, customInput: value } : sa
  )
}

function getAttributeValues(attrId: number) {
  return attributes.value.find((a) => a.id === attrId)?.values ?? []
}

// --- Submit ---
async function handleSubmit(): Promise<void> {
  if (!validate()) return

  isSubmitting.value = true
  errorMessage.value = ''

  try {
    const payload = {
      name: productName.value.trim(),
      category_id: selectedCategory.value !== '' ? Number(selectedCategory.value) : null,
      pricing_mode: pricingMode.value,
      base_price: basePrice.value || null,
      has_variants: hasVariants.value,
    }

    const { data: createdProduct } = await api.post<{ id: number }>(
      '/api/v1/catalog/products/',
      payload
    )

    if (hasVariants.value && canGenerateVariants.value) {
      isGeneratingVariants.value = true
      try {
        const genPayload = {
          attributes: selectedAttributes.value.map((sa) => ({
            attribute_id: sa.attributeId,
            values: sa.selectedValues,
          })),
        }
        const { data } = await api.post<{ variants_created: number }>(
          `/api/v1/catalog/products/${createdProduct.id}/generate-variants/`,
          genPayload
        )
        toast.success(`Товар создан, сгенерировано ${data.variants_created} вариантов`)
      } catch {
        toast.warning('Товар создан, но варианты не удалось сгенерировать')
      } finally {
        isGeneratingVariants.value = false
      }
    } else {
      toast.success('Товар успешно создан')
    }

    router.push({ name: 'products' })
  } catch (error: unknown) {
    const axiosError = error as { response?: { data?: { detail?: string; name?: string[] } } }
    const detail =
      axiosError.response?.data?.detail ??
      axiosError.response?.data?.name?.[0] ??
      'Не удалось создать товар. Попробуйте ещё раз.'
    errorMessage.value = detail
  } finally {
    isSubmitting.value = false
  }
}

onMounted(() => {
  Promise.all([loadCategories(), loadAttributes()])
})
</script>

<template>
  <div class="create-page">
    <!-- Header -->
    <header class="page-header">
      <button
        class="back-btn"
        type="button"
        aria-label="Назад"
        @click="router.back()"
      >
        <ArrowLeft :size="20" :stroke-width="1.75" />
      </button>
      <h1 class="page-title">Новый товар</h1>
      <div class="header-spacer" aria-hidden="true" />
    </header>

    <form class="form-content" novalidate @submit.prevent="handleSubmit">
      <!-- Error banner -->
      <div v-if="errorMessage" class="error-banner" role="alert">
        <AlertCircle :size="16" :stroke-width="1.75" aria-hidden="true" />
        {{ errorMessage }}
      </div>

      <!-- Section: Basic info -->
      <section class="form-section">
        <div class="section-label">
          <Tag :size="14" :stroke-width="1.75" aria-hidden="true" />
          Основная информация
        </div>

        <div class="form-fields">
          <BaseInput
            v-model="productName"
            label="Название товара *"
            placeholder="Например: Nike Air Max 90"
            :error="errors.name"
          />

          <div class="input-group">
            <label class="input-label" for="category-select">Категория</label>
            <select
              id="category-select"
              v-model="selectedCategory"
              class="styled-select"
            >
              <option value="">Без категории</option>
              <option
                v-for="cat in categories"
                :key="cat.id"
                :value="cat.id"
              >
                {{ cat.name }}
              </option>
            </select>
          </div>

          <!-- Pricing mode chips -->
          <div class="input-group">
            <span class="input-label" id="pricing-mode-label">Тип цены</span>
            <div class="chip-group" role="group" aria-labelledby="pricing-mode-label">
              <button
                v-for="option in pricingModeOptions"
                :key="option.value"
                type="button"
                class="chip"
                :class="{ 'chip--active': pricingMode === option.value }"
                @click="pricingMode = option.value"
              >
                {{ option.label }}
              </button>
            </div>
          </div>

          <div v-if="pricingMode !== PricingMode.ASK_EACH_SALE" class="price-field">
            <BaseInput
              v-model="basePrice"
              label="Базовая цена *"
              placeholder="0"
              type="number"
              :error="errors.price"
            />
            <div v-if="basePrice" class="price-hint">
              {{ parseFloat(basePrice).toLocaleString('ru-RU') }} сум
            </div>
          </div>
        </div>
      </section>

      <!-- Section: Variants -->
      <section class="form-section">
        <div class="section-label">
          <Layers :size="14" :stroke-width="1.75" aria-hidden="true" />
          Варианты товара
        </div>

        <div class="toggle-row">
          <div class="toggle-text">
            <span class="toggle-title">Есть варианты</span>
            <span class="toggle-desc">Размеры, цвета и другие атрибуты</span>
          </div>
          <button
            type="button"
            class="toggle-switch"
            :class="{ 'toggle-switch--on': hasVariants }"
            role="switch"
            :aria-checked="hasVariants"
            aria-label="Включить варианты"
            @click="hasVariants = !hasVariants"
          >
            <span class="toggle-knob" />
          </button>
        </div>

        <!-- Variants configuration -->
        <Transition name="variants-expand">
          <div v-if="hasVariants" class="variants-config">
            <!-- Selected attributes -->
            <div
              v-for="sa in selectedAttributes"
              :key="sa.attributeId"
              class="attribute-block"
            >
              <div class="attribute-header">
                <span class="attribute-name">{{ sa.attributeName }}</span>
                <button
                  type="button"
                  class="attribute-remove"
                  :aria-label="`Удалить атрибут ${sa.attributeName}`"
                  @click="removeAttribute(sa.attributeId)"
                >
                  <X :size="16" :stroke-width="2" />
                </button>
              </div>

              <!-- Preset values from API -->
              <div v-if="getAttributeValues(sa.attributeId).length" class="value-chips">
                <button
                  v-for="av in getAttributeValues(sa.attributeId)"
                  :key="av.id"
                  type="button"
                  class="value-chip"
                  :class="{ 'value-chip--selected': sa.selectedValues.includes(av.value) }"
                  @click="toggleValue(sa.attributeId, av.value)"
                >
                  {{ av.value }}
                </button>
              </div>

              <!-- Custom value input -->
              <div class="custom-value-row">
                <input
                  :value="sa.customInput"
                  type="text"
                  class="custom-value-input"
                  placeholder="Добавить значение..."
                  @input="updateCustomInput(sa.attributeId, ($event.target as HTMLInputElement).value)"
                  @keydown="onCustomInputKeydown($event, sa.attributeId)"
                />
                <button
                  type="button"
                  class="custom-value-add"
                  :disabled="!sa.customInput.trim()"
                  aria-label="Добавить значение"
                  @click="addCustomValue(sa.attributeId)"
                >
                  <Plus :size="16" :stroke-width="2" />
                </button>
              </div>

              <!-- Selected values summary -->
              <div v-if="sa.selectedValues.length > 0" class="selected-summary">
                <span
                  v-for="val in sa.selectedValues"
                  :key="val"
                  class="selected-value-tag"
                >
                  {{ val }}
                  <button
                    type="button"
                    class="remove-value"
                    :aria-label="`Удалить значение ${val}`"
                    @click="toggleValue(sa.attributeId, val)"
                  >
                    <X :size="12" :stroke-width="2.5" />
                  </button>
                </span>
              </div>
            </div>

            <!-- Add attribute -->
            <div v-if="availableAttributes.length > 0" class="add-attribute-wrap">
              <span class="add-attribute-label">Добавить атрибут:</span>
              <div class="add-attribute-chips">
                <button
                  v-for="attr in availableAttributes"
                  :key="attr.id"
                  type="button"
                  class="add-attr-chip"
                  @click="addAttribute(attr)"
                >
                  <Plus :size="14" :stroke-width="2" aria-hidden="true" />
                  {{ attr.name }}
                </button>
              </div>
            </div>

            <div v-if="selectedAttributes.length === 0" class="variants-empty">
              Добавьте хотя бы один атрибут (Размер, Цвет и т. д.)
            </div>
          </div>
        </Transition>
      </section>

      <!-- Footer actions -->
      <div class="form-footer">
        <BaseButton
          type="button"
          variant="secondary"
          @click="router.back()"
        >
          Отмена
        </BaseButton>
        <BaseButton
          type="submit"
          variant="primary"
          :loading="isSubmitting || isGeneratingVariants"
        >
          {{ hasVariants && canGenerateVariants ? 'Создать с вариантами' : 'Создать товар' }}
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

/* Header */
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

.back-btn {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  color: var(--color-text-secondary);
  transition: background var(--duration-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
  flex-shrink: 0;
}

.back-btn:hover {
  background: var(--color-bg-secondary);
}

.back-btn:active {
  transform: scale(0.92);
}

.page-title {
  flex: 1;
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  text-align: center;
}

.header-spacer {
  width: 40px;
  flex-shrink: 0;
}

/* Form */
.form-content {
  padding: var(--space-5);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-width: 600px;
  margin: 0 auto;
}

/* Error */
.error-banner {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
  background: var(--color-error-bg);
  color: var(--color-error);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
}

/* Section */
.form-section {
  background: var(--color-bg-elevated);
  border-radius: var(--radius-lg);
  padding: var(--space-5);
  box-shadow: var(--shadow-sm);
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.section-label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-tertiary);
}

.form-fields {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

/* Native select */
.input-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.input-label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
}

.styled-select {
  height: 48px;
  padding: 0 var(--space-10) 0 var(--space-4);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  font-size: var(--text-base);
  color: var(--color-text-primary);
  outline: none;
  -webkit-appearance: none;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%239C948A' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right var(--space-4) center;
  cursor: pointer;
  transition:
    border-color var(--duration-fast) var(--ease-out),
    box-shadow var(--duration-fast) var(--ease-out);
}

.styled-select:focus {
  border-color: var(--color-border-focus);
  box-shadow: 0 0 0 2px var(--color-brand-100);
}

/* Pricing chips */
.chip-group {
  display: flex;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.chip {
  height: 36px;
  padding: 0 var(--space-4);
  border: 1.5px solid var(--color-border-default);
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
  background: var(--color-bg-elevated);
  cursor: pointer;
  white-space: nowrap;
  transition:
    background var(--duration-fast) var(--ease-out),
    border-color var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out);
}

.chip:hover {
  border-color: var(--color-brand-300);
  color: var(--color-brand-500);
}

.chip--active {
  background: var(--color-brand-50);
  border-color: var(--color-brand-500);
  color: var(--color-brand-600);
  font-weight: var(--font-semibold);
}

/* Price field */
.price-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.price-hint {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  padding-left: var(--space-1);
}

/* Toggle */
.toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  min-height: 48px;
}

.toggle-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.toggle-title {
  font-size: var(--text-base);
  font-weight: var(--font-medium);
  color: var(--color-text-primary);
}

.toggle-desc {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.toggle-switch {
  width: 52px;
  height: 30px;
  min-width: 52px;
  border-radius: var(--radius-full);
  background: var(--color-bg-sunken);
  border: 2px solid var(--color-border-default);
  position: relative;
  cursor: pointer;
  transition:
    background var(--duration-normal) var(--ease-out),
    border-color var(--duration-normal) var(--ease-out);
  flex-shrink: 0;
}

.toggle-switch--on {
  background: var(--color-brand-500);
  border-color: var(--color-brand-500);
}

.toggle-knob {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 22px;
  height: 22px;
  border-radius: var(--radius-full);
  background: var(--color-bg-elevated);
  box-shadow: var(--shadow-sm);
  transition: transform var(--duration-normal) var(--ease-spring);
}

.toggle-switch--on .toggle-knob {
  transform: translateX(22px);
}

/* Variants config */
.variants-config {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding-top: var(--space-3);
  border-top: 1px solid var(--color-border-subtle);
}

.attribute-block {
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.attribute-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.attribute-name {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.attribute-remove {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-full);
  color: var(--color-text-tertiary);
  transition: background var(--duration-fast) var(--ease-out);
  flex-shrink: 0;
}

.attribute-remove:hover {
  background: var(--color-error-bg);
  color: var(--color-error);
}

/* Value chips */
.value-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.value-chip {
  height: 32px;
  padding: 0 var(--space-3);
  border: 1.5px solid var(--color-border-default);
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  background: var(--color-bg-elevated);
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease-out),
    border-color var(--duration-fast) var(--ease-out),
    color var(--duration-fast) var(--ease-out);
}

.value-chip:hover {
  border-color: var(--color-brand-300);
}

.value-chip--selected {
  background: var(--color-brand-50);
  border-color: var(--color-brand-500);
  color: var(--color-brand-600);
  font-weight: var(--font-medium);
}

/* Custom value input */
.custom-value-row {
  display: flex;
  gap: var(--space-2);
  align-items: center;
}

.custom-value-input {
  flex: 1;
  height: 40px;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-md);
  background: var(--color-bg-elevated);
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  outline: none;
  transition: border-color var(--duration-fast) var(--ease-out);
}

.custom-value-input::placeholder {
  color: var(--color-text-tertiary);
}

.custom-value-input:focus {
  border-color: var(--color-border-focus);
  box-shadow: 0 0 0 2px var(--color-brand-100);
}

.custom-value-add {
  width: 40px;
  height: 40px;
  min-width: 40px;
  border-radius: var(--radius-md);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background var(--duration-fast) var(--ease-out);
  flex-shrink: 0;
}

.custom-value-add:hover:not(:disabled) {
  background: var(--color-brand-600);
}

.custom-value-add:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Selected values */
.selected-summary {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.selected-value-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 26px;
  padding: 0 4px 0 var(--space-3);
  background: var(--color-brand-100);
  color: var(--color-brand-700);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
}

.remove-value {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: var(--radius-full);
  color: var(--color-brand-600);
  flex-shrink: 0;
  transition: background var(--duration-fast) var(--ease-out);
}

.remove-value:hover {
  background: var(--color-brand-200);
}

/* Add attribute */
.add-attribute-wrap {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.add-attribute-label {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.add-attribute-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.add-attr-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  height: 36px;
  padding: 0 var(--space-3);
  border: 1.5px dashed var(--color-brand-300);
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  color: var(--color-brand-500);
  background: var(--color-brand-50);
  cursor: pointer;
  transition:
    background var(--duration-fast) var(--ease-out),
    border-color var(--duration-fast) var(--ease-out);
}

.add-attr-chip:hover {
  background: var(--color-brand-100);
  border-style: solid;
}

/* Empty variants state */
.variants-empty {
  padding: var(--space-4);
  text-align: center;
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
  background: var(--color-bg-secondary);
  border-radius: var(--radius-md);
}

/* Transition */
.variants-expand-enter-active,
.variants-expand-leave-active {
  transition:
    opacity var(--duration-normal) var(--ease-out),
    transform var(--duration-normal) var(--ease-out);
}

.variants-expand-enter-from,
.variants-expand-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

/* Footer */
.form-footer {
  display: flex;
  gap: var(--space-3);
  justify-content: flex-end;
  padding-top: var(--space-2);
}

@media (max-width: 480px) {
  .form-footer {
    flex-direction: column-reverse;
  }
}

@media (prefers-reduced-motion: reduce) {
  .toggle-knob,
  .toggle-switch,
  .variants-expand-enter-active,
  .variants-expand-leave-active {
    transition: none;
    animation: none;
  }
}
</style>
