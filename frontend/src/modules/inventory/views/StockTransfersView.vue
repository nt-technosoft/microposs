<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, ArrowRightLeft, Package2, RefreshCw } from 'lucide-vue-next'
import { fetchLocations, fetchLots, fetchStockMovements, transferStock } from '@/api/inventory'
import type { Location, Lot, StockMovement } from '@/types/models'
import BaseSelect from '@/components/base/BaseSelect.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import AppEmptyState from '@/components/feedback/AppEmptyState.vue'
import { useToast } from '@/composables/useToast'
import { getApiErrorMessage } from '@/utils/errors'

const router = useRouter()
const toast = useToast()

const isLoading = ref(true)
const isSubmitting = ref(false)
const isLoadingLots = ref(false)
const locations = ref<Location[]>([])
const lots = ref<Lot[]>([])
const recentTransfers = ref<StockMovement[]>([])
const formError = ref('')
const loadError = ref('')

const form = ref({
  fromWarehouseId: null as number | null,
  toWarehouseId: null as number | null,
  lotId: null as number | null,
  quantity: '1',
})

const activeLocations = computed(() =>
  locations.value.filter((location) => location.is_active),
)

const sourceOptions = computed(() =>
  activeLocations.value.map((location) => ({
    value: location.id,
    label: `${location.name} · ${location.kind === 'storage' ? 'Склад' : 'Магазин'}`,
  })),
)

const destinationOptions = computed(() =>
  activeLocations.value
    .filter((location) => location.id !== form.value.fromWarehouseId)
    .map((location) => ({
      value: location.id,
      label: `${location.name} · ${location.kind === 'storage' ? 'Склад' : 'Магазин'}`,
    })),
)

function lotAvailableQuantity(lot: Lot): number {
  const stock = lot.stocks?.find((entry) => entry.warehouse === form.value.fromWarehouseId)
  return stock?.quantity_remaining ?? 0
}

function lotLabel(lot: Lot): string {
  return `${lot.product_variant_name || `Лот #${lot.id}`} · ${lotAvailableQuantity(lot)} шт`
}

const lotOptions = computed(() =>
  lots.value.map((lot) => ({
    value: lot.id,
    label: lotLabel(lot),
  })),
)

const selectedLot = computed(() =>
  lots.value.find((lot) => lot.id === form.value.lotId) ?? null,
)

const selectedLotAvailable = computed(() =>
  selectedLot.value ? lotAvailableQuantity(selectedLot.value) : 0,
)

const canSubmit = computed(() => {
  const quantity = Number(form.value.quantity)
  return (
    !!form.value.fromWarehouseId
    && !!form.value.toWarehouseId
    && !!form.value.lotId
    && Number.isFinite(quantity)
    && quantity > 0
    && quantity <= selectedLotAvailable.value
  )
})

const transferCandidatesEmpty = computed(() =>
  !isLoading.value
  && !loadError.value
  && !!form.value.fromWarehouseId
  && !isLoadingLots.value
  && lots.value.length === 0,
)

function formatDate(date: string): string {
  return new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(date))
}

async function loadLocationsAndMovements(): Promise<void> {
  isLoading.value = true
  loadError.value = ''
  try {
    const [loadedLocations, movementsResponse] = await Promise.all([
      fetchLocations(),
      fetchStockMovements({ page: 1 }),
    ])
    locations.value = loadedLocations
    recentTransfers.value = movementsResponse.results.filter((movement) => (
      movement.movement_type === 'TRANSFER' || movement.reference_type === 'transfer'
    )).slice(0, 6)

    if (!form.value.fromWarehouseId) {
      const defaultSource = loadedLocations.find((location) => location.kind === 'storage') ?? loadedLocations[0]
      form.value.fromWarehouseId = defaultSource?.id ?? null
    }

    if (!form.value.toWarehouseId) {
      const defaultDestination = loadedLocations.find((location) => (
        location.kind === 'shop' && location.id !== form.value.fromWarehouseId
      )) ?? loadedLocations.find((location) => location.id !== form.value.fromWarehouseId)
      form.value.toWarehouseId = defaultDestination?.id ?? null
    }
  } catch (error: unknown) {
    loadError.value = getApiErrorMessage(error, 'Не удалось загрузить перемещения')
  } finally {
    isLoading.value = false
  }
}

async function loadLotsForSource(): Promise<void> {
  if (!form.value.fromWarehouseId) {
    lots.value = []
    form.value.lotId = null
    return
  }

  isLoadingLots.value = true
  formError.value = ''
  try {
    const response = await fetchLots({
      warehouse: form.value.fromWarehouseId,
      active: true,
      page: 1,
    })
    lots.value = response.results.filter((lot) => lotAvailableQuantity(lot) > 0)
    if (!lots.value.some((lot) => lot.id === form.value.lotId)) {
      form.value.lotId = lots.value[0]?.id ?? null
    }
  } catch (error: unknown) {
    formError.value = getApiErrorMessage(error, 'Не удалось загрузить доступные партии')
    lots.value = []
    form.value.lotId = null
  } finally {
    isLoadingLots.value = false
  }
}

async function submitTransfer(): Promise<void> {
  if (!canSubmit.value || isSubmitting.value) return

  isSubmitting.value = true
  formError.value = ''
  try {
    await transferStock({
      lot_id: Number(form.value.lotId),
      from_warehouse_id: Number(form.value.fromWarehouseId),
      to_warehouse_id: Number(form.value.toWarehouseId),
      quantity: Number(form.value.quantity),
    })
    toast.success('Перемещение проведено')
    form.value.quantity = '1'
    await Promise.all([loadLotsForSource(), loadLocationsAndMovements()])
  } catch (error: unknown) {
    formError.value = getApiErrorMessage(error, 'Не удалось провести перемещение')
  } finally {
    isSubmitting.value = false
  }
}

function swapWarehouses(): void {
  const nextSource = form.value.toWarehouseId
  form.value.toWarehouseId = form.value.fromWarehouseId
  form.value.fromWarehouseId = nextSource
}

function goBack(): void {
  router.back()
}

watch(() => form.value.fromWarehouseId, async (nextSource, previousSource) => {
  if (!nextSource) {
    lots.value = []
    form.value.lotId = null
    return
  }

  if (nextSource === form.value.toWarehouseId) {
    const fallbackDestination = activeLocations.value.find((location) => location.id !== nextSource)
    form.value.toWarehouseId = fallbackDestination?.id ?? null
  }

  if (nextSource !== previousSource) {
    await loadLotsForSource()
  }
}, { immediate: false })

watch(() => form.value.toWarehouseId, (nextDestination) => {
  if (nextDestination && nextDestination === form.value.fromWarehouseId) {
    const fallbackSource = activeLocations.value.find((location) => location.id !== nextDestination)
    form.value.fromWarehouseId = fallbackSource?.id ?? null
  }
})

onMounted(async () => {
  await loadLocationsAndMovements()
  await loadLotsForSource()
})
</script>

<template>
  <div class="transfer-page">
    <header class="page-header">
      <button class="back-btn" type="button" aria-label="Назад" @click="goBack">
        <ArrowLeft :size="20" :stroke-width="2" />
      </button>
      <div class="page-headings">
        <h1 class="page-title">Перемещение</h1>
        <p class="page-subtitle">Перенос товара со склада в магазин и обратно.</p>
      </div>
    </header>

    <div class="content">
      <section class="panel">
        <div class="section-title-row">
          <h2 class="section-title">Новая операция</h2>
          <button class="ghost-refresh" type="button" @click="loadLocationsAndMovements">
            <RefreshCw :size="16" :stroke-width="2" />
          </button>
        </div>

        <div v-if="loadError" class="error-banner">{{ loadError }}</div>

        <div v-else class="form-grid">
          <BaseSelect
            v-model="form.fromWarehouseId"
            :options="sourceOptions"
            title="Откуда перемещаем"
            placeholder="Выбери точку отправления"
          />

          <div class="swap-row">
            <button class="swap-btn" type="button" @click="swapWarehouses">
              <ArrowRightLeft :size="18" :stroke-width="2" />
            </button>
          </div>

          <BaseSelect
            v-model="form.toWarehouseId"
            :options="destinationOptions"
            title="Куда перемещаем"
            placeholder="Выбери точку назначения"
          />

          <BaseSelect
            v-model="form.lotId"
            :options="lotOptions"
            title="Какая партия"
            placeholder="Выбери товар для перемещения"
            :disabled="isLoadingLots || lotOptions.length === 0"
          />

          <BaseInput
            v-model="form.quantity"
            label="Количество"
            type="number"
            placeholder="Например, 10"
          />

          <p v-if="selectedLot" class="helper-text">
            Доступно к перемещению: <strong>{{ selectedLotAvailable }}</strong>
          </p>

          <div v-if="formError" class="inline-error">{{ formError }}</div>

          <button
            class="primary-btn"
            type="button"
            :disabled="!canSubmit || isSubmitting"
            @click="submitTransfer"
          >
            {{ isSubmitting ? 'Сохраняем...' : 'Провести перемещение' }}
          </button>
        </div>

        <AppEmptyState
          v-if="transferCandidatesEmpty"
          title="Нет доступных партий"
          description="На выбранной точке сейчас нечего перемещать."
        >
          <template #illustration>
            <div class="empty-icon">
              <Package2 :size="34" :stroke-width="1.5" />
            </div>
          </template>
        </AppEmptyState>
      </section>

      <section class="panel">
        <h2 class="section-title">Последние перемещения</h2>
        <div v-if="recentTransfers.length === 0" class="history-empty">
          Перемещений пока нет.
        </div>
        <ul v-else class="history-list">
          <li v-for="movement in recentTransfers" :key="movement.id" class="history-item">
            <div class="history-main">
              <span class="history-route">
                {{ movement.from_location_name || 'Источник' }} → {{ movement.to_location_name || 'Назначение' }}
              </span>
              <strong class="history-qty">{{ movement.quantity }} шт</strong>
            </div>
            <div class="history-sub">
              Лот #{{ movement.lot }} · {{ formatDate(movement.created_at) }}
            </div>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>

<style scoped>
.transfer-page {
  min-height: 100dvh;
  background: var(--color-bg-primary);
}

.page-header {
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  padding: var(--space-4);
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-bg-primary);
}

.back-btn {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-elevated);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-primary);
  flex-shrink: 0;
}

.page-headings {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.page-title {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--color-text-primary);
}

.page-subtitle {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.content {
  display: grid;
  gap: var(--space-4);
  padding: var(--space-4);
  padding-bottom: calc(var(--bottom-nav-height) + var(--space-8));
}

.panel {
  display: grid;
  gap: var(--space-4);
  padding: var(--space-4);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-xl);
  background: var(--color-bg-elevated);
}

.section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.section-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.ghost-refresh {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.form-grid {
  display: grid;
  gap: var(--space-3);
}

.swap-row {
  display: flex;
  justify-content: center;
  margin-top: calc(var(--space-1) * -1);
  margin-bottom: calc(var(--space-1) * -1);
}

.swap-btn {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-secondary);
  color: var(--color-brand-600);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.helper-text {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  margin-top: calc(var(--space-2) * -1);
}

.inline-error,
.error-banner {
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-lg);
  background: var(--color-error-bg);
  color: var(--color-error);
  font-size: var(--text-sm);
}

.primary-btn {
  min-height: 48px;
  border-radius: var(--radius-lg);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
}

.primary-btn:disabled {
  opacity: 0.5;
}

.empty-icon {
  width: 68px;
  height: 68px;
  border-radius: var(--radius-full);
  background: var(--color-bg-secondary);
  color: var(--color-brand-500);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.history-empty {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.history-list {
  display: grid;
  gap: var(--space-2);
}

.history-item {
  display: grid;
  gap: 4px;
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-lg);
  background: var(--color-bg-secondary);
}

.history-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.history-route {
  font-size: var(--text-sm);
  color: var(--color-text-primary);
}

.history-qty {
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  white-space: nowrap;
}

.history-sub {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}
</style>
