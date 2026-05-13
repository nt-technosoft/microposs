import { computed, type ComputedRef, type Ref } from 'vue'
import type { ProcurementDetail } from '@/api/partnerships'
import { ProcurementStatus, ProcurementType } from '@/types/enums'

type SettlementType = 'PREPAID' | 'PARTIAL' | 'DEFERRED' | 'INSTALLMENT' | 'CONSIGNMENT'
type WorkspaceSection = 'overview' | 'source' | 'items' | 'settlement' | 'capital' | 'receive' | 'history'

interface WorkspaceStateInput {
  procurement: Ref<ProcurementDetail | null>
  isOwner: ComputedRef<boolean>
  selectedWarehouseId?: Ref<number | null>
}

const OWN_FUNDS_SETTLEMENTS: SettlementType[] = ['PREPAID', 'PARTIAL', 'DEFERRED', 'INSTALLMENT', 'CONSIGNMENT']
const PARTNERSHIP_SETTLEMENTS: SettlementType[] = ['PREPAID']
const SUPPLIER_REQUIRED_SETTLEMENTS: SettlementType[] = ['PARTIAL', 'DEFERRED', 'INSTALLMENT', 'CONSIGNMENT']
const RECEIVE_READY_STATUSES = new Set(['READY', 'AUTO_SURPLUS', 'AGREEMENT_SURPLUS'])

function normalizeFundingSource(type: string | null | undefined): ProcurementType | null {
  if (type === ProcurementType.MUSHARAKA) return ProcurementType.PARTNERSHIP
  if (type === ProcurementType.OWN_FUNDS) return ProcurementType.OWN_FUNDS
  if (type === ProcurementType.PARTNERSHIP) return ProcurementType.PARTNERSHIP
  return null
}

export function useProcurementWorkspaceState(input: WorkspaceStateInput) {
  const fundingSource = computed(() => normalizeFundingSource(input.procurement.value?.procurement_type))
  const isLegacyMusharaka = computed(() => input.procurement.value?.procurement_type === ProcurementType.MUSHARAKA)
  const isOwnFunds = computed(() => fundingSource.value === ProcurementType.OWN_FUNDS)
  const isPartnership = computed(() => fundingSource.value === ProcurementType.PARTNERSHIP)
  const settlementType = computed(() => input.procurement.value?.terms?.type as SettlementType | undefined)

  const allowedSettlementTypes = computed<SettlementType[]>(() => {
    if (isOwnFunds.value) return OWN_FUNDS_SETTLEMENTS
    if (isPartnership.value) return PARTNERSHIP_SETTLEMENTS
    return []
  })

  const canWorkOnProcurement = computed(() => {
    const status = input.procurement.value?.status
    return status === ProcurementStatus.OPEN || status === ProcurementStatus.PARTIALLY_RECEIVED
  })

  const hasReceiveBatches = computed(() => Boolean(input.procurement.value?.receive_batches?.length))
  const hasCapitalActivity = computed(() => {
    const balance = input.procurement.value?.balance
    return Boolean(
      balance?.contributions?.length
      || balance?.withdrawals?.length
      || balance?.exchanges?.length,
    )
  })
  const hasSettlement = computed(() => Boolean(input.procurement.value?.terms))
  const hasSupplier = computed(() => Boolean(input.procurement.value?.supplier))
  const hasInvestmentAgreement = computed(() => Boolean(input.procurement.value?.agreement || input.procurement.value?.contract))
  const hasCapitalPool = computed(() => Boolean(input.procurement.value?.balance))

  const blockedReasons = computed(() => {
    const reasons: string[] = []
    if (isLegacyMusharaka.value) {
      reasons.push('MUSHARAKA is legacy-only; use PARTNERSHIP in new flows.')
    }
    if (settlementType.value && !allowedSettlementTypes.value.includes(settlementType.value)) {
      reasons.push(`${fundingSource.value} does not allow ${settlementType.value} settlement in MVP.`)
    }
    if (isOwnFunds.value && hasCapitalActivity.value) {
      reasons.push('OWN_FUNDS should not use procurement capital pool.')
    }
    if (isPartnership.value && !hasInvestmentAgreement.value) {
      reasons.push('PARTNERSHIP requires investment agreement or contract.')
    }
    if (isPartnership.value && !hasCapitalPool.value) {
      reasons.push('PARTNERSHIP requires procurement capital pool.')
    }
    if (settlementType.value && SUPPLIER_REQUIRED_SETTLEMENTS.includes(settlementType.value) && !hasSupplier.value) {
      reasons.push(`${settlementType.value} settlement requires supplier.`)
    }
    return reasons
  })

  const isPolicyValid = computed(() => blockedReasons.value.length === 0)
  const visibleSections = computed<WorkspaceSection[]>(() => {
    const sections: WorkspaceSection[] = ['overview', 'source', 'items', 'settlement']
    if (isPartnership.value) sections.push('capital')
    sections.push('receive', 'history')
    return sections
  })

  const canEditSource = computed(() => (
    canWorkOnProcurement.value
    && !hasReceiveBatches.value
    && !hasCapitalActivity.value
  ))
  const canEditItems = computed(() => canWorkOnProcurement.value)
  const canManageCapital = computed(() => input.isOwner.value && canWorkOnProcurement.value && isPartnership.value)
  const canAllocateFromAgreement = computed(() => canManageCapital.value && Boolean(input.procurement.value?.agreement))
  const canReceiveBase = computed(() => {
    const status = input.procurement.value?.receive_plan?.status
    const warehouseReady = input.selectedWarehouseId ? input.selectedWarehouseId.value !== null : true
    return canWorkOnProcurement.value && warehouseReady && Boolean(status && RECEIVE_READY_STATUSES.has(status))
  })

  const readiness = computed(() => ({
    source_ready: isPartnership.value ? hasInvestmentAgreement.value : (settlementType.value && SUPPLIER_REQUIRED_SETTLEMENTS.includes(settlementType.value) ? hasSupplier.value : true),
    items_ready: Boolean(input.procurement.value?.items?.length),
    settlement_ready: settlementType.value ? allowedSettlementTypes.value.includes(settlementType.value) : false,
    capital_ready: isPartnership.value ? hasInvestmentAgreement.value && hasCapitalPool.value : true,
    receive_ready: canReceiveBase.value && isPolicyValid.value,
  }))

  return {
    fundingSource,
    isLegacyMusharaka,
    isOwnFunds,
    isPartnership,
    settlementType,
    allowedSettlementTypes,
    visibleSections,
    blockedReasons,
    isPolicyValid,
    canWorkOnProcurement,
    canEditSource,
    canEditItems,
    canManageCapital,
    canAllocateFromAgreement,
    canReceiveBase,
    hasReceiveBatches,
    hasCapitalActivity,
    hasSettlement,
    hasSupplier,
    hasInvestmentAgreement,
    hasCapitalPool,
    readiness,
    showCapitalSection: computed(() => visibleSections.value.includes('capital')),
  }
}

