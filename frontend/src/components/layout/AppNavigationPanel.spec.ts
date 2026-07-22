import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it } from 'vitest'
import { UserRole } from '@/types/enums'
import AppNavigationPanel from './AppNavigationPanel.vue'
import { getBusinessNavigation } from './navigation'

const messages = {
  ru: {
    nav: {
      main: 'Основная навигация',
      sections: {
        sales: 'Продажи',
        products: 'Товары',
        procurements: 'Приходы',
        finance: 'Деньги',
        relationships: 'Контрагенты',
        settings: 'Система',
      },
      sales: 'Продажа',
      products: 'Товары',
      procurements: 'Приход',
      reports: 'Отчёты',
      cash: 'Касса',
      settings: 'Настройки',
    },
    sales: { history: 'История продаж' },
    products: { categories: 'Категории' },
    settings: { quickLinks: { transfers: 'Перемещения', integrations: 'Интеграции', pageMap: 'Карта разделов' } },
    procurements: { agreements: 'Договоры' },
    reports: { reconciliation: 'Сверка' },
    finance: { exchange: 'Обмен валют' },
    investors: { ownerTitle: 'Инвесторы' },
    customers: { title: 'Покупатели' },
    suppliers: { title: 'Поставщики', payablesPageTitle: 'Долги поставщикам' },
  },
}

async function mountPanel(routeName = 'sales-catalog') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/sales', name: 'sales-catalog', component: { template: '<div />' } },
      { path: '/products', name: 'products', component: { template: '<div />' } },
    ],
  })
  await router.push({ name: routeName })
  await router.isReady()

  const i18n = createI18n({ legacy: false, locale: 'ru', messages })
  const wrapper = mount(AppNavigationPanel, {
    props: {
      items: getBusinessNavigation({ role: UserRole.OWNER }),
      collapsibleSections: true,
    },
    global: {
      plugins: [router, i18n],
      stubs: {
        RouterLink: {
          props: ['to'],
          template: '<a href="#"><slot /></a>',
        },
      },
    },
  })
  return { wrapper, router }
}

describe('desktop navigation sections', () => {
  beforeEach(() => window.localStorage.clear())

  it('starts expanded and persists independently collapsed sections', async () => {
    const { wrapper } = await mountPanel()
    const productsToggle = wrapper.get('button[data-section-id="products"]')

    expect(productsToggle.attributes('aria-expanded')).toBe('true')
    await productsToggle.trigger('click')
    expect(productsToggle.attributes('aria-expanded')).toBe('false')
    const productsContent = wrapper.get('[data-section-items="products"]')
    expect(productsContent.attributes('data-collapsed')).toBe('true')
    expect(productsContent.attributes('aria-hidden')).toBe('true')
    expect(productsContent.attributes('inert')).toBeDefined()
    expect(window.localStorage.getItem('microposs:desktop-nav-sections:v1')).toContain('products')
  })

  it('keeps the active section open even when it was previously collapsed', async () => {
    window.localStorage.setItem('microposs:desktop-nav-sections:v1', JSON.stringify(['products']))
    const { wrapper } = await mountPanel('products')

    const productsToggle = wrapper.get('button[data-section-id="products"]')
    expect(productsToggle.attributes('aria-expanded')).toBe('true')
    expect(productsToggle.attributes('disabled')).toBeDefined()
    const productsContent = wrapper.get('[data-section-items="products"]')
    expect(productsContent.attributes('data-collapsed')).toBe('false')
    expect(productsContent.attributes('aria-hidden')).toBeUndefined()
    expect(productsContent.attributes('inert')).toBeUndefined()
  })

  it('does not expose section toggles in the non-collapsible drawer contract', async () => {
    const { wrapper } = await mountPanel()
    await wrapper.setProps({ collapsibleSections: false })
    expect(wrapper.find('button[data-section-id]').exists()).toBe(false)
  })
})
