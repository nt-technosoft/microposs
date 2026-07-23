<script setup lang="ts">
import { computed } from 'vue'
import type { Component } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
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
  KeyRound,
} from 'lucide-vue-next'
import { useUIStore } from '@/stores/ui'
import { useAuthStore } from '@/stores/auth'
import { supportedLocales, type Locale } from '@/i18n/keys'
import { updateUserPreferences } from '@/api/auth'
import { useToast } from '@/composables/useToast'
import BaseButton from '@/components/base/BaseButton.vue'
import PageChrome from '@/components/layout/PageChrome.vue'
import ResponsiveFlowColumns from '@/components/layout/ResponsiveFlowColumns.vue'

const router = useRouter()
const { t } = useI18n()
const ui = useUIStore()
const auth = useAuthStore()
const toast = useToast()

const localeOptions = supportedLocales

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
    name: t('settings.quickLinks.pageMap'),
    description: t('settings.quickLinks.pageMapDescription'),
    routeName: 'settings-page-map',
    icon: Map,
  })

  if (auth.role === 'owner' || auth.role === 'cashier') {
    links.push({
      name: t('settings.quickLinks.salesHistory'),
      description: t('settings.quickLinks.salesHistoryDescription'),
      routeName: 'sales-history',
      icon: History,
    })
  }

  if (auth.role === 'owner' || auth.role === 'warehouse') {
    links.push({
      name: t('settings.quickLinks.transfers'),
      description: t('settings.quickLinks.transfersDescription'),
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
      name: t('settings.quickLinks.customers'),
      description: t('settings.quickLinks.customersDescription'),
      routeName: 'customers',
      icon: Users,
    },
    {
      name: t('settings.quickLinks.suppliers'),
      description: t('settings.quickLinks.suppliersDescription'),
      routeName: 'suppliers',
      icon: Truck,
    },
    {
      name: t('settings.quickLinks.categories'),
      description: t('settings.quickLinks.categoriesDescription'),
      routeName: 'categories',
      icon: FolderTree,
    },
    {
      name: t('settings.quickLinks.exchange'),
      description: t('settings.quickLinks.exchangeDescription'),
      routeName: 'finance-exchange',
      icon: Wallet,
    },
    {
      name: t('settings.quickLinks.reconciliation'),
      description: t('settings.quickLinks.reconciliationDescription'),
      routeName: 'reports-reconciliation',
      icon: Scale,
    },
    {
      name: t('settings.quickLinks.integrations'),
      description: t('settings.quickLinks.integrationsDescription'),
      routeName: 'integrations',
      icon: KeyRound,
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

async function changeLocale(locale: Locale): Promise<void> {
  ui.setLocale(locale)
  try {
    await updateUserPreferences({ locale })
    toast.success(t('settings.languageSaved'))
  } catch {
    toast.warning(t('settings.languageSaveFailed'))
  }
}
</script>

<template>
  <div class="settings-page">
    <PageChrome :title="t('settings.title')" :eyebrow="t('nav.settings')">
      <template #primary>
        <button class="back-btn" type="button" :aria-label="t('common.back')" @click="router.back()">
          <ArrowLeft :size="18" :stroke-width="2" />
        </button>
      </template>
    </PageChrome>

    <main class="content">
      <section class="card">
        <h2 class="section-title">Профиль и бизнес</h2>
        <div class="setting-row vertical">
          <div class="setting-meta">
            <div class="setting-name">{{ auth.user?.full_name || auth.user?.username }}</div>
            <div class="setting-desc">Пользователь · роль {{ auth.role || '—' }}</div>
          </div>
          <div class="identity-grid">
            <div>
              <span class="identity-label">Активный бизнес</span>
              <strong>{{ auth.user?.active_business?.name || auth.user?.tenant_name || 'не выбран' }}</strong>
            </div>
            <div>
              <span class="identity-label">Валюта</span>
              <strong>{{ auth.user?.active_business?.currency || '—' }}</strong>
            </div>
            <div>
              <span class="identity-label">Бизнесов</span>
              <strong>{{ auth.user?.owned_businesses.length ?? 0 }}</strong>
            </div>
            <div>
              <span class="identity-label">Профилей партнёра</span>
              <strong>{{ auth.user?.partner_profiles.length ?? 0 }}</strong>
            </div>
          </div>
          <p v-if="auth.user?.tenant_issue" class="tenant-warning">
            У аккаунта несколько активных бизнесов. Для MVP нужен явный контекст входа, поэтому данные бизнеса не выбираются автоматически.
          </p>
        </div>
      </section>

      <ResponsiveFlowColumns class="settings-flow">
        <section class="card">
          <h2 class="section-title">{{ t('settings.appearance') }}</h2>
          <div class="setting-row">
            <div class="setting-meta">
              <div class="setting-name">{{ t('settings.theme') }}</div>
              <div class="setting-desc">{{ t('settings.themeDescription') }}</div>
            </div>
            <button class="toggle-btn" type="button" @click="ui.toggleTheme()">
              <Sun v-if="!isDark" :size="16" :stroke-width="1.75" />
              <Moon v-else :size="16" :stroke-width="1.75" />
              <span>{{ isDark ? t('settings.darkTheme') : t('settings.lightTheme') }}</span>
            </button>
          </div>
        </section>

        <section class="card">
          <h2 class="section-title">{{ t('settings.localization') }}</h2>
          <div class="setting-row vertical">
            <div class="setting-meta">
              <div class="setting-name">{{ t('settings.language') }}</div>
              <div class="setting-desc">{{ t('settings.languageDescription') }}</div>
            </div>
            <div class="locale-grid" role="group" :aria-label="t('settings.language')">
              <button
                v-for="option in localeOptions"
                :key="option.value"
                class="locale-btn"
                :class="{ active: ui.locale === option.value }"
                type="button"
                @click="changeLocale(option.value)"
              >
                <Languages :size="14" :stroke-width="1.75" />
                {{ option.label }}
              </button>
            </div>
          </div>
        </section>

        <section class="card">
          <h2 class="section-title">{{ t('settings.modes') }}</h2>
          <div class="setting-row">
            <div class="setting-meta">
              <div class="setting-name">{{ t('settings.cashierMode') }}</div>
              <div class="setting-desc">{{ t('settings.cashierModeDescription') }}</div>
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
          <h2 class="section-title">{{ t('settings.workspace') }}</h2>
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
          <h2 class="section-title">{{ t('settings.management') }}</h2>
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
          <h2 class="section-title">{{ t('settings.partnership') }}</h2>
          <button class="nav-row" type="button" @click="router.push({ name: 'owner-investors' })">
            <span class="nav-icon"><Users :size="16" :stroke-width="1.75" /></span>
            <span class="setting-meta">
              <span class="setting-name">{{ t('settings.quickLinks.investors') }}</span>
              <span class="setting-desc">{{ t('settings.quickLinks.investorsDescription') }}</span>
            </span>
          </button>
        </section>
      </ResponsiveFlowColumns>

      <section class="card danger">
        <h2 class="section-title">{{ t('settings.session') }}</h2>
        <div class="logout-wrap">
          <BaseButton type="button" variant="danger" size="md" :full-width="true" @click="handleLogout">
            <LogOut :size="16" :stroke-width="2" />
            <span>{{ t('settings.logout') }}</span>
          </BaseButton>
          <p class="hint">
            <ShieldCheck :size="14" :stroke-width="1.75" />
            {{ t('settings.logoutHint') }}
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

.identity-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
  width: 100%;
}

.identity-grid > div {
  border: 1px solid var(--color-border);
  border-radius: 0.875rem;
  padding: 0.75rem;
  background: var(--color-bg-secondary);
}

.identity-label {
  display: block;
  margin-bottom: 0.25rem;
  color: var(--color-text-secondary);
  font-size: 0.75rem;
}

.tenant-warning {
  color: var(--color-warning);
  font-size: 0.8125rem;
  line-height: 1.45;
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

@media (min-width: 768px) {
  .content { max-width:1120px; margin:0 auto; padding:var(--space-6); padding-bottom:var(--space-8); }
}

@media (min-width: 1280px) {
  .settings-page { background: transparent; }
  .content { max-width:none; margin:0; padding-inline:var(--space-8); }
  .content > .card:first-child .setting-row.vertical {
    grid-template-columns: minmax(13rem, 0.35fr) minmax(0, 1fr);
    align-items: start;
    gap: var(--space-6);
  }
  .content > .card:first-child .identity-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
  .content > .card:first-child .tenant-warning {
    grid-column: 1 / -1;
  }
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
