<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  CheckCircle2,
  LayoutDashboard,
  LogOut,
  RefreshCw,
  ShieldCheck,
  Store,
  Users,
  XCircle,
} from 'lucide-vue-next'
import BaseButton from '@/components/base/BaseButton.vue'
import {
  approveBusinessRegistrationRequest,
  fetchBusinessRegistrationRequests,
  rejectBusinessRegistrationRequest,
  type BusinessRegistrationRequest,
  type BusinessRegistrationRequestStatus,
} from '@/api/core'
import { useAuthStore } from '@/stores/auth'
import { intlLocale } from '@/i18n/format'

type FilterValue = 'ALL' | BusinessRegistrationRequestStatus

const router = useRouter()
const auth = useAuthStore()
const { t, locale } = useI18n()

const requests = ref<BusinessRegistrationRequest[]>([])
const isLoading = ref(false)
const loadError = ref('')
const actionId = ref<number | null>(null)
const filter = ref<FilterValue>('PENDING')

const filterOptions = computed<Array<{ value: FilterValue, label: string }>>(() => [
  { value: 'PENDING', label: t('platformAdmin.filter.pending') },
  { value: 'APPROVED', label: t('platformAdmin.filter.approved') },
  { value: 'REJECTED', label: t('platformAdmin.filter.rejected') },
  { value: 'ALL', label: t('platformAdmin.filter.all') },
])

const statusMeta = computed<Record<BusinessRegistrationRequestStatus, { label: string, tone: string }>>(() => ({
  PENDING: { label: t('platformAdmin.status.pending'), tone: 'pending' },
  APPROVED: { label: t('platformAdmin.status.approved'), tone: 'approved' },
  REJECTED: { label: t('platformAdmin.status.rejected'), tone: 'rejected' },
}))

const futureSections = computed(() => [
  { label: t('platformAdmin.sections.requests'), icon: ShieldCheck, active: true },
  { label: t('platformAdmin.sections.businesses'), icon: Store, active: false },
  { label: t('platformAdmin.sections.investors'), icon: Users, active: false },
  { label: t('platformAdmin.sections.dashboard'), icon: LayoutDashboard, active: false },
])

const pendingCount = computed(() => requests.value.filter((item) => item.status === 'PENDING').length)
const approvedCount = computed(() => requests.value.filter((item) => item.status === 'APPROVED').length)
const rejectedCount = computed(() => requests.value.filter((item) => item.status === 'REJECTED').length)

const visibleRequests = computed(() => {
  const rank: Record<BusinessRegistrationRequestStatus, number> = {
    PENDING: 0,
    APPROVED: 1,
    REJECTED: 2,
  }

  return [...requests.value]
    .filter((item) => filter.value === 'ALL' || item.status === filter.value)
    .sort((left, right) => {
      const statusDiff = rank[left.status] - rank[right.status]
      if (statusDiff !== 0) return statusDiff
      return new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
    })
})

function formatDateTime(value: string | null) {
  if (!value) return '—'
  return new Intl.DateTimeFormat(intlLocale(locale.value), {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

async function loadRequests() {
  isLoading.value = true
  loadError.value = ''

  try {
    requests.value = await fetchBusinessRegistrationRequests()
  } catch {
    loadError.value = t('platformAdmin.loadFailed')
  } finally {
    isLoading.value = false
  }
}

function replaceRequest(updated: BusinessRegistrationRequest) {
  requests.value = requests.value.map((item) => (item.id === updated.id ? updated : item))
}

async function approveRequest(requestItem: BusinessRegistrationRequest) {
  if (actionId.value !== null) return
  actionId.value = requestItem.id

  try {
    const updated = await approveBusinessRegistrationRequest(requestItem.id)
    replaceRequest(updated)
  } catch {
    loadError.value = t('platformAdmin.approveFailed')
  } finally {
    actionId.value = null
  }
}

async function rejectRequest(requestItem: BusinessRegistrationRequest) {
  if (actionId.value !== null) return
  const reason = window.prompt(t('platformAdmin.rejectionPrompt'), '')
  if (reason === null) return

  actionId.value = requestItem.id

  try {
    const updated = await rejectBusinessRegistrationRequest(requestItem.id, reason)
    replaceRequest(updated)
  } catch {
    loadError.value = t('platformAdmin.rejectFailed')
  } finally {
    actionId.value = null
  }
}

function logout() {
  auth.logout()
  router.push('/login')
}

onMounted(() => {
  loadRequests()
})
</script>

<template>
  <div class="platform-admin-page">
    <div class="platform-admin-shell">
      <section class="admin-hero">
        <div class="admin-hero__content">
          <span class="admin-hero__eyebrow">{{ t('platformAdmin.eyebrow') }}</span>
          <h1 class="admin-hero__title">{{ t('platformAdmin.title') }}</h1>
          <p class="admin-hero__text">
            {{ t('platformAdmin.text') }}
          </p>
        </div>

        <button type="button" class="logout-button" @click="logout">
          <LogOut :size="18" stroke-width="1.9" />
          <span>{{ t('platformAdmin.logout') }}</span>
        </button>
      </section>

      <section class="future-nav">
        <button
          v-for="section in futureSections"
          :key="section.label"
          type="button"
          class="future-nav__item"
          :class="{ 'future-nav__item--active': section.active }"
          :disabled="!section.active"
        >
          <component :is="section.icon" :size="16" stroke-width="1.8" />
          <span>{{ section.label }}</span>
          <small v-if="!section.active">{{ t('platformAdmin.soon') }}</small>
        </button>
      </section>

      <section class="overview-strip">
        <article class="metric-card">
          <span class="metric-card__label">{{ t('platformAdmin.filter.pending') }}</span>
          <strong class="metric-card__value">{{ pendingCount }}</strong>
        </article>
        <article class="metric-card">
          <span class="metric-card__label">{{ t('platformAdmin.filter.approved') }}</span>
          <strong class="metric-card__value">{{ approvedCount }}</strong>
        </article>
        <article class="metric-card">
          <span class="metric-card__label">{{ t('platformAdmin.filter.rejected') }}</span>
          <strong class="metric-card__value">{{ rejectedCount }}</strong>
        </article>
      </section>

      <section class="workspace-panel">
        <div class="workspace-panel__top">
          <div class="filters">
            <button
              v-for="option in filterOptions"
              :key="option.value"
              type="button"
              class="filter-chip"
              :class="{ 'filter-chip--active': filter === option.value }"
              @click="filter = option.value"
            >
              {{ option.label }}
            </button>
          </div>

          <button type="button" class="refresh-button" @click="loadRequests">
            <RefreshCw :size="16" stroke-width="1.9" />
            <span>{{ t('common.refresh') }}</span>
          </button>
        </div>

        <p v-if="loadError" class="workspace-message workspace-message--error">{{ loadError }}</p>
        <p v-else-if="isLoading" class="workspace-message">{{ t('platformAdmin.loadingRequests') }}</p>
        <p v-else-if="visibleRequests.length === 0" class="workspace-message">{{ t('platformAdmin.noRequests') }}</p>

        <div v-else class="request-list">
          <article v-for="item in visibleRequests" :key="item.id" class="request-card">
            <div class="request-card__head">
              <div class="request-card__identity">
                <h2 class="request-card__title">{{ item.business_name }}</h2>
                <p class="request-card__subtitle">
                  {{ item.full_name || `${item.first_name} ${item.last_name}`.trim() || item.username }}
                </p>
              </div>
              <span class="status-pill" :class="`status-pill--${statusMeta[item.status].tone}`">
                {{ statusMeta[item.status].label }}
              </span>
            </div>

            <div class="request-card__details">
              <div class="detail-row">
                <span class="detail-row__label">{{ t('platformAdmin.login') }}</span>
                <span class="detail-row__value">{{ item.username }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-row__label">{{ t('platformAdmin.phone') }}</span>
                <span class="detail-row__value">{{ item.phone }}</span>
              </div>
              <div class="detail-row">
                <span class="detail-row__label">{{ t('platformAdmin.createdAt') }}</span>
                <span class="detail-row__value">{{ formatDateTime(item.created_at) }}</span>
              </div>
              <div v-if="item.reviewed_at" class="detail-row">
                <span class="detail-row__label">{{ t('platformAdmin.reviewedAt') }}</span>
                <span class="detail-row__value">{{ formatDateTime(item.reviewed_at) }}</span>
              </div>
              <div v-if="item.approved_business_name" class="detail-row">
                <span class="detail-row__label">{{ t('platformAdmin.createdBusiness') }}</span>
                <span class="detail-row__value">{{ item.approved_business_name }}</span>
              </div>
              <div v-if="item.rejection_reason" class="detail-row detail-row--stacked">
                <span class="detail-row__label">{{ t('platformAdmin.rejectionReason') }}</span>
                <span class="detail-row__value">{{ item.rejection_reason }}</span>
              </div>
            </div>

            <div v-if="item.status === 'PENDING'" class="request-card__actions">
              <BaseButton
                variant="secondary"
                :disabled="actionId === item.id"
                :loading="actionId === item.id"
                @click="rejectRequest(item)"
              >
                <XCircle :size="16" stroke-width="1.8" />
                {{ t('platformAdmin.reject') }}
              </BaseButton>
              <BaseButton
                :disabled="actionId === item.id"
                :loading="actionId === item.id"
                @click="approveRequest(item)"
              >
                <CheckCircle2 :size="16" stroke-width="1.8" />
                {{ t('platformAdmin.approve') }}
              </BaseButton>
            </div>
          </article>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.platform-admin-page {
  min-height: 100dvh;
  padding: var(--space-4);
  background:
    radial-gradient(circle at top left, rgba(21, 107, 86, 0.12), transparent 28%),
    linear-gradient(180deg, #f4f6f3 0%, #edf1ed 100%);
}

.platform-admin-shell {
  max-width: 680px;
  margin: 0 auto;
  display: grid;
  gap: var(--space-4);
}

.admin-hero,
.future-nav,
.overview-strip,
.workspace-panel {
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(20, 37, 31, 0.08);
  box-shadow: 0 10px 26px rgba(20, 37, 31, 0.05);
}

.admin-hero {
  border-radius: 28px;
  padding: var(--space-5);
  display: grid;
  gap: var(--space-4);
}

.admin-hero__content {
  display: grid;
  gap: var(--space-2);
}

.admin-hero__eyebrow {
  font-size: 11px;
  line-height: 1.1;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #156B56;
  font-weight: var(--font-semibold);
}

.admin-hero__title {
  margin: 0;
  font-size: clamp(1.8rem, 6vw, 2.5rem);
  line-height: 1;
  letter-spacing: -0.04em;
  color: #1d2520;
}

.admin-hero__text {
  margin: 0;
  font-size: var(--text-sm);
  line-height: 1.55;
  color: var(--color-text-secondary);
}

.logout-button,
.refresh-button {
  width: fit-content;
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  min-height: 42px;
  padding: 0 var(--space-3);
  border-radius: 14px;
  border: 1px solid rgba(20, 37, 31, 0.08);
  background: #fbfcfb;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.future-nav {
  border-radius: 24px;
  padding: var(--space-3);
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-2);
}

.future-nav__item {
  min-height: 52px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  border-radius: 16px;
  border: 1px solid rgba(20, 37, 31, 0.08);
  background: #f8faf8;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
}

.future-nav__item small {
  font-size: 10px;
  line-height: 1;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-tertiary);
}

.future-nav__item--active {
  border-color: rgba(21, 107, 86, 0.18);
  background: rgba(21, 107, 86, 0.07);
  color: #156B56;
}

.overview-strip {
  border-radius: 24px;
  padding: var(--space-3);
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-2);
}

.metric-card {
  padding: var(--space-3);
  border-radius: 18px;
  background: #f8faf8;
  border: 1px solid rgba(20, 37, 31, 0.06);
  display: grid;
  gap: 6px;
}

.metric-card__label {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.metric-card__value {
  font-size: 1.35rem;
  line-height: 1;
  color: #1d2520;
}

.workspace-panel {
  border-radius: 28px;
  padding: var(--space-4);
  display: grid;
  gap: var(--space-4);
}

.workspace-panel__top {
  display: grid;
  gap: var(--space-3);
}

.filters {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
}

.filter-chip {
  min-height: 36px;
  padding: 0 var(--space-3);
  border-radius: 999px;
  border: 1px solid rgba(20, 37, 31, 0.08);
  background: #f7faf7;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  cursor: pointer;
}

.filter-chip--active {
  background: #1d3d34;
  color: #ffffff;
  border-color: #1d3d34;
}

.workspace-message {
  margin: 0;
  padding: var(--space-4);
  border-radius: 18px;
  background: #f8faf8;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.workspace-message--error {
  background: rgba(217, 83, 79, 0.08);
  color: var(--color-error);
}

.request-list {
  display: grid;
  gap: var(--space-3);
}

.request-card {
  padding: var(--space-4);
  border-radius: 22px;
  border: 1px solid rgba(20, 37, 31, 0.08);
  background: #fbfcfb;
  display: grid;
  gap: var(--space-4);
}

.request-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}

.request-card__identity {
  min-width: 0;
  display: grid;
  gap: 6px;
}

.request-card__title {
  margin: 0;
  font-size: 1.1rem;
  line-height: 1.15;
  color: #1d2520;
}

.request-card__subtitle {
  margin: 0;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.status-pill {
  min-height: 28px;
  padding: 0 var(--space-3);
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  white-space: nowrap;
}

.status-pill--pending {
  color: #b57400;
  background: rgba(255, 191, 73, 0.14);
}

.status-pill--approved {
  color: #156B56;
  background: rgba(21, 107, 86, 0.12);
}

.status-pill--rejected {
  color: var(--color-error);
  background: rgba(217, 83, 79, 0.12);
}

.request-card__details {
  display: grid;
  gap: var(--space-2);
}

.detail-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  padding-bottom: var(--space-2);
  border-bottom: 1px solid rgba(20, 37, 31, 0.06);
}

.detail-row:last-child {
  padding-bottom: 0;
  border-bottom: none;
}

.detail-row--stacked {
  display: grid;
}

.detail-row__label {
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
}

.detail-row__value {
  font-size: var(--text-sm);
  color: #1d2520;
  text-align: right;
}

.detail-row--stacked .detail-row__value {
  text-align: left;
}

.request-card__actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-2);
}

@media (min-width: 768px) {
  .platform-admin-page {
    padding: var(--space-8);
  }

  .platform-admin-shell {
    gap: var(--space-5);
  }

  .admin-hero {
    padding: var(--space-6);
    grid-template-columns: 1fr auto;
    align-items: start;
  }

  .workspace-panel__top {
    grid-template-columns: 1fr auto;
    align-items: center;
  }

  .future-nav {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
</style>
