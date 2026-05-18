<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Handshake, RefreshCcw, RotateCcw, PackageOpen } from 'lucide-vue-next'
import { useToast } from '@/composables/useToast'
import { formatPrice } from '@/utils/currency'
import { ProcurementStatus, ProcurementType } from '@/types/enums'
import { fetchProcurementWorkspaces, type ProcurementWorkspacePayload } from '@/api/partnerships'
import ProcurementSectionShell from '@/modules/intake/components/ProcurementSectionShell.vue'
import { intlLocale } from '@/i18n/format'
import { procurementStatusMeta, procurementTypeMeta, type LabelMeta } from '@/utils/domainLabels'

// ── Router & composables ────────────────────────────────────────────────────

const router = useRouter()
const toast = useToast()
const { t, locale } = useI18n()

// ── State ───────────────────────────────────────────────────────────────────

type StatusFilter = 'all' | ProcurementStatus

interface FilterChip {
  value: StatusFilter
  label: string
}

const FILTER_CHIPS = computed<FilterChip[]>(() => [
  { value: 'all', label: t('common.all') },
  { value: ProcurementStatus.OPEN, label: t('domain.procurementStatus.OPEN') },
  { value: ProcurementStatus.PARTIALLY_RECEIVED, label: t('domain.procurementStatus.PARTIALLY_RECEIVED') },
  { value: ProcurementStatus.RECEIVED, label: t('domain.procurementStatus.RECEIVED') },
  { value: ProcurementStatus.CLOSED, label: t('domain.procurementStatus.CLOSED') },
])

const procurements = ref<ProcurementWorkspacePayload[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)
const activeFilter = ref<StatusFilter>('all')

// ── API ──────────────────────────────────────────────────────────────────────

async function loadProcurementList(): Promise<void> {
  isLoading.value = true
  error.value = null

  try {
    const params: Record<string, string> = {}
    if (activeFilter.value !== 'all') {
      params.status = activeFilter.value
    }

    procurements.value = await fetchProcurementWorkspaces(params)
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : t('procurements.loadFailed')
    error.value = message
    toast.error(message)
  } finally {
    isLoading.value = false
  }
}

onMounted(loadProcurementList)

// ── Computed ─────────────────────────────────────────────────────────────────

const filteredProcurements = computed<ProcurementWorkspacePayload[]>(() => {
  if (activeFilter.value === 'all') return procurements.value
  return procurements.value.filter((item) => item.status === activeFilter.value)
})

function getTypeMeta(type: ProcurementType): LabelMeta {
  return procurementTypeMeta[type] ?? { label: type, colorClass: 'badge-type--blue' }
}

function getStatusMeta(status: ProcurementStatus) {
  return procurementStatusMeta[status] ?? { label: status, colorClass: 'badge-status--gray' }
}

// ── Formatting ───────────────────────────────────────────────────────────────

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString(intlLocale(locale.value), {
    day: 'numeric',
    month: 'short',
  })
}

function totalCost(totalAmount: string): string {
  const total = parseFloat(totalAmount || '0')
  return formatPrice(Number.isNaN(total) ? 0 : total)
}

function linesLabel(countRaw: number): string {
  const count = Number.isFinite(countRaw) ? countRaw : 0
  return t('procurements.lineCount', { count })
}

// ── Navigation ───────────────────────────────────────────────────────────────

function goToDetail(id: number): void {
  router.push({ name: 'procurement-detail', params: { id } })
}

function goToCreate(): void {
  router.push({ name: 'procurement-create' })
}

function goToPartnershipCreate(): void {
  router.push({ name: 'procurement-create', query: { mode: 'partnership' } })
}

function onFilterChange(value: StatusFilter): void {
  activeFilter.value = value
  loadProcurementList()
}
</script>

<template>
  <ProcurementSectionShell
    active-mode="procurements"
    :title="t('procurements.title')"
    :primary-label="t('procurements.new')"
    :primary-aria-label="t('procurements.newProcurementAria')"
    @primary="goToCreate"
  >
    <template #header-actions>
      <button class="partnership-btn" type="button" aria-label="Создать партнёрский приход" @click="goToPartnershipCreate">
        <Handshake :size="16" :stroke-width="1.9" />
        <span>Партнёрский</span>
      </button>
      <button class="icon-btn" type="button" :aria-label="t('procurements.refreshProcurements')" @click="loadProcurementList">
        <RefreshCcw :size="17" />
      </button>
    </template>

    <template #summary>
      <div class="filter-row" role="group" :aria-label="t('procurements.statusFilter')">
        <button
          v-for="chip in FILTER_CHIPS"
          :key="chip.value"
          class="filter-chip"
          :class="{ active: activeFilter === chip.value }"
          @click="onFilterChange(chip.value)"
        >
          {{ chip.label }}
        </button>
      </div>
    </template>

    <div class="content">
      <template v-if="isLoading && filteredProcurements.length === 0">
        <div v-for="n in 4" :key="n" class="skeleton-card" />
      </template>

      <div v-else-if="error && filteredProcurements.length === 0" class="state-box state-error">
        <RotateCcw :size="28" :stroke-width="1.5" class="state-icon" />
        <p class="state-title">{{ t('procurements.loadingError') }}</p>
        <p class="state-body">{{ error }}</p>
        <button class="btn-retry" @click="loadProcurementList">{{ t('common.retry') }}</button>
      </div>

      <div v-else-if="!isLoading && filteredProcurements.length === 0" class="state-box">
        <PackageOpen :size="40" :stroke-width="1.25" class="state-icon-empty" />
        <p class="state-title">{{ t('procurements.noProcurements') }}</p>
        <p class="state-body">
          {{ activeFilter === 'all'
            ? t('procurements.createFirstProcurement')
            : t('procurements.noProcurementsByStatus') }}
        </p>
        <button v-if="activeFilter === 'all'" class="btn-retry" @click="goToCreate">
          {{ t('procurements.createProcurement') }}
        </button>
      </div>

      <template v-else>
        <button
          v-for="procurement in filteredProcurements"
          :key="procurement.id"
          class="receipt-card"
          @click="goToDetail(procurement.id)"
        >
          <div class="card-top">
            <div class="card-id-row">
              <span class="card-id">#{{ procurement.id }}</span>
              <span class="card-date">{{ formatDate(procurement.documents.procurement.opened_at) }}</span>
            </div>
            <span class="badge-type" :class="getTypeMeta(procurement.policy.funding_source as ProcurementType).colorClass">
              {{ getTypeMeta(procurement.policy.funding_source as ProcurementType).label }}
            </span>
          </div>

          <div class="card-main">
            <div class="card-value">
              <span class="card-total tabular-nums">{{ totalCost(procurement.summaries.items_total_uzs) }}</span>
            </div>
            <div class="card-meta-line">
              <span class="card-trace">
                {{ linesLabel(procurement.documents.items.length) }}
                <template v-if="procurement.documents.procurement.supplier_name">
                  · {{ procurement.documents.procurement.supplier_name }}
                </template>
              </span>
              <span
                class="badge-status"
                :class="getStatusMeta(procurement.status as ProcurementStatus).colorClass"
              >
                {{ getStatusMeta(procurement.status as ProcurementStatus).label }}
              </span>
            </div>
          </div>
        </button>
      </template>
    </div>
  </ProcurementSectionShell>
</template>

<style scoped>
.icon-btn {
  width: 38px;
  height: 38px;
  display: inline-grid;
  place-items: center;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-full);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  flex-shrink: 0;
}

.partnership-btn {
  min-height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 var(--space-3);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-full);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  white-space: nowrap;
}

.filter-row {
  display: flex;
  gap: var(--space-2);
  overflow-x: auto;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
}

.filter-row::-webkit-scrollbar {
  display: none;
}

.filter-chip {
  flex-shrink: 0;
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  border: 1px solid transparent;
  transition: background var(--duration-fast) var(--ease-out),
              color var(--duration-fast) var(--ease-out),
              border-color var(--duration-fast) var(--ease-out);
}

.filter-chip.active {
  background: var(--color-brand-50);
  color: var(--color-brand-600);
  border-color: var(--color-brand-200);
}

.filter-chip:active {
  transform: scale(0.96);
}

.content {
  display: grid;
  gap: var(--space-2);
}

.receipt-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  padding: var(--space-4);
  background: var(--color-bg-elevated);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-subtle);
  box-shadow: var(--shadow-sm);
  text-align: left;
  width: 100%;
  cursor: pointer;
  transition: box-shadow var(--duration-fast) var(--ease-out),
              border-color var(--duration-fast) var(--ease-out),
              transform var(--duration-fast) var(--ease-out);
}

.receipt-card:hover {
  border-color: var(--color-border-default);
  box-shadow: var(--shadow-md);
}

.receipt-card:active {
  transform: scale(0.985);
}

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.card-id-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.card-id {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  font-family: var(--font-mono);
}

.card-date {
  font-size: var(--text-sm);
  color: var(--color-text-tertiary);
}

.card-main {
  display: grid;
  gap: 10px;
}

.card-value { display: grid; gap: 0; }

.card-total {
  font-size: var(--text-xl);
  font-weight: var(--font-bold);
  color: var(--color-text-primary);
  line-height: 1.15;
}

.card-trace { font-size: var(--text-sm); color: var(--color-text-secondary); line-height: var(--leading-snug); }

.card-meta-line {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-3);
}

/* ── Type badges ────────────────────────────────────────────────────────── */

.badge-type {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  white-space: nowrap;
  flex-shrink: 0;
}

.badge-type--teal {
  background: var(--color-brand-50);
  color: var(--color-brand-600);
}

.badge-type--purple {
  background: #F3E8FF;
  color: #7C3AED;
}

.badge-type--indigo {
  background: #EEF2FF;
  color: #4338CA;
}

.badge-type--blue {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.badge-type--orange {
  background: #FFF7ED;
  color: #C2410C;
}

/* ── Status badges ──────────────────────────────────────────────────────── */

.badge-status {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--space-2);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  white-space: nowrap;
  flex-shrink: 0;
}

.badge-status--gray {
  background: var(--color-bg-sunken);
  color: var(--color-text-secondary);
}

.badge-status--green {
  background: var(--color-success-bg);
  color: var(--color-success);
}

.badge-status--blue {
  background: var(--color-info-bg);
  color: var(--color-info);
}

.badge-status--orange {
  background: #FFF7ED;
  color: #C2410C;
}

/* ── State boxes ────────────────────────────────────────────────────────── */

.state-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  padding: var(--space-16) var(--space-6);
  text-align: center;
}

.state-icon {
  color: var(--color-error);
  margin-bottom: var(--space-2);
}

.state-icon-empty {
  color: var(--color-text-tertiary);
  margin-bottom: var(--space-2);
}

.state-title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.state-body {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.btn-retry {
  margin-top: var(--space-4);
  padding: var(--space-2) var(--space-5);
  border-radius: var(--radius-full);
  background: var(--color-brand-500);
  color: var(--color-text-inverse);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  transition: background var(--duration-fast) var(--ease-out);
}

.btn-retry:hover {
  background: var(--color-brand-600);
}

/* ── Skeleton ───────────────────────────────────────────────────────────── */

.skeleton-card {
  height: 88px;
  border-radius: var(--radius-lg);
  background: var(--color-bg-sunken);
  animation: shimmer 1.4s ease-in-out infinite;
}

.skeleton-card:nth-child(2) { animation-delay: 0.1s; }
.skeleton-card:nth-child(3) { animation-delay: 0.2s; }
.skeleton-card:nth-child(4) { animation-delay: 0.3s; }

@keyframes shimmer {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* ── Reduced motion ─────────────────────────────────────────────────────── */

@media (prefers-reduced-motion: reduce) {
  .skeleton-card { animation: none; opacity: 0.6; }
  .receipt-card, .filter-chip, .btn-new, .btn-retry { transition: none; }
}
</style>
