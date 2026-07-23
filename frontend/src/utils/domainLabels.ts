import { ProcurementStatus, ProcurementType } from '@/types/enums'
import { translateNow } from '@/i18n'

export interface LabelMeta {
  label: string
  colorClass?: string
  labelKey?: string
}

export const procurementTypeMeta: Record<ProcurementType, LabelMeta> = {
  [ProcurementType.OWN_FUNDS]: { label: 'Own funds', labelKey: 'domain.procurementType.OWN_FUNDS', colorClass: 'badge-type--teal' },
  [ProcurementType.PARTNERSHIP]: { label: 'Partnership', labelKey: 'domain.procurementType.PARTNERSHIP', colorClass: 'badge-type--purple' },
  [ProcurementType.MUSHARAKA]: { label: 'Musharaka', labelKey: 'domain.procurementType.MUSHARAKA', colorClass: 'badge-type--indigo' },
  [ProcurementType.DISTRIBUTOR]: { label: 'Distributor', labelKey: 'domain.procurementType.DISTRIBUTOR', colorClass: 'badge-type--blue' },
}

export const procurementStatusMeta: Record<ProcurementStatus, LabelMeta> = {
  [ProcurementStatus.OPEN]: { label: 'Open', labelKey: 'domain.procurementStatus.OPEN', colorClass: 'badge-status--gray' },
  [ProcurementStatus.PARTIALLY_RECEIVED]: { label: 'Partial', labelKey: 'domain.procurementStatus.PARTIALLY_RECEIVED', colorClass: 'badge-status--orange' },
  [ProcurementStatus.RECEIVED]: { label: 'Completed', labelKey: 'domain.procurementStatus.RECEIVED', colorClass: 'badge-status--green' },
  [ProcurementStatus.CLOSED]: { label: 'Closed', labelKey: 'domain.procurementStatus.CLOSED', colorClass: 'badge-status--blue' },
  [ProcurementStatus.CANCELLED]: { label: 'Cancelled', labelKey: 'domain.procurementStatus.CANCELLED', colorClass: 'badge-status--orange' },
}

export function procurementTypeLabel(type: string): string {
  const meta = procurementTypeMeta[type as ProcurementType]
  return meta?.labelKey ? translateNow(meta.labelKey) : (meta?.label ?? type)
}

export function procurementStatusLabel(status: string): string {
  const meta = procurementStatusMeta[status as ProcurementStatus]
  return meta?.labelKey ? translateNow(meta.labelKey) : (meta?.label ?? status)
}

const _isLineSettled = (state: string): boolean => state === 'RECEIVED' || state === 'CANCELLED'

/**
 * Receive-badge label that disambiguates the backend PARTIALLY_RECEIVED state.
 * The backend holds a procurement at PARTIALLY_RECEIVED while ANY item OR expense
 * line is still unposted (this keeps the amendment/expense-posting window open).
 * A flat "Частично" then contradicts a "10/10 goods received" count. When every
 * goods line is in but a cost line is still unposted, say so explicitly; only call
 * the goods receipt itself partial when a goods line is genuinely pending.
 */
export function procurementReceiveBadgeLabel(
  status: string,
  items: Array<{ lifecycle_state: string }> = [],
  expenses: Array<{ lifecycle_state: string }> = [],
): string {
  if (status !== ProcurementStatus.PARTIALLY_RECEIVED) {
    return procurementStatusLabel(status)
  }
  const goodsPending = items.some((item) => !_isLineSettled(item.lifecycle_state))
  const expensesPending = expenses.some((expense) => !_isLineSettled(expense.lifecycle_state))
  if (!goodsPending && expensesPending) {
    return 'Товар принят · расход не проведён'
  }
  return 'Товар принят частично'
}

export function partnerRoleLabel(role: string): string {
  if (role === 'INVESTOR') return translateNow('domain.partnerRole.INVESTOR')
  if (role === 'OPERATOR') return translateNow('domain.partnerRole.OPERATOR')
  return role
}
