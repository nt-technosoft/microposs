import { describe, it, expect } from 'vitest'
import { procurementReceiveBadgeLabel } from './domainLabels'

// FB-4: backend keeps a procurement PARTIALLY_RECEIVED while any cost line is
// still unposted, even when every goods line is received (10/10). The receive
// badge must distinguish "goods in, expense not posted" from genuinely partial
// goods receipt, instead of reading a flat "Частично" against a 10/10 count.
describe('procurementReceiveBadgeLabel — FB-4', () => {
  it('reads "goods accepted, expense not posted" when all items are received but an expense is unposted', () => {
    const items = [
      { lifecycle_state: 'RECEIVED' },
      { lifecycle_state: 'RECEIVED' },
    ]
    const expenses = [{ lifecycle_state: 'DRAFT' }]
    expect(procurementReceiveBadgeLabel('PARTIALLY_RECEIVED', items, expenses))
      .toBe('Товар принят · расход не проведён')
  })

  it('reads "goods partially accepted" when a goods line is still pending', () => {
    const items = [
      { lifecycle_state: 'RECEIVED' },
      { lifecycle_state: 'DRAFT' },
    ]
    const expenses = [{ lifecycle_state: 'RECEIVED' }]
    expect(procurementReceiveBadgeLabel('PARTIALLY_RECEIVED', items, expenses))
      .toBe('Товар принят частично')
  })

  it('defers to the plain status label for non-partial statuses', () => {
    const label = procurementReceiveBadgeLabel('RECEIVED', [], [])
    expect(label).not.toBe('Товар принят · расход не проведён')
    expect(label).not.toBe('Товар принят частично')
  })
})
