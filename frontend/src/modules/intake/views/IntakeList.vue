<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { fetchProcurementWorkspaces, type ProcurementWorkspacePayload } from '@/api/partnerships'
import { useToast } from '@/composables/useToast'
import { ProcurementStatus } from '@/types/enums'
import ProcurementListCard from '@/modules/intake/components/list/ProcurementListCard.vue'
import ProcurementListHeader from '@/modules/intake/components/list/ProcurementListHeader.vue'
import ProcurementListStates from '@/modules/intake/components/list/ProcurementListStates.vue'
import ProcurementListWorkbench from '@/modules/intake/components/list/ProcurementListWorkbench.vue'
import type { FilterChip, ProcurementView } from '@/modules/intake/components/list/types'
import { computeSignals, matchesView } from '@/modules/intake/utils/procurementListStats'

const router = useRouter()
const toast = useToast()
const { t } = useI18n()

const procurements = ref<ProcurementWorkspacePayload[]>([])
const isLoading = ref(false)
const error = ref<string | null>(null)
const activeView = ref<ProcurementView>('all')

let controller: AbortController | null = null

const filterChips: FilterChip[] = [
  { value: 'all', label: t('common.all') },
  { value: ProcurementStatus.OPEN, label: 'В работе' },
  { value: ProcurementStatus.PARTIALLY_RECEIVED, label: 'Часть получена' },
  { value: ProcurementStatus.RECEIVED, label: 'Получены' },
  { value: ProcurementStatus.CLOSED, label: 'Закрытые' },
]

// Signals are computed over the full list, independent of the active filter:
// triage answers "what needs action across everything", not "within this view".
const signals = computed(() => computeSignals(procurements.value))

const filteredProcurements = computed(() =>
  procurements.value.filter((item) => matchesView(item, activeView.value)),
)

function isAbort(err: unknown): boolean {
  return (
    typeof err === 'object' &&
    err !== null &&
    ('name' in err && (err as { name?: string }).name === 'CanceledError'
      || 'code' in err && (err as { code?: string }).code === 'ERR_CANCELED')
  )
}

async function loadProcurementList(): Promise<void> {
  controller?.abort()
  controller = new AbortController()
  isLoading.value = true
  error.value = null

  try {
    procurements.value = await fetchProcurementWorkspaces({}, controller.signal)
  } catch (err: unknown) {
    if (isAbort(err)) return
    const message = err instanceof Error ? err.message : t('procurements.loadFailed')
    error.value = message
    toast.error(message)
  } finally {
    isLoading.value = false
  }
}

onMounted(loadProcurementList)
onBeforeUnmount(() => controller?.abort())

function goToDetail(id: number): void {
  router.push({ name: 'procurement-detail', params: { id } })
}

function goToCreate(): void {
  router.push({ name: 'procurement-create' })
}

function goToPartnershipCreate(): void {
  router.push({ name: 'procurement-create', query: { mode: 'partnership' } })
}

function goToAgreements(): void {
  router.push({ name: 'agreement-list' })
}

function onSelectView(value: ProcurementView): void {
  activeView.value = activeView.value === value ? 'all' : value
}
</script>

<template>
  <main class="min-h-dvh bg-background pb-[calc(var(--bottom-nav-height)+1rem)]">
    <ProcurementListHeader
      :is-loading="isLoading"
      @refresh="loadProcurementList"
      @create="goToCreate"
      @create-partnership="goToPartnershipCreate"
    />

    <section class="mx-auto flex w-full max-w-[var(--max-content-width)] flex-col gap-4 px-4 py-4 sm:px-6 lg:px-8">
      <ProcurementListWorkbench
        :active-view="activeView"
        :filters="filterChips"
        :signals="signals"
        @select-view="onSelectView"
        @open-agreements="goToAgreements"
      />

      <ProcurementListStates
        v-if="isLoading && procurements.length === 0"
        state="loading"
      />

      <ProcurementListStates
        v-else-if="error && filteredProcurements.length === 0"
        state="error"
        :error="error"
        @retry="loadProcurementList"
      />

      <ProcurementListStates
        v-else-if="filteredProcurements.length === 0"
        state="empty"
        :can-create="activeView === 'all'"
        @create="goToCreate"
      />

      <div
        v-else
        class="divide-y divide-neutral-200 overflow-hidden rounded-[14px] border border-neutral-200 bg-surface"
      >
        <ProcurementListCard
          v-for="procurement in filteredProcurements"
          :key="procurement.id"
          :procurement="procurement"
          @open="goToDetail"
        />
      </div>
    </section>
  </main>
</template>
