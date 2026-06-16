import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import AgreementRecoveredCapitalCard from './AgreementRecoveredCapitalCard.vue'

// FB-5: the account picker auto-selected the first account even when its balance
// is 0 ("Main Card · 0 UZS"). A capital return debits real cash, so the default
// must prefer a funded account — and never silently pick an empty one.
const BaseSelectStub = {
  name: 'BaseSelect',
  props: ['modelValue', 'options', 'title'],
  template: '<div data-test="account-select" />',
}
const MoneyStub = {
  name: 'MoneyCurrencyInput',
  props: ['modelValue', 'currency', 'currencies', 'placeholder'],
  template: '<div />',
}

const rows = [{
  key: 'r1',
  procurementId: 1,
  partnerId: 1,
  partnerName: 'Партнёр',
  role: 'INVESTOR',
  availableUzs: 1000,
  recoveredUzs: 1000,
  returnedUzs: 0,
}]

function mountCard(accounts: unknown[]) {
  return mount(AgreementRecoveredCapitalCard, {
    props: { rows: rows as never, accounts: accounts as never, usdRate: '0' },
    global: { stubs: { BaseSelect: BaseSelectStub, MoneyCurrencyInput: MoneyStub } },
  })
}

function selectedAccountId(wrapper: ReturnType<typeof mountCard>): number | null {
  return wrapper.findComponent(BaseSelectStub).props('modelValue') as number | null
}

describe('AgreementRecoveredCapitalCard — FB-5 (default account selection)', () => {
  it('defaults to the first funded account, not the empty one', () => {
    const wrapper = mountCard([
      { id: 10, name: 'Main Card', currency: 'UZS', is_active: true, balance: '0' },
      { id: 20, name: 'Касса', currency: 'UZS', is_active: true, balance: '500000' },
    ])
    expect(selectedAccountId(wrapper)).toBe(20)
  })

  it('auto-selects nothing (placeholder) when no account is funded', () => {
    const wrapper = mountCard([
      { id: 10, name: 'Main Card', currency: 'UZS', is_active: true, balance: '0' },
      { id: 11, name: 'Резерв', currency: 'UZS', is_active: true, balance: '0' },
    ])
    expect(selectedAccountId(wrapper)).toBeNull()
  })
})
