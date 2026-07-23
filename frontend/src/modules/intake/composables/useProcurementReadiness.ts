import { computed, type Ref } from 'vue'
import type { ProcurementWorkspacePayload, WorkspaceSectionKey } from '@/api/partnerships'

/**
 * Single source of truth for section visibility and readiness state.
 * Cards whose local isFilled semantics match the backend key can call
 * readinessOk(key) instead of maintaining a local computed.
 *
 * Keys where backend semantics currently diverge from prior local logic
 * (source_ready, expenses_ready, payment_ready, receive_ready) are NOT
 * exposed here to prevent inadvertent visual regressions. Migrate those
 * once backend readiness is refined to match expected UX.
 */
export function useProcurementReadiness(
  procurement: Ref<ProcurementWorkspacePayload | null>,
) {
  function sectionVisible(key: WorkspaceSectionKey): boolean {
    return procurement.value?.policy.visible_sections.includes(key) ?? false
  }

  function readinessOk(readinessKey: string): boolean {
    return procurement.value?.readiness[readinessKey]?.ok ?? false
  }

  function readinessMessage(readinessKey: string): string | null {
    return procurement.value?.readiness[readinessKey]?.message ?? null
  }

  const capitalSectionVisible = computed(() => sectionVisible('capital'))
  const itemsReady = computed(() => readinessOk('items_ready'))

  return {
    sectionVisible,
    readinessOk,
    readinessMessage,
    capitalSectionVisible,
    itemsReady,
  }
}
