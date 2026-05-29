import type { ProcurementWorkspacePayload } from '@/api/partnerships'
import { ProcurementStatus, ProcurementType } from '@/types/enums'

export function fundingLabel(source: string | null | undefined): string {
  if (source === ProcurementType.PARTNERSHIP) return 'Партнёрский'
  if (source === ProcurementType.OWN_FUNDS) return 'Свои деньги'
  return 'Источник не выбран'
}

/** Funding tone: brand-green ink for partnership, quiet neutral otherwise.
 *  Color is an accent on the label, never the only signal (label text carries meaning). */
export function fundingToneClass(source: string | null | undefined): string {
  if (source === ProcurementType.PARTNERSHIP) return 'text-green-700'
  return 'text-neutral-500'
}

export function statusLabel(status: string): string {
  switch (status) {
    case ProcurementStatus.OPEN:
      return 'В работе'
    case ProcurementStatus.PARTIALLY_RECEIVED:
      return 'Часть получена'
    case ProcurementStatus.RECEIVED:
      return 'Товар получен'
    case ProcurementStatus.CLOSED:
      return 'Закрыт'
    case ProcurementStatus.CANCELLED:
      return 'Отменён'
    default:
      return status
  }
}

/** Semantic dot fill for a status. Color rides on a dot, not on small text,
 *  so contrast stays AA and the status label remains neutral and readable. */
export function statusDotClass(status: string): string {
  switch (status) {
    case ProcurementStatus.OPEN:
      return 'bg-info'
    case ProcurementStatus.PARTIALLY_RECEIVED:
      return 'bg-warning'
    case ProcurementStatus.RECEIVED:
      return 'bg-positive'
    case ProcurementStatus.CLOSED:
      return 'bg-neutral-400'
    case ProcurementStatus.CANCELLED:
      return 'bg-negative'
    default:
      return 'bg-neutral-300'
  }
}

export function supplierLabel(procurement: ProcurementWorkspacePayload): string {
  return procurement.documents.procurement.supplier_name || 'Поставщик не выбран'
}

export function currentStepLabel(procurement: ProcurementWorkspacePayload): string {
  const step = procurement.flow.steps.find((item) => item.key === procurement.flow.current_step)
  return step?.title || procurement.display.next_action.label || 'Следующий шаг'
}
