<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, ArrowRightLeft, ChevronDown, Package2, RefreshCw } from 'lucide-vue-next'
import { fetchLocations, fetchLots, fetchStockMovements, transferStock } from '@/api/inventory'
import type { Location, Lot, StockMovement } from '@/types/models'
import BaseSelect from '@/components/base/BaseSelect.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import AppEmptyState from '@/components/feedback/AppEmptyState.vue'
import { useToast } from '@/composables/useToast'
import { intlLocale } from '@/i18n/format'
import { getApiErrorMessage } from '@/utils/errors'
import PageChrome from '@/components/layout/PageChrome.vue'

const router = useRouter()
const toast = useToast()
const { t, locale } = useI18n()

const isLoading = ref(true)
const isSubmitting = ref(false)
const isLoadingLots = ref(false)
const isLoadingMoreTransfers = ref(false)
const locations = ref<Location[]>([])
const lots = ref<Lot[]>([])
const recentTransfers = ref<StockMovement[]>([])
const transferPage = ref(1)
const transferTotal = ref(0)
const expandedTransferId = ref<number | null>(null)
const formError = ref('')
const loadError = ref('')

const TRANSFER_PAGE_SIZE = 6

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
    label: `${location.name} · ${location.kind === 'storage' ? t('inventory.warehouse') : t('inventory.shop')}`,
  })),
)

const destinationOptions = computed(() =>
  activeLocations.value
    .filter((location) => location.id !== form.value.fromWarehouseId)
    .map((location) => ({
      value: location.id,
      label: `${location.name} · ${location.kind === 'storage' ? t('inventory.warehouse') : t('inventory.shop')}`,
    })),
)

const selectedSource = computed(() =>
  activeLocations.value.find((location) => location.id === form.value.fromWarehouseId) ?? null,
)

const selectedDestination = computed(() =>
  activeLocations.value.find((location) => location.id === form.value.toWarehouseId) ?? null,
)

const directionLabel = computed(() => {
  const sourceKind = selectedSource.value?.kind
  const destinationKind = selectedDestination.value?.kind
  if (sourceKind === 'storage' && destinationKind === 'shop') return t('inventory.fromWarehouseToShop')
  if (sourceKind === 'shop' && destinationKind === 'storage') return t('inventory.fromShopToWarehouse')
  return t('inventory.betweenLocations')
})

function lotAvailableQuantity(lot: Lot): number {
  const stock = lot.stocks?.find((entry) => entry.warehouse === form.value.fromWarehouseId)
  return stock?.quantity_remaining ?? 0
}

function lotLabel(lot: Lot): string {
  return `${lot.product_variant_name || t('inventory.lotFallback', { id: lot.id })} · ${lotAvailableQuantity(lot)} ${t('common.pieces')}`
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

const hasMoreTransfers = computed(() => recentTransfers.value.length < transferTotal.value)

function formatDate(date: string): string {
  return new Intl.DateTimeFormat(intlLocale(locale.value), {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(date))
}

function formatFullDate(date: string): string {
  return new Intl.DateTimeFormat(intlLocale(locale.value), {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(date))
}

function movementTitle(movement: StockMovement): string {
  return movement.lot_product_name || t('inventory.batchSource', { id: movement.lot })
}

function movementSource(movement: StockMovement): string {
  if (movement.lot_procurement_id) return t('inventory.procurementSource', { id: movement.lot_procurement_id })
  if (movement.lot_receipt_id) return t('inventory.documentSource', { id: movement.lot_receipt_id })
  return t('inventory.batchSource', { id: movement.lot })
}

function toggleTransferDetails(id: number): void {
  expandedTransferId.value = expandedTransferId.value === id ? null : id
}

async function loadTransferHistory({ reset = false } = {}): Promise<void> {
  const nextPage = reset ? 1 : transferPage.value + 1
  if (!reset) isLoadingMoreTransfers.value = true
  try {
    const response = await fetchStockMovements({
      movement_type: 'transfer',
      page: nextPage,
      page_size: TRANSFER_PAGE_SIZE,
    })
    recentTransfers.value = reset
      ? response.results
      : [...recentTransfers.value, ...response.results]
    transferTotal.value = response.count
    transferPage.value = nextPage
  } catch (error: unknown) {
    const message = getApiErrorMessage(error, t('inventory.loadHistoryFailed'))
    if (reset) loadError.value = message
    else toast.error(message)
  } finally {
    isLoadingMoreTransfers.value = false
  }
}

async function loadLocationsAndMovements(): Promise<void> {
  isLoading.value = true
  loadError.value = ''
  try {
    const [loadedLocations, movementsResponse] = await Promise.all([
      fetchLocations(),
      fetchStockMovements({ movement_type: 'transfer', page: 1, page_size: TRANSFER_PAGE_SIZE }),
    ])
    locations.value = loadedLocations
    recentTransfers.value = movementsResponse.results
    transferTotal.value = movementsResponse.count
    transferPage.value = 1
    expandedTransferId.value = null

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
    loadError.value = getApiErrorMessage(error, t('inventory.loadTransfersFailed'))
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
    formError.value = getApiErrorMessage(error, t('inventory.loadLotsFailed'))
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
    toast.success(t('inventory.transferDone'))
    form.value.quantity = '1'
    await Promise.all([loadLotsForSource(), loadLocationsAndMovements()])
  } catch (error: unknown) {
    formError.value = getApiErrorMessage(error, t('inventory.submitFailed'))
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
    <PageChrome
      :title="t('inventory.transferTitle')"
      :eyebrow="t('nav.products')"
      :description="t('inventory.transferSubtitle')"
    >
      <template #primary>
        <button class="back-btn" type="button" :aria-label="t('common.back')" @click="goBack">
          <ArrowLeft :size="20" :stroke-width="2" />
        </button>
      </template>
    </PageChrome>

    <div class="content">
      <section class="panel">
        <div class="section-title-row">
          <h2 class="section-title">{{ t('inventory.newOperation') }}</h2>
          <button class="ghost-refresh" type="button" @click="loadLocationsAndMovements">
            <RefreshCw :size="16" :stroke-width="2" />
          </button>
        </div>

        <div v-if="loadError" class="error-banner">{{ loadError }}</div>

        <div v-else class="form-grid">
          <div class="direction-strip">
            <ArrowRightLeft :size="16" :stroke-width="2" />
            <span>{{ directionLabel }}</span>
          </div>

          <BaseSelect
            v-model="form.fromWarehouseId"
            :options="sourceOptions"
            :title="t('inventory.source')"
            :placeholder="t('inventory.chooseSource')"
          />

          <div class="swap-row">
            <button class="swap-btn" type="button" @click="swapWarehouses">
              <ArrowRightLeft :size="18" :stroke-width="2" />
            </button>
          </div>

          <BaseSelect
            v-model="form.toWarehouseId"
            :options="destinationOptions"
            :title="t('inventory.destination')"
            :placeholder="t('inventory.chooseDestination')"
          />

          <BaseSelect
            v-model="form.lotId"
            :options="lotOptions"
            :title="t('inventory.batch')"
            :placeholder="t('inventory.chooseLot')"
            :disabled="isLoadingLots || lotOptions.length === 0"
          />

          <BaseInput
            v-model="form.quantity"
            :label="t('common.quantity')"
            type="number"
            :placeholder="t('inventory.quantityExample')"
          />

          <p v-if="selectedLot" class="helper-text">
            {{ t('inventory.availableToMove', { count: selectedLotAvailable }) }}
          </p>

          <div v-if="formError" class="inline-error">{{ formError }}</div>

          <button
            class="primary-btn"
            type="button"
            :disabled="!canSubmit || isSubmitting"
            @click="submitTransfer"
          >
            {{ isSubmitting ? t('inventory.transferSubmitting') : t('inventory.transferSubmit') }}
          </button>
        </div>

        <AppEmptyState
          v-if="transferCandidatesEmpty"
          :title="t('inventory.noLotsTitle')"
          :description="t('inventory.noLotsDescription')"
        >
          <template #illustration>
            <div class="empty-icon">
              <Package2 :size="34" :stroke-width="1.5" />
            </div>
          </template>
        </AppEmptyState>
      </section>

      <section class="panel">
        <div class="section-title-row">
          <div class="section-heading">
            <h2 class="section-title">{{ t('inventory.historyTitle') }}</h2>
            <p v-if="transferTotal > 0" class="section-meta">
              {{ t('inventory.shownOf', { shown: recentTransfers.length, total: transferTotal }) }}
            </p>
          </div>
          <button class="ghost-refresh" type="button" @click="loadTransferHistory({ reset: true })">
            <RefreshCw :size="16" :stroke-width="2" />
          </button>
        </div>
        <div v-if="recentTransfers.length === 0" class="history-empty">
          {{ t('inventory.noTransfers') }}
        </div>
        <ul v-else class="history-list">
          <li
            v-for="movement in recentTransfers"
            :key="movement.id"
            class="history-item"
          >
            <button
              class="history-toggle"
              type="button"
              :aria-expanded="expandedTransferId === movement.id"
              @click="toggleTransferDetails(movement.id)"
            >
              <div class="history-main">
                <span class="history-product">{{ movementTitle(movement) }}</span>
                <strong class="history-qty">{{ movement.quantity }} {{ t('common.pieces') }}</strong>
              </div>
              <div class="history-sub">
                <span>{{ movement.from_location_name || t('inventory.source') }} → {{ movement.to_location_name || t('inventory.destination') }}</span>
                <ChevronDown class="history-chevron" :size="16" :stroke-width="2" />
              </div>
            </button>

            <div v-if="expandedTransferId === movement.id" class="history-details">
              <div class="detail-row">
                <span>{{ t('inventory.batchOrigin') }}</span>
                <strong>{{ movementSource(movement) }}</strong>
              </div>
              <div class="detail-row">
                <span>{{ t('common.date') }}</span>
                <strong>{{ formatFullDate(movement.created_at) }}</strong>
              </div>
              <div v-if="movement.lot_landed_cost_per_unit" class="detail-row">
                <span>{{ t('reports.cogs') }}</span>
                <strong>{{ t('inventory.costPerUnit', { amount: movement.lot_landed_cost_per_unit }) }}</strong>
              </div>
            </div>
          </li>
        </ul>
        <button
          v-if="hasMoreTransfers"
          class="secondary-btn"
          type="button"
          :disabled="isLoadingMoreTransfers"
          @click="loadTransferHistory()"
        >
          {{ isLoadingMoreTransfers ? t('common.loadingMore') : t('common.loadMore') }}
        </button>
      </section>
    </div>
  </div>
</template>

<style scoped>
.transfer-page {
  min-height: 100dvh;
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

.content {
  display: grid;
  gap: var(--space-4);
  padding: var(--space-4);
  padding-bottom: calc(var(--bottom-nav-height) + var(--space-8));
}

@media (min-width: 768px) {
  .content { max-width:1120px; margin:0 auto; grid-template-columns:minmax(0, 1fr) minmax(320px, .8fr); padding:var(--space-6); padding-bottom:var(--space-8); }
}

@media (min-width: 1280px) {
  .transfer-page { background: transparent; }
  .content { max-width:none; margin:0; padding-inline:var(--space-8); }
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

.section-heading {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.section-title {
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.section-meta {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
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

.direction-strip {
  min-height: 36px;
  padding: 0 var(--space-3);
  border-radius: var(--radius-md);
  background: var(--color-brand-50);
  color: var(--color-brand-700);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
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

.secondary-btn {
  min-height: 44px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-primary);
  color: var(--color-brand-700);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.secondary-btn:disabled {
  opacity: 0.55;
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
  overflow: hidden;
  border-radius: var(--radius-lg);
  background: var(--color-bg-secondary);
}

.history-toggle {
  display: grid;
  gap: 6px;
  width: 100%;
  padding: var(--space-3) var(--space-4);
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
}

.history-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.history-product {
  min-width: 0;
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-qty {
  font-size: var(--text-sm);
  color: var(--color-text-primary);
  white-space: nowrap;
}

.history-sub {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.history-sub span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-chevron {
  flex-shrink: 0;
  color: var(--color-text-tertiary);
  transition: transform 160ms ease;
}

.history-toggle[aria-expanded='true'] .history-chevron {
  transform: rotate(180deg);
}

.history-details {
  display: grid;
  gap: var(--space-2);
  padding: 0 var(--space-4) var(--space-3);
  border-top: 1px solid var(--color-border-subtle);
}

.detail-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding-top: var(--space-2);
  font-size: var(--text-xs);
}

.detail-row span {
  color: var(--color-text-secondary);
}

.detail-row strong {
  color: var(--color-text-primary);
  font-weight: var(--font-semibold);
  text-align: right;
}
</style>
