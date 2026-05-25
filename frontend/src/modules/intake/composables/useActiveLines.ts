/**
 * Single source of truth for active procurement lines and obligation totals.
 *
 * Mirrors backend active_procurement_lines() + procurement_cost_by_currency().
 * Rule: obligation totals exclude CANCELLED and RECEIVED. No × fx.
 * See docs/architecture.md — Currency Discipline & Receive Batch Gate.
 */
import { computed, type Ref } from 'vue'
import type { ProcurementWorkspacePayload } from '@/api/partnerships'

type Item = ProcurementWorkspacePayload['documents']['items'][number]
type Expense = ProcurementWorkspacePayload['documents']['expenses'][number]

function groupByCurrency<T>(
  lines: T[],
  getValue: (l: T) => number,
  getCurrency: (l: T) => string,
): Record<string, number> {
  const totals: Record<string, number> = {}
  for (const l of lines) {
    const cur = (getCurrency(l) || 'UZS').toUpperCase()
    totals[cur] = (totals[cur] ?? 0) + getValue(l)
  }
  return totals
}

function mergeTotals(
  a: Record<string, number>,
  b: Record<string, number>,
): Record<string, number> {
  const result = { ...a }
  for (const [cur, val] of Object.entries(b)) {
    result[cur] = (result[cur] ?? 0) + val
  }
  return result
}

export function useActiveLines(procurement: Ref<ProcurementWorkspacePayload>) {
  /** Non-CANCELLED items (for display lists — includes RECEIVED items for history). */
  const items = computed<Item[]>(() =>
    procurement.value.documents.items.filter((i) => i.lifecycle_state !== 'CANCELLED'),
  )

  /** Non-CANCELLED expenses (for display lists). */
  const expenses = computed<Expense[]>(() =>
    procurement.value.documents.expenses.filter((e) => e.lifecycle_state !== 'CANCELLED'),
  )

  /**
   * Active items for obligation totals — excludes CANCELLED and RECEIVED.
   * Matches backend active_procurement_lines() semantics.
   */
  const obligationItems = computed<Item[]>(() =>
    items.value.filter((i) => i.lifecycle_state !== 'RECEIVED'),
  )

  /** Active expenses for obligation totals — excludes CANCELLED and RECEIVED. */
  const obligationExpenses = computed<Expense[]>(() =>
    expenses.value.filter((e) => e.lifecycle_state !== 'RECEIVED'),
  )

  /** Per-currency obligation totals for items only (qty × unit_purchase_price, no × fx). */
  const itemTotalsByCurrency = computed<Record<string, number>>(() =>
    groupByCurrency(
      obligationItems.value,
      (i) => (parseFloat(i.quantity) || 0) * (parseFloat(i.unit_purchase_price) || 0),
      (i) => i.currency,
    ),
  )

  /** Per-currency obligation totals for expenses only (amount, no × fx). */
  const expenseTotalsByCurrency = computed<Record<string, number>>(() =>
    groupByCurrency(
      obligationExpenses.value,
      (e) => parseFloat(e.amount) || 0,
      (e) => e.currency,
    ),
  )

  /**
   * Combined per-currency obligation totals (items + expenses).
   * This is the frontend equivalent of backend procurement_cost_by_currency().
   * Use this for financing required, payment obligation display, receive cost.
   */
  const allTotalsByCurrency = computed<Record<string, number>>(() =>
    mergeTotals(itemTotalsByCurrency.value, expenseTotalsByCurrency.value),
  )

  return {
    items,
    expenses,
    obligationItems,
    obligationExpenses,
    itemTotalsByCurrency,
    expenseTotalsByCurrency,
    allTotalsByCurrency,
  }
}
