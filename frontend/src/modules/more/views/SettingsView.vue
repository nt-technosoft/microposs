<script setup lang="ts">
import { computed } from 'vue'
import type { Component } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowLeft,
  Moon,
  Sun,
  Languages,
  ShieldCheck,
  LogOut,
  Users,
  History,
  ArrowRightLeft,
  FolderTree,
  Wallet,
  Scale,
  Truck,
  Map,
} from 'lucide-vue-next'
import { useUIStore } from '@/stores/ui'
import { useAuthStore } from '@/stores/auth'
import BaseButton from '@/components/base/BaseButton.vue'

const router = useRouter()
const ui = useUIStore()
const auth = useAuthStore()

const localeOptions = [
  { value: 'ru', label: 'Русский' },
  { value: 'uz', label: 'Узбекский' },
  { value: 'en', label: 'Английский' },
] as const

interface QuickLink {
  name: string
  description: string
  routeName: string
  icon: Component
}

const isDark = computed(() => ui.theme === 'dark')

const workspaceLinks = computed<QuickLink[]>(() => {
  const links: QuickLink[] = []

  links.push({
    name: 'Карта разделов',
    description: 'Что где находится и какие экраны открываются из контекста',
    routeName: 'settings-page-map',
    icon: Map,
  })

  if (auth.role === 'owner' || auth.role === 'cashier') {
    links.push({
      name: 'История продаж',
      description: 'Все продажи за смену и детали чеков',
      routeName: 'sales-history',
      icon: History,
    })
  }

  if (auth.role === 'owner' || auth.role === 'warehouse') {
    links.push({
      name: 'Перемещения',
      description: 'Переводы товаров между точками',
      routeName: 'stock-transfers',
      icon: ArrowRightLeft,
    })
  }

  return links
})

const managementLinks = computed<QuickLink[]>(() => {
  if (!auth.isOwner) return []

  return [
    {
      name: 'Покупатели',
      description: 'Долги клиентов и ручные погашения',
      routeName: 'customers',
      icon: Users,
    },
    {
      name: 'Поставщики',
      description: 'Кредиторка и оплаты поставщикам',
      routeName: 'suppliers',
      icon: Truck,
    },
    {
      name: 'Категории',
      description: 'Структура каталога и шаблоны атрибутов',
      routeName: 'categories',
      icon: FolderTree,
    },
    {
      name: 'Обмен валют',
      description: 'Кассовые операции и FX-обмен',
      routeName: 'finance-exchange',
      icon: Wallet,
    },
    {
      name: 'Сверка',
      description: 'Контроль остатков и расхождений',
      routeName: 'reports-reconciliation',
      icon: Scale,
    },
  ]
})

function openQuickLink(routeName: string): void {
  router.push({ name: routeName })
}

function handleLogout(): void {
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="settings-page">
    <header class="page-header">
      <button class="back-btn" type="button" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>
      <h1 class="page-title">Настройки</h1>
      <div class="header-spacer" />
    </header>

    <main class="content">
      <section class="card">
        <h2 class="section-title">Внешний вид</h2>
        <div class="setting-row">
          <div class="setting-meta">
            <div class="setting-name">Тема</div>
            <div class="setting-desc">Светлая или тёмная тема интерфейса</div>
          </div>
          <button class="toggle-btn" type="button" @click="ui.toggleTheme()">
            <Sun v-if="!isDark" :size="16" :stroke-width="1.75" />
            <Moon v-else :size="16" :stroke-width="1.75" />
            <span>{{ isDark ? 'Тёмная' : 'Светлая' }}</span>
          </button>
        </div>
      </section>

      <section class="card">
        <h2 class="section-title">Локализация</h2>
        <div class="setting-row vertical">
          <div class="setting-meta">
            <div class="setting-name">Язык интерфейса</div>
            <div class="setting-desc">Язык подписей и системных текстов</div>
          </div>
          <div class="locale-grid" role="group" aria-label="Выбор языка">
            <button
              v-for="option in localeOptions"
              :key="option.value"
              class="locale-btn"
              :class="{ active: ui.locale === option.value }"
              type="button"
              @click="ui.setLocale(option.value)"
            >
              <Languages :size="14" :stroke-width="1.75" />
              {{ option.label }}
            </button>
          </div>
        </div>
      </section>

      <section class="card">
        <h2 class="section-title">Режимы работы</h2>
        <div class="setting-row">
          <div class="setting-meta">
            <div class="setting-name">Режим кассира</div>
            <div class="setting-desc">Оставляет только продажи и скрывает остальные разделы</div>
          </div>
          <label class="switch">
            <input
              :checked="ui.simpleSellerMode"
              type="checkbox"
              @change="ui.setSimpleSellerMode(($event.target as HTMLInputElement).checked)"
            />
            <span class="slider" />
          </label>
        </div>
      </section>

      <section v-if="workspaceLinks.length > 0" class="card">
        <h2 class="section-title">Рабочие разделы</h2>
        <div class="nav-list">
          <button
            v-for="link in workspaceLinks"
            :key="link.routeName"
            class="nav-row"
            type="button"
            @click="openQuickLink(link.routeName)"
          >
            <span class="nav-icon"><component :is="link.icon" :size="16" :stroke-width="1.75" /></span>
            <span class="setting-meta">
              <span class="setting-name">{{ link.name }}</span>
              <span class="setting-desc">{{ link.description }}</span>
            </span>
          </button>
        </div>
      </section>

      <section v-if="managementLinks.length > 0" class="card">
        <h2 class="section-title">Справочники и контроль</h2>
        <div class="nav-list">
          <button
            v-for="link in managementLinks"
            :key="link.routeName"
            class="nav-row"
            type="button"
            @click="openQuickLink(link.routeName)"
          >
            <span class="nav-icon"><component :is="link.icon" :size="16" :stroke-width="1.75" /></span>
            <span class="setting-meta">
              <span class="setting-name">{{ link.name }}</span>
              <span class="setting-desc">{{ link.description }}</span>
            </span>
          </button>
        </div>
      </section>

      <section v-if="auth.isOwner" class="card">
        <h2 class="section-title">Партнёрство</h2>
        <button class="nav-row" type="button" @click="router.push({ name: 'owner-investors' })">
          <span class="nav-icon"><Users :size="16" :stroke-width="1.75" /></span>
          <span class="setting-meta">
            <span class="setting-name">Инвесторы</span>
            <span class="setting-desc">Приглашения и доступные инвесторы бизнеса</span>
          </span>
        </button>
      </section>

      <section class="card danger">
        <h2 class="section-title">Сессия</h2>
        <div class="logout-wrap">
          <BaseButton type="button" variant="danger" size="md" :full-width="true" @click="handleLogout">
            <LogOut :size="16" :stroke-width="2" />
            <span>Выйти из системы</span>
          </BaseButton>
          <p class="hint">
            <ShieldCheck :size="14" :stroke-width="1.75" />
            Доступ к защищённым разделам будет закрыт до повторного входа.
          </p>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.settings-page {
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
  text-align: center;
  font-size: var(--text-lg);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
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

.card {
  background: var(--color-bg-elevated);
  border: 1px solid var(--color-border-subtle);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
}

.card.danger {
  border-color: var(--color-error-bg);
}

.section-title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
  margin-bottom: var(--space-3);
}

.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
}

.nav-row {
  width: 100%;
  min-height: 48px;
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  text-align: left;
  padding: var(--space-1) 0;
}

.nav-list {
  display: grid;
  gap: var(--space-2);
}

.nav-icon {
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md);
  background: var(--color-bg-secondary);
  color: var(--color-brand-600);
  flex-shrink: 0;
}

.setting-row.vertical {
  display: grid;
  gap: var(--space-3);
}

.setting-meta {
  min-width: 0;
  flex: 1;
  display: grid;
  gap: 2px;
}

.setting-name {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.setting-desc {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: var(--leading-normal);
}

.toggle-btn {
  min-height: 36px;
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-secondary);
  color: var(--color-text-primary);
  padding: 0 var(--space-3);
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

.locale-grid {
  display: grid;
  gap: var(--space-2);
}

.locale-btn {
  min-height: 40px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-secondary);
  color: var(--color-text-secondary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

.locale-btn.active {
  border-color: var(--color-brand-400);
  color: var(--color-brand-600);
  background: var(--color-brand-50);
}

.switch {
  position: relative;
  display: inline-flex;
  width: 44px;
  height: 24px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  background: var(--color-bg-sunken);
  border: 1px solid var(--color-border-default);
  transition: background var(--duration-fast) var(--ease-out);
}

.slider::before {
  content: '';
  position: absolute;
  width: 18px;
  height: 18px;
  left: 2px;
  top: 2px;
  border-radius: 50%;
  background: #fff;
  box-shadow: var(--shadow-sm);
  transition: transform var(--duration-fast) var(--ease-spring);
}

.switch input:checked + .slider {
  background: var(--color-brand-500);
  border-color: var(--color-brand-500);
}

.switch input:checked + .slider::before {
  transform: translateX(20px);
}

.logout-wrap {
  display: grid;
  gap: var(--space-2);
}

.hint {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
}
</style>
