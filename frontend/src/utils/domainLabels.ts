import { ProcurementStatus, ProcurementType } from '@/types/enums'

export interface LabelMeta {
  label: string
  colorClass?: string
}

export const procurementTypeMeta: Record<ProcurementType, LabelMeta> = {
  [ProcurementType.OWN_FUNDS]: { label: 'Свои деньги', colorClass: 'badge-type--teal' },
  [ProcurementType.PARTNERSHIP]: { label: 'Партнёрский', colorClass: 'badge-type--purple' },
  [ProcurementType.MUSHARAKA]: { label: 'Мушарака', colorClass: 'badge-type--indigo' },
  [ProcurementType.DISTRIBUTOR]: { label: 'Дистрибьютор', colorClass: 'badge-type--blue' },
}

export const procurementStatusMeta: Record<ProcurementStatus, LabelMeta> = {
  [ProcurementStatus.OPEN]: { label: 'Открыт', colorClass: 'badge-status--gray' },
  [ProcurementStatus.PARTIALLY_RECEIVED]: { label: 'Частично', colorClass: 'badge-status--orange' },
  [ProcurementStatus.RECEIVED]: { label: 'Завершён', colorClass: 'badge-status--green' },
  [ProcurementStatus.CLOSED]: { label: 'Закрыт', colorClass: 'badge-status--blue' },
  [ProcurementStatus.CANCELLED]: { label: 'Отменён', colorClass: 'badge-status--orange' },
}

export function procurementTypeLabel(type: string): string {
  return procurementTypeMeta[type as ProcurementType]?.label ?? type
}

export function procurementStatusLabel(status: string): string {
  return procurementStatusMeta[status as ProcurementStatus]?.label ?? status
}

export function partnerRoleLabel(role: string): string {
  if (role === 'INVESTOR') return 'Инвестор'
  if (role === 'OPERATOR') return 'Бизнес'
  return role
}
