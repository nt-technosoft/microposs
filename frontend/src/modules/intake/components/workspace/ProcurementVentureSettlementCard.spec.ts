import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ProcurementVentureSettlementCard from './ProcurementVentureSettlementCard.vue'

// FB-3: the figure shown is provisional_profit_available_uzs (profit still owed
// to partners). Labelling it "Предв. прибыль" makes a fully-paid 0 read as if the
// profit vanished. The label must describe "to be paid out".
describe('ProcurementVentureSettlementCard — FB-3 (available-profit label)', () => {
  const summary = {
    totals: {
      capital_recovered_uzs: '1000.00',
      capital_return_available_uzs: '0.00',
      provisional_profit_uzs: '500.00',
      provisional_profit_available_uzs: '0.00',
      loss_uzs: '0.00',
      remaining_inventory_capital_uzs: '0.00',
    },
    has_active_lots: false,
  }

  it('labels the available-profit figure as payable, not as gross profit', () => {
    const wrapper = mount(ProcurementVentureSettlementCard, {
      props: { summary: summary as never, readonly: true },
    })
    expect(wrapper.text()).toContain('Прибыль к выплате')
    expect(wrapper.text()).not.toContain('Предв. прибыль')
  })
})
