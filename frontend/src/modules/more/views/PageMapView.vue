<script setup lang="ts">
import type { Component } from 'vue'
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
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
const { t } = useI18n()

const sections = computed<PageMapSection[]>(() => [
  {
    title: t('pageMap.sections.sales.title'),
    description: t('pageMap.sections.sales.description'),
    icon: ShoppingBag,
    primaryRouteName: 'sales-catalog',
    items: [
      { title: t('pageMap.sections.sales.catalog'), description: t('pageMap.sections.sales.catalogDescription'), routeName: 'sales-catalog', roles: [UserRole.OWNER, UserRole.CASHIER] },
      { title: t('pageMap.sections.sales.cart'), description: t('pageMap.sections.sales.cartDescription'), contextual: true, roles: [UserRole.OWNER, UserRole.CASHIER] },
      { title: t('pageMap.sections.sales.history'), description: t('pageMap.sections.sales.historyDescription'), routeName: 'sales-history', roles: [UserRole.OWNER, UserRole.CASHIER] },
      { title: t('pageMap.sections.sales.audit'), description: t('pageMap.sections.sales.auditDescription'), contextual: true, roles: [UserRole.OWNER] },
    ],
  },
  {
    title: t('pageMap.sections.products.title'),
    description: t('pageMap.sections.products.description'),
    icon: Package,
    primaryRouteName: 'products',
    items: [
      { title: t('pageMap.sections.products.list'), description: t('pageMap.sections.products.listDescription'), routeName: 'products', roles: [UserRole.OWNER, UserRole.WAREHOUSE] },
      { title: t('pageMap.sections.products.create'), description: t('pageMap.sections.products.createDescription'), routeName: 'product-create', roles: [UserRole.OWNER] },
      { title: t('pageMap.sections.products.categories'), description: t('pageMap.sections.products.categoriesDescription'), routeName: 'categories', roles: [UserRole.OWNER] },
      { title: t('pageMap.sections.products.transfers'), description: t('pageMap.sections.products.transfersDescription'), routeName: 'stock-transfers', roles: [UserRole.OWNER, UserRole.WAREHOUSE] },
    ],
  },
  {
    title: t('pageMap.sections.procurements.title'),
    description: t('pageMap.sections.procurements.description'),
    icon: Download,
    primaryRouteName: 'procurement-list',
    items: [
      { title: t('pageMap.sections.procurements.list'), description: t('pageMap.sections.procurements.listDescription'), routeName: 'procurement-list', roles: [UserRole.OWNER, UserRole.WAREHOUSE] },
      { title: t('pageMap.sections.procurements.agreements'), description: t('pageMap.sections.procurements.agreementsDescription'), routeName: 'agreement-list', roles: [UserRole.OWNER] },
      { title: t('pageMap.sections.procurements.create'), description: t('pageMap.sections.procurements.createDescription'), routeName: 'procurement-create', roles: [UserRole.OWNER, UserRole.WAREHOUSE] },
      { title: t('pageMap.sections.procurements.agreementCreate'), description: t('pageMap.sections.procurements.agreementCreateDescription'), routeName: 'agreement-create', roles: [UserRole.OWNER] },
      { title: t('pageMap.sections.procurements.detail'), description: t('pageMap.sections.procurements.detailDescription'), contextual: true, roles: [UserRole.OWNER, UserRole.WAREHOUSE] },
      { title: t('pageMap.sections.procurements.agreementDetail'), description: t('pageMap.sections.procurements.agreementDetailDescription'), contextual: true, roles: [UserRole.OWNER] },
      { title: t('pageMap.sections.procurements.audit'), description: t('pageMap.sections.procurements.auditDescription'), contextual: true, roles: [UserRole.OWNER] },
    ],
  },
  {
    title: t('pageMap.sections.reports.title'),
    description: t('pageMap.sections.reports.description'),
    icon: BarChart3,
    primaryRouteName: 'reports',
    items: [
      { title: t('pageMap.sections.reports.dashboard'), description: t('pageMap.sections.reports.dashboardDescription'), routeName: 'reports', roles: [UserRole.OWNER] },
      { title: t('pageMap.sections.reports.reconciliation'), description: t('pageMap.sections.reports.reconciliationDescription'), routeName: 'reports-reconciliation', roles: [UserRole.OWNER] },
      { title: t('pageMap.sections.reports.exchange'), description: t('pageMap.sections.reports.exchangeDescription'), routeName: 'finance-exchange', roles: [UserRole.OWNER] },
      { title: t('pageMap.sections.reports.agreementReport'), description: t('pageMap.sections.reports.agreementReportDescription'), contextual: true, roles: [UserRole.OWNER] },
      { title: t('pageMap.sections.reports.drilldown'), description: t('pageMap.sections.reports.drilldownDescription'), contextual: true, roles: [UserRole.OWNER] },
    ],
  },
  {
    title: t('pageMap.sections.counterparties.title'),
    description: t('pageMap.sections.counterparties.description'),
    icon: Users,
    primaryRouteName: 'customers',
    items: [
      { title: t('pageMap.sections.counterparties.customers'), description: t('pageMap.sections.counterparties.customersDescription'), routeName: 'customers', roles: [UserRole.OWNER] },
      { title: t('pageMap.sections.counterparties.suppliers'), description: t('pageMap.sections.counterparties.suppliersDescription'), routeName: 'suppliers', roles: [UserRole.OWNER] },
      { title: t('pageMap.sections.counterparties.investors'), description: t('pageMap.sections.counterparties.investorsDescription'), routeName: 'owner-investors', roles: [UserRole.OWNER] },
    ],
  },
  {
    title: t('pageMap.sections.investor.title'),
    description: t('pageMap.sections.investor.description'),
    icon: CircleDollarSign,
    primaryRouteName: 'investor-dashboard',
    items: [
      { title: t('pageMap.sections.investor.dashboard'), description: t('pageMap.sections.investor.dashboardDescription'), routeName: 'investor-dashboard', roles: [UserRole.INVESTOR] },
      { title: t('pageMap.sections.investor.agreements'), description: t('pageMap.sections.investor.agreementsDescription'), routeName: 'investor-agreements', roles: [UserRole.INVESTOR] },
      { title: t('pageMap.sections.investor.funds'), description: t('pageMap.sections.investor.fundsDescription'), routeName: 'investor-funds', roles: [UserRole.INVESTOR] },
      { title: t('pageMap.sections.investor.agreement'), description: t('pageMap.sections.investor.agreementDescription'), contextual: true, roles: [UserRole.INVESTOR] },
      { title: t('pageMap.sections.investor.procurement'), description: t('pageMap.sections.investor.procurementDescription'), contextual: true, roles: [UserRole.INVESTOR] },
    ],
  },
  {
    title: t('pageMap.sections.system.title'),
    description: t('pageMap.sections.system.description'),
    icon: Settings,
    primaryRouteName: 'settings',
    items: [
      { title: t('pageMap.sections.system.settings'), description: t('pageMap.sections.system.settingsDescription'), routeName: 'settings', roles: [UserRole.OWNER, UserRole.CASHIER, UserRole.WAREHOUSE, UserRole.INVESTOR] },
      { title: t('pageMap.sections.system.map'), description: t('pageMap.sections.system.mapDescription'), routeName: 'settings-page-map', roles: [UserRole.OWNER, UserRole.CASHIER, UserRole.WAREHOUSE, UserRole.INVESTOR] },
    ],
  },
])

const visibleSections = sections

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
    [UserRole.PLATFORM_ADMIN]: 'platform_admin',
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
      <button class="back-btn" type="button" :aria-label="t('common.back')" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>
      <h1 class="page-title">{{ t('pageMap.title') }}</h1>
      <div class="header-spacer" />
    </header>

    <main class="content">
      <section class="intro">
        <div class="intro-icon">
          <Map :size="20" :stroke-width="1.8" />
        </div>
        <div>
          <h2>{{ t('pageMap.introTitle') }}</h2>
          <p>{{ t('pageMap.introText') }}</p>
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
            :aria-label="`${t('pageMap.open')} ${section.title}`"
            @click="openRoute(section.primaryRouteName)"
          >
            {{ t('pageMap.open') }}
          </button>
        </div>

        <div class="page-list">
          <article v-for="item in section.items" :key="`${section.title}-${item.title}`" class="page-row">
            <span class="page-marker" :class="{ 'page-marker--context': item.contextual }">
              <LockKeyhole v-if="item.contextual" :size="13" :stroke-width="1.8" />
              <ReceiptText v-else-if="section.primaryRouteName === 'reports'" :size="13" :stroke-width="1.8" />
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
              :aria-label="`${t('pageMap.open')} ${item.title}`"
              @click="openItem(item)"
            >
              {{ t('pageMap.go') }}
            </button>
            <span v-else class="context-label">{{ item.contextual ? t('pageMap.fromContext') : t('pageMap.noAccess') }}</span>
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
