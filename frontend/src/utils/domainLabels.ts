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

export function partnerRoleLabel(role: string): string {
  if (role === 'INVESTOR') return translateNow('domain.partnerRole.INVESTOR')
  if (role === 'OPERATOR') return translateNow('domain.partnerRole.OPERATOR')
  return role
}
