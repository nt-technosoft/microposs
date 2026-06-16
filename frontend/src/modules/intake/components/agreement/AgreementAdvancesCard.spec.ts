import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AgreementAdvancesCard from './AgreementAdvancesCard.vue'

// FB-3: the venture-facts block shows provisional_profit_available_uzs (profit
// still owed). Same mislabel as the procurement card — must read "to be paid out".
describe('AgreementAdvancesCard — FB-3 (available-profit label)', () => {
  const positions = [{
    partner_id: 1,
    partner_name: 'Партнёр',
    role: 'INVESTOR',
    currency: 'UZS',
    net: '0',
    owed: '0',
    withdrawable: '0',
    capital_recovered_uzs: '1000.00',
    remaining_inventory_capital_uzs: '0.00',
    provisional_profit_uzs: '500.00',
    provisional_profit_available_uzs: '0.00',
    capital_return_available_uzs: '0.00',
    loss_uzs: '0.00',
    negative_position_uzs: '0.00',
  }]

  it('labels the available-profit figure as payable, not as gross profit', () => {
    const wrapper = mount(AgreementAdvancesCard, {
      props: { positions: positions as never },
    })
    expect(wrapper.text()).toContain('Прибыль к выплате')
    expect(wrapper.text()).not.toContain('Предв. прибыль')
  })
})
