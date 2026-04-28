<script setup lang="ts">
import type { Component } from 'vue'
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowLeft,
  BarChart3,
  Boxes,
  CircleDollarSign,
  Download,
  FolderTree,
  History,
  LockKeyhole,
  Map,
  Package,
  ReceiptText,
  Settings,
  ShoppingBag,
  Users,
} from 'lucide-vue-next'

import { useAuthStore } from '@/stores/auth'
import { UserRole } from '@/types/enums'

interface PageMapItem {
  title: string
  description: string
  routeName?: string
  contextual?: boolean
  roles: UserRole[]
}

interface PageMapSection {
  title: string
  description: string
  icon: Component
  primaryRouteName?: string
  items: PageMapItem[]
}

const router = useRouter()
const auth = useAuthStore()

const sections: PageMapSection[] = [
  {
    title: 'Продажи',
    description: 'Касса, корзина, оформление, история и аудит чеков.',
    icon: ShoppingBag,
    primaryRouteName: 'sales-catalog',
    items: [
      { title: 'Каталог продажи', description: 'Главный экран кассира.', routeName: 'sales-catalog', roles: [UserRole.OWNER, UserRole.CASHIER] },
      { title: 'Корзина и оформление', description: 'Открываются из каталога после выбора товара.', contextual: true, roles: [UserRole.OWNER, UserRole.CASHIER] },
      { title: 'История продаж', description: 'Все чеки, возвраты и детали продажи.', routeName: 'sales-history', roles: [UserRole.OWNER, UserRole.CASHIER] },
      { title: 'Аудит продажи', description: 'Открывается из истории или блока прибыльности продаж.', contextual: true, roles: [UserRole.OWNER] },
    ],
  },
  {
    title: 'Товары и склад',
    description: 'Каталог, категории, остатки и перемещения между точками.',
    icon: Package,
    primaryRouteName: 'products',
    items: [
      { title: 'Товары', description: 'Список товаров и редактирование карточек.', routeName: 'products', roles: [UserRole.OWNER, UserRole.WAREHOUSE] },
      { title: 'Создание товара', description: 'Открывается из списка товаров.', routeName: 'product-create', roles: [UserRole.OWNER] },
      { title: 'Категории', description: 'Структура каталога и шаблоны атрибутов.', routeName: 'categories', roles: [UserRole.OWNER] },
      { title: 'Перемещения', description: 'Перевод остатков между складом и магазином.', routeName: 'stock-transfers', roles: [UserRole.OWNER, UserRole.WAREHOUSE] },
    ],
  },
  {
    title: 'Приход',
    description: 'Закупки, договор, баланс, оприходование и аналитика по закупке.',
    icon: Download,
    primaryRouteName: 'procurement-list',
    items: [
      { title: 'Список приходов', description: 'Все закупки и их текущий статус.', routeName: 'procurement-list', roles: [UserRole.OWNER, UserRole.WAREHOUSE] },
      { title: 'Инвестдоговоры', description: 'Общий бюджет, взносы и несколько связанных приходов.', routeName: 'agreement-list', roles: [UserRole.OWNER] },
      { title: 'Создание прихода', description: 'Новый приход, договор и строки закупки.', routeName: 'procurement-create', roles: [UserRole.OWNER, UserRole.WAREHOUSE] },
      { title: 'Создание инвестдоговора', description: 'Плановый бюджет и участники партнёрской сделки.', routeName: 'agreement-create', roles: [UserRole.OWNER] },
      { title: 'Карточка прихода', description: 'Открывается из списка приходов.', contextual: true, roles: [UserRole.OWNER, UserRole.WAREHOUSE] },
      { title: 'Карточка инвестдоговора', description: 'Открывается из списка инвестдоговоров.', contextual: true, roles: [UserRole.OWNER] },
      { title: 'Аудит закупки', description: 'Прибыль, остаток, прогноз и распределение.', contextual: true, roles: [UserRole.OWNER] },
    ],
  },
  {
    title: 'Отчёты',
    description: 'Управленческие цифры, сверка, прибыльность и объяснение расчётов.',
    icon: BarChart3,
    primaryRouteName: 'reports',
    items: [
      { title: 'Панель отчётов', description: 'Финансы, прибыльность продаж, товаров и закупок.', routeName: 'reports', roles: [UserRole.OWNER] },
      { title: 'Сверка', description: 'Контроль структурных и операционных расхождений.', routeName: 'reports-reconciliation', roles: [UserRole.OWNER] },
      { title: 'Обмен валют', description: 'Кассовые операции и FX-обмен.', routeName: 'finance-exchange', roles: [UserRole.OWNER] },
      { title: 'Отчёт инвестдоговора', description: 'Агрегация связанных приходов, капитала и прибыли.', contextual: true, roles: [UserRole.OWNER] },
      { title: 'Drill-down отчёты', description: 'Открываются из строк продаж и закупок.', contextual: true, roles: [UserRole.OWNER] },
    ],
  },
  {
    title: 'Контрагенты',
    description: 'Покупатели, поставщики, долги и партнёрский доступ.',
    icon: Users,
    primaryRouteName: 'customers',
    items: [
      { title: 'Покупатели', description: 'Долги клиентов и ручные погашения.', routeName: 'customers', roles: [UserRole.OWNER] },
      { title: 'Поставщики', description: 'Кредиторка и оплаты поставщикам.', routeName: 'suppliers', roles: [UserRole.OWNER] },
      { title: 'Инвесторы', description: 'Приглашения и доступ инвесторов бизнеса.', routeName: 'owner-investors', roles: [UserRole.OWNER] },
    ],
  },
  {
    title: 'Кабинет инвестора',
    description: 'Прозрачность капитала, прибыли и закупок инвестора.',
    icon: CircleDollarSign,
    primaryRouteName: 'investor-dashboard',
    items: [
      { title: 'Сводка инвестора', description: 'Капитал, прибыль, выплаты и остаток в товаре.', routeName: 'investor-dashboard', roles: [UserRole.INVESTOR] },
      { title: 'Мои инвестдоговоры', description: 'Договоры, остаток в бюджете, товар и прибыль.', routeName: 'investor-agreements', roles: [UserRole.INVESTOR] },
      { title: 'Инвесторский договор', description: 'Открывается из сводки инвестора.', contextual: true, roles: [UserRole.INVESTOR] },
      { title: 'Инвесторский приход', description: 'Открывается из сводки инвестора.', contextual: true, roles: [UserRole.INVESTOR] },
    ],
  },
  {
    title: 'Система',
    description: 'Настройки интерфейса, режимы работы и карта разделов.',
    icon: Settings,
    primaryRouteName: 'settings',
    items: [
      { title: 'Настройки', description: 'Тема, язык, режим кассира и быстрые входы.', routeName: 'settings', roles: [UserRole.OWNER, UserRole.CASHIER, UserRole.WAREHOUSE, UserRole.INVESTOR] },
      { title: 'Карта разделов', description: 'Текущий экран со структурой продукта.', routeName: 'settings-page-map', roles: [UserRole.OWNER, UserRole.CASHIER, UserRole.WAREHOUSE, UserRole.INVESTOR] },
    ],
  },
]

const visibleSections = computed(() => sections)

function canSee(roles: UserRole[]): boolean {
  return Boolean(auth.role && roles.includes(auth.role))
}

function canOpenItem(item: PageMapItem): boolean {
  return Boolean(item.routeName && !item.contextual && canSee(item.roles))
}

function canOpenSection(section: PageMapSection): boolean {
  const primaryItem = section.items.find((item) => item.routeName === section.primaryRouteName)
  return Boolean(primaryItem && canOpenItem(primaryItem))
}

function rolesLabel(roles: UserRole[]): string {
  const labels: Record<UserRole, string> = {
    [UserRole.OWNER]: 'owner',
    [UserRole.CASHIER]: 'cashier',
    [UserRole.WAREHOUSE]: 'warehouse',
    [UserRole.INVESTOR]: 'investor',
  }
  return roles.map((role) => labels[role]).join(' / ')
}

function openRoute(routeName: string): void {
  router.push({ name: routeName })
}

function openItem(item: PageMapItem): void {
  if (!canOpenItem(item) || !item.routeName) return
  openRoute(item.routeName)
}
</script>

<template>
  <div class="page-map">
    <header class="page-header">
      <button class="back-btn" type="button" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>
      <h1 class="page-title">Карта разделов</h1>
      <div class="header-spacer" />
    </header>

    <main class="content">
      <section class="intro">
        <div class="intro-icon">
          <Map :size="20" :stroke-width="1.8" />
        </div>
        <div>
          <h2>Что где находится</h2>
          <p>Основные разделы открываются напрямую. Контекстные экраны появляются из конкретной продажи, товара или прихода.</p>
        </div>
      </section>

      <section v-for="section in visibleSections" :key="section.title" class="map-section">
        <div class="section-head">
          <span class="section-icon"><component :is="section.icon" :size="17" :stroke-width="1.75" /></span>
          <div class="section-copy">
            <h3>{{ section.title }}</h3>
            <p>{{ section.description }}</p>
          </div>
          <button
            v-if="section.primaryRouteName && canOpenSection(section)"
            class="section-open"
            type="button"
            :aria-label="`Открыть ${section.title}`"
            @click="openRoute(section.primaryRouteName)"
          >
            Открыть
          </button>
        </div>

        <div class="page-list">
          <article v-for="item in section.items" :key="`${section.title}-${item.title}`" class="page-row">
            <span class="page-marker" :class="{ 'page-marker--context': item.contextual }">
              <LockKeyhole v-if="item.contextual" :size="13" :stroke-width="1.8" />
              <ReceiptText v-else-if="section.title === 'Отчёты'" :size="13" :stroke-width="1.8" />
              <Boxes v-else :size="13" :stroke-width="1.8" />
            </span>
            <span class="page-copy">
              <strong>{{ item.title }}</strong>
              <span>{{ item.description }}</span>
              <em>{{ rolesLabel(item.roles) }}</em>
            </span>
            <button
              v-if="canOpenItem(item)"
              class="page-open"
              type="button"
              :aria-label="`Открыть ${item.title}`"
              @click="openItem(item)"
            >
              Перейти
            </button>
            <span v-else class="context-label">{{ item.contextual ? 'из контекста' : 'нет доступа' }}</span>
          </article>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.page-map {
  min-height: 100%;
  background: var(--color-bg-primary);
}

.page-header {
  position: sticky;
  top: 0;
  z-index: var(--z-sticky);
  display: grid;
  grid-template-columns: 40px 1fr 40px;
  align-items: center;
  gap: var(--space-3);
  min-height: var(--header-height);
  padding: 0 var(--space-4);
  border-bottom: 1px solid var(--color-border-subtle);
  background: var(--color-bg-primary);
}

.page-title {
  color: var(--color-text-primary);
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  text-align: center;
}

.back-btn,
.header-spacer {
  width: 40px;
  height: 40px;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  color: var(--color-text-primary);
}

.content {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-4);
  padding-bottom: calc(var(--bottom-nav-height) + var(--space-8));
}

.intro {
  display: flex;
  gap: var(--space-3);
  padding: var(--space-4) 0 var(--space-2);
}

.intro-icon,
.section-icon,
.page-marker {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.intro-icon {
  width: 42px;
  height: 42px;
  border-radius: var(--radius-lg);
  background: var(--color-brand-50);
  color: var(--color-brand-600);
}

.intro h2,
.section-copy h3 {
  margin: 0;
  color: var(--color-text-primary);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
}

.intro p,
.section-copy p,
.page-copy span,
.page-copy em {
  margin: var(--space-1) 0 0;
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  line-height: var(--leading-normal);
}

.page-copy em {
  margin-top: 0;
  color: var(--color-text-tertiary);
  font-style: normal;
}

.map-section {
  display: grid;
  gap: var(--space-3);
  padding: var(--space-3) 0;
  border-top: 1px solid var(--color-border-subtle);
}

.section-head {
  display: grid;
  grid-template-columns: 36px 1fr auto;
  align-items: start;
  gap: var(--space-3);
}

.section-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  color: var(--color-brand-600);
}

.section-copy {
  min-width: 0;
}

.section-open,
.page-open {
  min-height: 32px;
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-secondary);
  color: var(--color-brand-700);
  padding: 0 var(--space-3);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
}

.page-list {
  display: grid;
  gap: 1px;
  overflow: hidden;
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  background: var(--color-border-subtle);
}

.page-row {
  display: grid;
  grid-template-columns: 28px 1fr auto;
  align-items: center;
  gap: var(--space-2);
  min-height: 58px;
  padding: var(--space-2) var(--space-3);
  background: var(--color-bg-elevated);
}

.page-marker {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-md);
  background: var(--color-brand-50);
  color: var(--color-brand-600);
}

.page-marker--context {
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
}

.page-copy {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.page-copy strong {
  color: var(--color-text-primary);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
}

.context-label {
  color: var(--color-text-tertiary);
  font-size: var(--text-xs);
  white-space: nowrap;
}
</style>
