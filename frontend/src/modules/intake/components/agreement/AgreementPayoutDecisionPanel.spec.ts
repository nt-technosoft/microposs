import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import AgreementPayoutDecisionPanel from './AgreementPayoutDecisionPanel.vue'
import type { PayoutDecisionPreview } from '@/api/partnerships'

const BaseSelectStub = {
  name: 'BaseSelect',
  props: ['modelValue', 'options', 'title'],
  template: '<div data-test="account-select" :data-title="title">{{ options.map((option) => option.label).join("|") }}</div>',
}

const rows = [{
  key: '1:10',
  procurementId: 1,
  partnerId: 10,
  partnerName: 'Investor',
  role: 'INVESTOR',
  availableUzs: 100000,
  recoveredUzs: 140000,
  returnedUzs: 20000,
  rolledUzs: 20000,
}]

const accounts = [{
  id: 5,
  name: 'Main Cash',
  currency: 'UZS',
  balance: '500000.00',
  is_active: true,
}]
const usdOnlyAccounts = [{
  id: 9,
  name: 'USD Cash',
  currency: 'USD',
  balance: '1200.00',
  is_active: true,
}]

function mountPanel(preview: PayoutDecisionPreview | null = null, customAccounts = accounts) {
  return mount(AgreementPayoutDecisionPanel, {
    props: { rows, accounts: customAccounts as never, preview },
    global: { stubs: { BaseSelect: BaseSelectStub } },
  })
}

function findButton(wrapper: ReturnType<typeof mountPanel>, text: string) {
  const button = wrapper.findAll('button').find((item) => item.text().includes(text))
  expect(button, `button ${text}`).toBeTruthy()
  return button!
}

describe('AgreementPayoutDecisionPanel', () => {
  it('emits a policy preview payload for the group decision', async () => {
    const wrapper = mountPanel()

    await findButton(wrapper, 'Проверить policy').trigger('click')

    expect(wrapper.emitted('preview')?.[0]?.[0]).toMatchObject({
      decisionType: 'ROLL_OVER_CAPITAL',
      amountUzs: '100000.00',
      accountId: 5,
    })
  })

  it('emits editable allocations when executing an allowed preview', async () => {
    const wrapper = mountPanel({
      allowed: true,
      agreement_id: 1,
      decision_type: 'ROLL_OVER_CAPITAL',
      currency: 'UZS',
      amount_uzs: '100000.00',
      total_available_uzs: '100000.00',
      eligible_total_uzs: '100000.00',
      reserve_amount_uzs: '0.00',
      trigger_mode: 'ANY',
      interval_ready: false,
      threshold_ready: true,
      spacing_ready: true,
      last_decision_id: null,
      source_account: { id: 5, name: 'Main Cash', currency: 'UZS', balance: '500000.00' },
      allocations: [{
        procurement_id: 1,
        partner_id: 10,
        partner_name: 'Investor',
        amount_uzs: '100000.00',
        available_uzs: '100000.00',
      }],
      constraints: [],
      blocking_reasons: [],
    })

    await findButton(wrapper, 'Оставить капитал').trigger('click')

    expect(wrapper.emitted('execute')?.[0]?.[0]).toMatchObject({
      decisionType: 'ROLL_OVER_CAPITAL',
      amountUzs: '100000.00',
      accountId: 5,
      allocations: [{ procurement_id: 1, partner_id: 10, amount_uzs: '100000.00' }],
    })
  })

  it('offers USD operating accounts for rollover but not direct payout', async () => {
    const wrapper = mountPanel(null, usdOnlyAccounts)

    expect(wrapper.find('[data-test="account-select"]').text()).toContain('USD Cash')
    await findButton(wrapper, 'Выплатить').trigger('click')

    expect(wrapper.find('[data-test="account-select"]').text()).toBe('')
    expect(wrapper.emitted('preview')).toBeFalsy()
  })
})
