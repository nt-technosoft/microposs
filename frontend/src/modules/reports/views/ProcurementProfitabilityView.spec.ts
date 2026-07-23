import { describe, it, expect, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { i18n } from '@/i18n'

vi.mock('vue-router', async (orig) => ({
  ...(await orig<typeof import('vue-router')>()),
  useRoute: () => ({ params: { id: '5' } }),
  useRouter: () => ({ push: vi.fn(), back: vi.fn() }),
}))

const reportPayload = {
  procurement: {
    procurement_id: 5,
    supplier_name: 'ACME',
    funding_source: 'PARTNERSHIP',
    status: 'RECEIVED',
    received_at: '2026-01-01T00:00:00Z',
    opened_at: '2026-01-01T00:00:00Z',
    gross_profit: '0',
    projected_gross_profit: '0',
    revenue: '0',
    cogs: '0',
    remaining_landed_cost: '0',
    quantity_sold: 0,
    remaining_quantity: 0,
    investor_profit: '0',
    business_profit: '0',
    projected_revenue: '0',
    projected_investor_profit: '0',
    projected_business_profit: '0',
  },
  items: [],
  report_currency: { currency: 'UZS' },
}

vi.mock('@/api/finance', () => ({
  fetchProcurementProfitabilityDetail: vi.fn(() => Promise.resolve(reportPayload)),
}))

const fetchProcurementMock = vi.fn()
vi.mock('@/api/partnerships', () => ({
  fetchProcurement: (...args: unknown[]) => fetchProcurementMock(...args),
}))

// Import after mocks are registered.
import ProcurementProfitabilityView from './ProcurementProfitabilityView.vue'

function mountView() {
  const errors: unknown[] = []
  const wrapper = mount(ProcurementProfitabilityView, {
    global: {
      plugins: [i18n],
      config: { errorHandler: (err: unknown) => { errors.push(err) } },
    },
  })
  return { wrapper, errors }
}

describe('ProcurementProfitabilityView — FB-1 (missing balance must not crash)', () => {
  it('renders the report (no crash) when the procurement has no balance block', async () => {
    // Non-partnership / no-contract procurement: backend omits `balance`.
    fetchProcurementMock.mockResolvedValueOnce({ id: 5 })

    const { wrapper, errors } = mountView()
    await flushPromises()

    expect(errors).toEqual([])
    expect(wrapper.find('.hero-title').exists()).toBe(true)
    // Ownership/movements fall back to empty — nothing rendered, no white screen.
    expect(wrapper.find('.participant-list').exists()).toBe(false)
    expect(wrapper.find('.history-list').exists()).toBe(false)
  })

  it('renders participant totals when a balance block is present', async () => {
    fetchProcurementMock.mockResolvedValueOnce({
      id: 5,
      balance: {
        participant_totals: [{
          partner_id: 1,
          partner_name: 'Partner',
          role: 'INVESTOR',
          contract_currency: 'UZS',
          planned_capital_share: '0',
          planned_profit_share: '0',
          contributed_amount: '0',
          net_capital: '0',
          actual_capital_share: '0',
        }],
        history: [],
      },
    })

    const { wrapper, errors } = mountView()
    await flushPromises()

    expect(errors).toEqual([])
    expect(wrapper.find('.participant-list').exists()).toBe(true)
  })
})
