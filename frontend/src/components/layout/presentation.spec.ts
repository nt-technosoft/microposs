import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { afterEach, describe, expect, it } from 'vitest'
import ListWorkbench from './ListWorkbench.vue'
import ResponsiveFlowColumns from './ResponsiveFlowColumns.vue'
import ResponsiveOverlay from './ResponsiveOverlay.vue'
import WorkspaceSplit from './WorkspaceSplit.vue'
import { clearPageChrome, pageChromeState, registerPageChrome } from './pageChrome'

const i18n = createI18n({
  legacy: false,
  locale: 'ru',
  messages: {
    ru: {
      common: {
        close: 'Закрыть',
        dialog: 'Диалог',
      },
    },
  },
})

describe('page chrome state', () => {
  const owners: symbol[] = []

  afterEach(() => {
    owners.forEach(clearPageChrome)
    owners.length = 0
  })

  it('keeps the newest page owner from being cleared by an older page', () => {
    const first = Symbol('first')
    const second = Symbol('second')
    owners.push(first, second)

    registerPageChrome(first, { title: 'Каталог' })
    registerPageChrome(second, { title: 'Карточка товара', status: 'Активен' })
    clearPageChrome(first)

    expect(pageChromeState.title).toBe('Карточка товара')
    expect(pageChromeState.status).toBe('Активен')
  })

  it('restores the parent page chrome after a nested owner unmounts', () => {
    const parent = Symbol('parent')
    const nested = Symbol('nested')
    owners.push(parent, nested)

    registerPageChrome(parent, { title: 'Товары' })
    registerPageChrome(nested, { title: 'Карточка товара' })
    clearPageChrome(nested)

    expect(pageChromeState.title).toBe('Товары')
  })
})

describe('responsive presentation primitives', () => {
  it('preserves the bottom-sheet close contract through the accessible dialog', async () => {
    const wrapper = mount(ResponsiveOverlay, {
      props: { open: true, title: 'Новая категория' },
      global: {
        plugins: [i18n],
        stubs: {
          Dialog: { template: '<div><slot /></div>' },
          DialogContent: { template: '<section><slot /></section>' },
          DialogHeader: { template: '<header><slot /></header>' },
          DialogTitle: { template: '<h2><slot /></h2>' },
          DialogDescription: { template: '<p><slot /></p>' },
        },
      },
    })

    expect(wrapper.text()).toContain('Новая категория')
    await wrapper.get('button[aria-label="Закрыть"]').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })

  it('keeps filters and results in one list workbench contract', () => {
    const wrapper = mount(ListWorkbench, {
      slots: {
        toolbar: '<div data-test="toolbar">Поиск</div>',
        aside: '<div data-test="aside">Фильтры</div>',
        default: '<div data-test="content">Результаты</div>',
      },
    })

    expect(wrapper.find('[data-test="toolbar"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="aside"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="content"]').exists()).toBe(true)
    expect(wrapper.find('.list-workbench__body--with-aside').exists()).toBe(true)
  })

  it('keeps independent flow and split regions in one DOM order', () => {
    const flow = mount(ResponsiveFlowColumns, {
      slots: {
        default: '<section data-test="first">Первый</section><section data-test="second">Второй</section>',
      },
    })
    const split = mount(WorkspaceSplit, {
      props: { stickyMain: true },
      slots: {
        default: '<div data-test="main">Работа</div>',
        aside: '<div data-test="aside">Контекст</div>',
      },
    })

    expect(flow.findAll('section').map((node) => node.attributes('data-test'))).toEqual(['first', 'second'])
    expect(split.find('[data-test="main"]').exists()).toBe(true)
    expect(split.find('[data-test="aside"]').exists()).toBe(true)
    expect(split.find('.workspace-split__main--sticky').exists()).toBe(true)
  })
})
