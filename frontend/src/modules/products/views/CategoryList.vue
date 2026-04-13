<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, Plus, FolderTree, AlertCircle } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { fetchCategories } from '@/api/catalog'
import api from '@/api/client'
import type { Category } from '@/types/models'
import { PricingMode } from '@/types/enums'
import { useToast } from '@/composables/useToast'
import AppBottomSheet from '@/components/feedback/AppBottomSheet.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import BaseButton from '@/components/base/BaseButton.vue'
import AppEmptyState from '@/components/feedback/AppEmptyState.vue'

type CategoryRecord = Category & {
  parent?: number | null
  products_count?: number
}

interface CategoryNode {
  item: CategoryRecord
  level: number
}

const router = useRouter()
const toast = useToast()

const categories = ref<CategoryRecord[]>([])
const isLoading = ref(true)
const errorMessage = ref('')

const createSheetOpen = ref(false)
const createName = ref('')
const createParent = ref<number | null>(null)
const isCreating = ref(false)

function getParentId(category: CategoryRecord): number | null {
  if (typeof category.parent === 'number') return category.parent
  if ('parent_id' in category && typeof category.parent_id === 'number') return category.parent_id
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

  function walk(parentId: number | null, level: number) {
    const children = byParent.get(parentId) ?? []
    for (const child of children) {
      result.push({ item: child, level })
      walk(child.id, level + 1)
    }
  }

  walk(null, 0)
  return result
})

const parentOptions = computed(() =>
  categories.value.map((category) => ({
    id: category.id,
    name: category.name,
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

function openCreateSheet(): void {
  createName.value = ''
  createParent.value = null
  createSheetOpen.value = true
}

async function createCategory(): Promise<void> {
  if (!createName.value.trim()) return

  isCreating.value = true
  try {
    await api.post('/api/v1/catalog/categories/', {
      name: createName.value.trim(),
      parent: createParent.value,
      default_pricing_mode: PricingMode.DEFAULT_EDITABLE,
      sort_order: categories.value.length + 1,
    })
    toast.success('Категория создана')
    createSheetOpen.value = false
    await loadCategories()
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Не удалось создать категорию'
    toast.error(message)
  } finally {
    isCreating.value = false
  }
}

onMounted(loadCategories)
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
        >
          <div class="category-main">
            <span class="category-name">{{ node.item.name }}</span>
            <span class="category-count">{{ node.item.products_count ?? 0 }} товаров</span>
          </div>
        </article>
      </div>
    </main>

    <button class="fab" type="button" aria-label="Добавить категорию" @click="openCreateSheet">
      <Plus :size="24" :stroke-width="2.2" />
    </button>

    <AppBottomSheet :open="createSheetOpen" title="Новая категория" @close="createSheetOpen = false">
      <form class="create-form" @submit.prevent="createCategory">
        <BaseInput v-model="createName" label="Название *" placeholder="Например: Обувь" />

        <label class="field-label" for="parent-select">Родительская категория</label>
        <select id="parent-select" v-model="createParent" class="select-field">
          <option :value="null">Без родителя</option>
          <option v-for="option in parentOptions" :key="option.id" :value="option.id">
            {{ option.name }}
          </option>
        </select>

        <BaseButton
          type="submit"
          variant="primary"
          size="lg"
          :full-width="true"
          :loading="isCreating"
          :disabled="isCreating || !createName.trim()"
        >
          Создать категорию
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

.category-name {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.category-count {
  font-size: var(--text-xs);
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

.select-field {
  width: 100%;
  min-height: 44px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-elevated);
  padding: 0 var(--space-3);
  color: var(--color-text-primary);
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

.empty-illustration {
  width: 72px;
  height: 72px;
  border-radius: var(--radius-full);
  background: var(--color-brand-50);
  color: var(--color-brand-500);
  display: flex;
  align-items: center;
  justify-content: center;
}

@keyframes shimmer {
  from { background-position: 0 0; }
  to { background-position: 200% 0; }
}
</style>
