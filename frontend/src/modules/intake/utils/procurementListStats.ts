import type { ProcurementWorkspacePayload } from '@/api/partnerships'
import { ProcurementStatus } from '@/types/enums'
import { formatPrice } from '@/utils/currency'
import type {
  AttentionSignals,
  AttentionView,
  MoneyByCurrency,
  ProcurementView,
} from '../components/list/types'

function toNumber(value: string | null | undefined): number {
  const parsed = Number.parseFloat(value ?? '0')
  return Number.isFinite(parsed) ? parsed : 0
}

/** Has an obligation that is not fully settled yet. */
export function isAwaitingPayment(p: ProcurementWorkspacePayload): boolean {
  const state = p.documents.payment_status?.state
  return state === 'unpaid' || state === 'underpaid'
}

/** Goods not yet (fully) received. */
export function isAwaitingReceipt(p: ProcurementWorkspacePayload): boolean {
  return p.status === ProcurementStatus.OPEN || p.status === ProcurementStatus.PARTIALLY_RECEIVED
}

/** Settlement deadline passed while still owing money. */
export function isOverdue(p: ProcurementWorkspacePayload, now: Date = new Date()): boolean {
  const deadline = p.documents.settlement?.deadline_date
  if (!deadline || !isAwaitingPayment(p)) return false
  return new Date(deadline).getTime() < now.getTime()
}

const ATTENTION_PREDICATES: Record<AttentionView, (p: ProcurementWorkspacePayload) => boolean> = {
  to_pay: isAwaitingPayment,
  to_receive: isAwaitingReceipt,
  overdue: (p) => isOverdue(p),
}

export function matchesView(p: ProcurementWorkspacePayload, view: ProcurementView): boolean {
  if (view === 'all') return true
  const predicate = ATTENTION_PREDICATES[view as AttentionView]
  if (predicate) return predicate(p)
  return p.status === view
}

/** Triage signals computed over the full (unfiltered) list. */
export function computeSignals(list: ProcurementWorkspacePayload[]): AttentionSignals {
  const remaining: MoneyByCurrency = {}
  let toPay = 0
  let toReceive = 0
  let overdue = 0
  const now = new Date()

  for (const p of list) {
    if (isAwaitingPayment(p)) {
      toPay += 1
      const byCurrency = p.documents.payment_status?.remaining_by_currency ?? {}
      for (const [currency, amount] of Object.entries(byCurrency)) {
        remaining[currency] = (remaining[currency] ?? 0) + toNumber(amount)
      }
    }
    if (isAwaitingReceipt(p)) toReceive += 1
    if (isOverdue(p, now)) overdue += 1
  }

  return {
    toPay: { count: toPay, remaining },
    toReceive: { count: toReceive },
    overdue: { count: overdue },
  }
}

/** Money by currency rendered without fx conversion: "1 250 000 UZS · 800 USD". */
export function formatMoneyByCurrency(money: MoneyByCurrency, max = 2): string {
  const entries = Object.entries(money).filter(([, amount]) => amount > 0)
  if (entries.length === 0) return '—'
  const shown = entries.slice(0, max).map(([currency, amount]) => formatPrice(amount, currency))
  const rest = entries.length - shown.length
  return rest > 0 ? `${shown.join(' · ')} +${rest}` : shown.join(' · ')
}
