<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, Plus, FolderTree, AlertCircle, Pencil } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import api from '@/api/client'
import {
  applyCategorySettings,
  createCategory,
  fetchCategories,
  fetchCategory,
  replaceCategoryAttributes,
  replaceCategoryCharacteristics,
  updateCategory,
} from '@/api/catalog'
import type {
  Attribute,
  Category,
  CategoryAttributeTemplate,
  CategoryCharacteristicTemplate,
} from '@/types/models'
import { PricingMode } from '@/types/enums'
import { useToast } from '@/composables/useToast'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import BaseSelect from '@/components/base/BaseSelect.vue'
import AppEmptyState from '@/components/feedback/AppEmptyState.vue'

type CategoryRecord = Category & {
  parent?: number | null
  products_count?: number
}

interface CategoryNode {
  item: CategoryRecord
  level: number
}

interface TemplateAttributeRow {
  key: number
  attribute: number | null
  is_variant_generating: boolean
}

interface TemplateCharacteristicRow {
  key: number
  name: string
  default_value: string
  sort_order: number
}

const router = useRouter()
const toast = useToast()

const categories = ref<CategoryRecord[]>([])
const attributes = ref<Attribute[]>([])
const isLoading = ref(true)
const errorMessage = ref('')

const formSheetOpen = ref(false)
const editingCategoryId = ref<number | null>(null)
const isSaving = ref(false)
const formName = ref('')
const formParent = ref<number | null>(null)
const formPricingMode = ref<PricingMode>(PricingMode.DEFAULT_EDITABLE)
const applyToExisting = ref(false)
const applyPricingMode = ref(true)
const applyCharacteristics = ref(true)
const templateAttributes = ref<TemplateAttributeRow[]>([])
const templateCharacteristics = ref<TemplateCharacteristicRow[]>([])
let rowKey = 1

const pricingModeOptions: Array<{ value: PricingMode; label: string }> = [
  { value: PricingMode.DEFAULT_EDITABLE, label: 'По умолчанию, можно менять' },
  { value: PricingMode.ASK_EACH_SALE, label: 'Всегда спрашивать' },
  { value: PricingMode.FIXED_LOCKED, label: 'Фиксированная' },
]

const applyModeOptions = [
  { value: false, label: 'Только новые товары' },
  { value: true, label: 'Применить ко всем товарам категории' },
]

const boolOptions = [
  { value: true, label: 'Да' },
  { value: false, label: 'Нет' },
]

function getParentId(category: CategoryRecord): number | null {
  if (typeof category.parent === 'number') return category.parent
  if (typeof category.parent_id === 'number') return category.parent_id
  return null
}

const orderedCategories = computed<CategoryNode[]>(() => {
  const byParent = new Map<number | null, CategoryRecord[]>()

  for (const category of categories.value) {
    const parentId = getParentId(category)
    const current = byParent.get(parentId) ?? []
    current.push(category)
    byParent.set(parentId, current)
  }

  for (const group of byParent.values()) {
    group.sort((a, b) => a.name.localeCompare(b.name, 'ru'))
  }

  const result: CategoryNode[] = []

  function walk(parentId: number | null, level: number): void {
    const children = byParent.get(parentId) ?? []
    for (const child of children) {
      result.push({ item: child, level })
      walk(child.id, level + 1)
    }
  }

  walk(null, 0)
  return result
})

const parentSelectOptions = computed(() => ([
  { value: null, label: 'Без родителя' },
  ...categories.value.map((category) => ({
    value: category.id,
    label: category.name,
  })),
]))

const attributeOptions = computed(() =>
  attributes.value.map((attribute) => ({
    value: attribute.id,
    label: attribute.name,
  })),
)

async function loadCategories(): Promise<void> {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const data = await fetchCategories()
    categories.value = data as CategoryRecord[]
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить категории'
  } finally {
    isLoading.value = false
  }
}

async function loadAttributes(): Promise<void> {
  try {
    const { data } = await api.get<Attribute[] | { results?: Attribute[] }>('/api/v1/catalog/attributes/')
    attributes.value = Array.isArray(data) ? data : (Array.isArray(data.results) ? data.results : [])
  } catch {
    attributes.value = []
  }
}

function resetForm(): void {
  editingCategoryId.value = null
  formName.value = ''
  formParent.value = null
  formPricingMode.value = PricingMode.DEFAULT_EDITABLE
  applyToExisting.value = false
  applyPricingMode.value = true
  applyCharacteristics.value = true
  templateAttributes.value = []
  templateCharacteristics.value = []
}

function addTemplateAttribute(): void {
  templateAttributes.value = [
    ...templateAttributes.value,
    {
      key: rowKey++,
      attribute: null,
      is_variant_generating: true,
    },
  ]
}

function removeTemplateAttribute(key: number): void {
  templateAttributes.value = templateAttributes.value.filter((row) => row.key !== key)
}

function addTemplateCharacteristic(): void {
  templateCharacteristics.value = [
    ...templateCharacteristics.value,
    {
      key: rowKey++,
      name: '',
      default_value: '',
      sort_order: templateCharacteristics.value.length,
    },
  ]
}

function removeTemplateCharacteristic(key: number): void {
  templateCharacteristics.value = templateCharacteristics.value.filter((row) => row.key !== key)
}

function openCreateSheet(): void {
  resetForm()
  formSheetOpen.value = true
}

async function openEditSheet(categoryId: number): Promise<void> {
  resetForm()
  formSheetOpen.value = true
  editingCategoryId.value = categoryId
  try {
    const detail = await fetchCategory(categoryId)
    formName.value = detail.name
    formParent.value = typeof detail.parent === 'number' ? detail.parent : (detail.parent_id ?? null)
    formPricingMode.value = detail.default_pricing_mode

    const detailAttributes: CategoryAttributeTemplate[] = Array.isArray(detail.template_attributes)
      ? detail.template_attributes
      : []
    templateAttributes.value = detailAttributes.map((item) => ({
      key: rowKey++,
      attribute: item.attribute_id,
      is_variant_generating: item.is_variant_generating,
    }))

    const detailCharacteristics: CategoryCharacteristicTemplate[] = Array.isArray(detail.template_characteristics)
      ? detail.template_characteristics
      : []
    templateCharacteristics.value = detailCharacteristics.map((item) => ({
      key: rowKey++,
      name: item.name,
      default_value: item.default_value ?? '',
      sort_order: item.sort_order ?? 0,
    }))
  } catch (error: unknown) {
    toast.error(error instanceof Error ? error.message : 'Не удалось открыть категорию')
    formSheetOpen.value = false
  }
}

async function saveCategory(): Promise<void> {
  if (!formName.value.trim()) {
    toast.error('Укажите название категории')
    return
  }

  isSaving.value = true
  try {
    const payload = {
      name: formName.value.trim(),
      parent: formParent.value,
      default_pricing_mode: formPricingMode.value,
      sort_order: 0,
    }

    let categoryId = editingCategoryId.value
    if (categoryId === null) {
      const created = await createCategory(payload)
      categoryId = created.id
    } else {
      await updateCategory(categoryId, payload)
    }

    const attributePayload = templateAttributes.value
      .filter((row) => typeof row.attribute === 'number')
      .map((row) => ({
        attribute: row.attribute as number,
        is_variant_generating: row.is_variant_generating,
      }))
    await replaceCategoryAttributes(categoryId, attributePayload)

    const characteristicPayload = templateCharacteristics.value
      .map((row, index) => ({
        name: row.name.trim(),
        default_value: row.default_value.trim(),
        sort_order: index,
      }))
      .filter((row) => row.name.length > 0)
    await replaceCategoryCharacteristics(categoryId, characteristicPayload)

    await applyCategorySettings(categoryId, {
      apply_to_existing: applyToExisting.value,
      apply_pricing_mode: applyPricingMode.value,
      apply_characteristics: applyCharacteristics.value,
    })

    toast.success(editingCategoryId.value ? 'Категория обновлена' : 'Категория создана')
    formSheetOpen.value = false
    await loadCategories()
  } catch (error: unknown) {
    toast.error(error instanceof Error ? error.message : 'Не удалось сохранить категорию')
  } finally {
    isSaving.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadCategories(), loadAttributes()])
})
</script>

<template>
  <div class="categories-page">
    <header class="page-header">
      <button class="back-btn" type="button" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>
      <h1 class="page-title">Категории</h1>
      <button class="add-btn" type="button" aria-label="Добавить категорию" @click="openCreateSheet">
        <Plus :size="18" :stroke-width="2" />
      </button>
    </header>

    <main class="content">
      <div v-if="isLoading" class="loading-grid" aria-busy="true">
        <div class="skeleton-row" />
        <div class="skeleton-row" />
        <div class="skeleton-row" />
      </div>

      <div v-else-if="errorMessage" class="error-banner" role="alert">
        <AlertCircle :size="16" :stroke-width="1.75" />
        <span>{{ errorMessage }}</span>
        <button class="retry-btn" type="button" @click="loadCategories">Повторить</button>
      </div>

      <AppEmptyState
        v-else-if="orderedCategories.length === 0"
        title="Категорий пока нет"
        description="Создайте первую категорию для каталога"
        action-label="Создать категорию"
        @action="openCreateSheet"
      >
        <template #illustration>
          <div class="empty-illustration">
            <FolderTree :size="40" :stroke-width="1.5" />
          </div>
        </template>
      </AppEmptyState>

      <div v-else class="category-list">
        <article
          v-for="node in orderedCategories"
          :key="node.item.id"
          class="category-row"
          :style="{ paddingLeft: `calc(var(--space-3) + ${node.level} * 16px)` }"
          @click="openEditSheet(node.item.id)"
        >
          <div class="category-main">
            <div class="category-info">
              <span class="category-name">{{ node.item.name }}</span>
              <span class="category-meta">
                {{ node.item.products_count ?? 0 }} товаров · {{ node.item.default_pricing_mode }}
              </span>
            </div>
            <Pencil :size="16" :stroke-width="2" class="edit-icon" />
          </div>
        </article>
      </div>
    </main>

    <button class="fab" type="button" aria-label="Добавить категорию" @click="openCreateSheet">
      <Plus :size="24" :stroke-width="2.2" />
    </button>

    <AppBottomSheet
      :open="formSheetOpen"
      :title="editingCategoryId ? 'Редактирование категории' : 'Новая категория'"
      @close="formSheetOpen = false"
    >
      <form class="create-form" @submit.prevent="saveCategory">
        <BaseInput v-model="formName" label="Название *" placeholder="Например: Обувь" />

        <label class="field-label">Родительская категория</label>
        <BaseSelect
          v-model="formParent"
          :options="parentSelectOptions"
          title="Родительская категория"
          placeholder="Без родителя"
        />

        <label class="field-label">Ценовой режим категории</label>
        <BaseSelect
          v-model="formPricingMode"
          :options="pricingModeOptions"
          title="Ценовой режим"
          placeholder="Выберите режим"
        />

        <div class="template-block">
          <div class="template-header">
            <span class="field-label">Шаблонные атрибуты</span>
            <button class="tiny-action" type="button" @click="addTemplateAttribute">+ Атрибут</button>
          </div>
          <div v-if="templateAttributes.length === 0" class="template-empty">Атрибуты не заданы</div>
          <div v-for="row in templateAttributes" :key="row.key" class="template-row">
            <BaseSelect
              v-model="row.attribute"
              :options="attributeOptions"
              title="Атрибут"
              placeholder="Выберите атрибут"
            />
            <BaseSelect
              v-model="row.is_variant_generating"
              :options="boolOptions"
              title="Генерировать SKU"
              placeholder="Генерировать SKU"
            />
            <button class="tiny-remove" type="button" @click="removeTemplateAttribute(row.key)">Удалить</button>
          </div>
        </div>

        <div class="template-block">
          <div class="template-header">
            <span class="field-label">Шаблонные характеристики</span>
            <button class="tiny-action" type="button" @click="addTemplateCharacteristic">+ Характеристика</button>
          </div>
          <div v-if="templateCharacteristics.length === 0" class="template-empty">Характеристики не заданы</div>
          <div v-for="row in templateCharacteristics" :key="row.key" class="template-row">
            <BaseInput v-model="row.name" label="Название" placeholder="Материал" />
            <BaseInput v-model="row.default_value" label="Значение" placeholder="Кожа" />
            <button class="tiny-remove" type="button" @click="removeTemplateCharacteristic(row.key)">Удалить</button>
          </div>
        </div>

        <label class="field-label">Применение изменений</label>
        <BaseSelect
          v-model="applyToExisting"
          :options="applyModeOptions"
          title="Применение изменений"
          placeholder="Выберите режим"
        />
        <div v-if="applyToExisting" class="apply-block">
          <BaseSelect
            v-model="applyPricingMode"
            :options="boolOptions"
            title="Применить pricing mode"
            placeholder="Применить pricing mode"
          />
          <BaseSelect
            v-model="applyCharacteristics"
            :options="boolOptions"
            title="Применить характеристики"
            placeholder="Применить характеристики"
          />
        </div>

        <BaseButton
          type="submit"
          variant="primary"
          size="lg"
          :full-width="true"
          :loading="isSaving"
          :disabled="isSaving || !formName.trim()"
        >
          {{ editingCategoryId ? 'Сохранить' : 'Создать категорию' }}
        </BaseButton>
      </form>
    </AppBottomSheet>
  </div>
</template>

<style scoped>
.categories-page {
  min-height: 100%;
  background: var(--color-bg-primary);
}

.page-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: grid;
  grid-template-columns: 40px 1fr 40px;
  align-items: center;
  gap: var(--space-3);
  min-height: var(--header-height);
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-bg-primary);
}

.page-title {
  text-align: center;
  font-size: var(--text-lg);
  color: var(--color-text-primary);
  font-weight: var(--font-semibold);
}

.back-btn,
.add-btn {
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-primary);
  border-radius: var(--radius-md);
}

.content {
  padding: var(--space-4);
  padding-bottom: calc(var(--bottom-nav-height) + 88px);
}

.category-list {
  display: grid;
  gap: var(--space-2);
}

.category-row {
  min-height: 52px;
  border: 1px solid var(--color-border-subtle);
  background: var(--color-bg-elevated);
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  padding-right: var(--space-3);
}

.category-main {
  display: flex;
  flex: 1;
  justify-content: space-between;
  gap: var(--space-3);
  align-items: center;
}

.category-info {
  display: grid;
  gap: 2px;
}

.category-name {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.category-meta {
  font-size: 11px;
  color: var(--color-text-secondary);
}

.edit-icon {
  color: var(--color-text-secondary);
}

.fab {
  position: fixed;
  right: var(--space-4);
  bottom: calc(var(--bottom-nav-height) + var(--space-4) + env(safe-area-inset-bottom, 0px));
  width: 56px;
  height: 56px;
  border-radius: var(--radius-full);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-float);
  z-index: var(--z-float);
}

.create-form {
  display: grid;
  gap: var(--space-3);
}

.field-label {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  font-weight: var(--font-medium);
}

.template-block {
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  display: grid;
  gap: var(--space-2);
}

.template-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.template-empty {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.template-row {
  display: grid;
  gap: var(--space-2);
}

.tiny-action,
.tiny-remove {
  min-height: 32px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-elevated);
  color: var(--color-text-primary);
  padding: 0 var(--space-2);
  font-size: var(--text-xs);
}

.apply-block {
  display: grid;
  gap: var(--space-2);
}

.error-banner {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-error);
  background: var(--color-error-bg);
  color: var(--color-error);
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
}

.retry-btn {
  margin-left: auto;
  color: var(--color-text-primary);
  border: 1px solid var(--color-border-default);
  border-radius: var(--radius-sm);
  min-height: 30px;
  padding: 0 var(--space-2);
  background: var(--color-bg-elevated);
}

.loading-grid {
  display: grid;
  gap: var(--space-2);
}

.skeleton-row {
  height: 52px;
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

@keyframes shimmer {
  from { background-position: 0 0; }
  to { background-position: 200% 0; }
}
</style>
