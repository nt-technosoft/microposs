import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  fetchProcurementWorkspace,
  createProcurementWorkspace,
  runProcurementWorkspaceAction,
  type ProcurementWorkspacePayload,
  type ProcurementWorkspaceCreatePayload,
  type WorkspaceActionKey,
} from '@/api/partnerships'

export type { ProcurementWorkspacePayload }

export const useProcurementWorkspaceStore = defineStore('procurementWorkspace', () => {
  const procurement = ref<ProcurementWorkspacePayload | null>(null)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  let abortController: AbortController | null = null

  function $reset(): void {
    abortController?.abort()
    abortController = null
    procurement.value = null
    isLoading.value = false
    error.value = null
  }

  async function load(procurementId: number): Promise<void> {
    abortController?.abort()
    abortController = new AbortController()
    isLoading.value = true
    error.value = null
    try {
      procurement.value = await fetchProcurementWorkspace(procurementId, abortController.signal)
    } catch (err) {
      if ((err as any)?.name === 'AbortError') return
      error.value = String((err as any)?.message ?? err)
    } finally {
      isLoading.value = false
    }
  }

  async function createDraft(payload: ProcurementWorkspaceCreatePayload): Promise<number> {
    abortController?.abort()
    abortController = null
    isLoading.value = true
    error.value = null
    procurement.value = null
    try {
      const created = await createProcurementWorkspace(payload)
      procurement.value = created
      return created.id
    } catch (err) {
      error.value = String((err as any)?.message ?? err)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function dispatch(action: WorkspaceActionKey | string, payload: Record<string, unknown>): Promise<void> {
    if (!procurement.value) throw new Error('No procurement loaded')
    procurement.value = await runProcurementWorkspaceAction(
      procurement.value.id,
      action as WorkspaceActionKey,
      payload,
    )
  }

  const status = computed(() => procurement.value?.status ?? null)

  return {
    procurement,
    isLoading,
    error,
    status,
    $reset,
    load,
    createDraft,
    dispatch,
  }
})
