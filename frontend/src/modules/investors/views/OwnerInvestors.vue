<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, Copy, Link, RefreshCcw, Send } from 'lucide-vue-next'
import {
  createInvestorInvite,
  fetchInvestorInvites,
  fetchInvestorRelations,
  type InvestorInvite,
  type InvestorRelation,
} from '@/api/core'
import { useToast } from '@/composables/useToast'
import { intlLocale } from '@/i18n/format'
import PageChrome from '@/components/layout/PageChrome.vue'

const router = useRouter()
const toast = useToast()
const { t, locale } = useI18n()

const relations = ref<InvestorRelation[]>([])
const invites = ref<InvestorInvite[]>([])
const displayName = ref('')
const email = ref('')
const isLoading = ref(true)
const isCreating = ref(false)
const errorMessage = ref('')

const activeRelations = computed(() =>
  relations.value.filter((relation) => relation.status === 'ACTIVE'),
)

const pendingInvites = computed(() =>
  invites.value.filter((invite) => invite.status === 'PENDING'),
)

function inviteUrl(invite: InvestorInvite): string {
  return `${window.location.origin}${invite.invite_path}`
}

async function copyInvite(invite: InvestorInvite): Promise<void> {
  await navigator.clipboard.writeText(inviteUrl(invite))
  toast.success(t('investors.copiedInvite'))
}

async function loadData(): Promise<void> {
  isLoading.value = true
  errorMessage.value = ''
  try {
    const [relationRows, inviteRows] = await Promise.all([
      fetchInvestorRelations(),
      fetchInvestorInvites(),
    ])
    relations.value = relationRows
    invites.value = inviteRows
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : t('investors.loadInvestorsFailed')
  } finally {
    isLoading.value = false
  }
}

async function createInvite(): Promise<void> {
  if (isCreating.value) return
  isCreating.value = true
  errorMessage.value = ''
  try {
    const invite = await createInvestorInvite({
      display_name: displayName.value.trim(),
      email: email.value.trim(),
    })
    invites.value = [invite, ...invites.value]
    displayName.value = ''
    email.value = ''
    await copyInvite(invite)
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : t('investors.createInviteFailed')
  } finally {
    isCreating.value = false
  }
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString(intlLocale(locale.value), {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

onMounted(loadData)
</script>

<template>
  <div class="investors-page">
    <PageChrome :title="t('investors.ownerTitle')" :eyebrow="t('settings.management')">
      <template #primary>
        <div class="page-header-actions">
          <button class="icon-btn" type="button" :aria-label="t('common.back')" @click="router.back()"><ArrowLeft :size="18" :stroke-width="2" /></button>
          <button class="icon-btn" type="button" :aria-label="t('common.refresh')" @click="loadData"><RefreshCcw :size="16" :stroke-width="1.75" /></button>
        </div>
      </template>
    </PageChrome>

    <main class="content">
      <section class="invite-panel">
        <div class="panel-copy">
          <h2>{{ t('investors.inviteInvestor') }}</h2>
          <p>{{ t('investors.inviteHint') }}</p>
        </div>
        <div class="invite-form">
          <input v-model="displayName" class="input-field" :placeholder="t('investors.investorName')" />
          <input v-model="email" class="input-field" type="email" :placeholder="t('investors.emailOptional')" />
          <button class="primary-btn" type="button" :disabled="isCreating" @click="createInvite">
            <Send :size="16" :stroke-width="2" />
            <span>{{ isCreating ? t('investors.creatingInvite') : t('investors.createInviteLink') }}</span>
          </button>
        </div>
      </section>

      <div v-if="errorMessage" class="error-box">{{ errorMessage }}</div>

      <div class="investor-workspace">
        <section class="section investor-workspace__relations">
          <h2 class="section-title">{{ t('investors.linkedInvestors') }}</h2>
          <div v-if="isLoading" class="muted">{{ t('investors.loading') }}</div>
          <div v-else-if="activeRelations.length === 0" class="muted">{{ t('investors.noActiveInvestors') }}</div>
          <div v-else class="list">
            <article v-for="relation in activeRelations" :key="relation.id" class="row-item">
              <div>
                <strong>{{ relation.partner_name }}</strong>
                <span>{{ relation.source === 'INVITE' ? t('investors.inviteSource') : t('investors.manualSource') }}</span>
              </div>
              <span class="status active">{{ t('investors.active') }}</span>
            </article>
          </div>
        </section>

        <aside class="investor-workspace__context">
          <section class="section section--pending">
            <h2 class="section-title">{{ t('investors.pendingInvites') }}</h2>
            <div v-if="pendingInvites.length === 0" class="muted">{{ t('investors.noPendingInvites') }}</div>
            <div v-else class="list">
              <article v-for="invite in pendingInvites" :key="invite.id" class="row-item">
                <div>
                  <strong>{{ invite.display_name || invite.email || t('investors.investorFallback') }}</strong>
                  <span>{{ t('investors.expiresAt', { date: formatDate(invite.expires_at) }) }}</span>
                </div>
                <button class="copy-btn" type="button" @click="copyInvite(invite)">
                  <Copy :size="15" :stroke-width="2" />
                  <span>{{ t('investors.copy') }}</span>
                </button>
              </article>
            </div>
          </section>

          <section class="section section--note">
            <div class="note-row">
              <Link :size="16" :stroke-width="1.75" />
              <span>{{ t('investors.accessNote') }}</span>
            </div>
          </section>
        </aside>
      </div>
    </main>
  </div>
</template>

<style scoped>
.investors-page { min-height: 100%; background: var(--color-bg-primary); }
.page-header-actions { display:flex; align-items:center; gap:var(--space-2); }
.icon-btn { width: 40px; height: 40px; display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radius-md); color: var(--color-text-primary); }
.content { display: grid; gap: var(--space-4); padding: var(--space-4); padding-bottom: calc(var(--bottom-nav-height) + var(--space-8)); }
.invite-panel { display: grid; gap: var(--space-4); padding: var(--space-4); border-radius: var(--radius-lg); background: var(--color-bg-elevated); border: 1px solid var(--color-border-subtle); }
.panel-copy h2, .section-title { font-size: var(--text-base); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.panel-copy p, .muted, .row-item span, .note-row { margin-top: 4px; font-size: var(--text-sm); color: var(--color-text-secondary); line-height: var(--leading-normal); }
.invite-form, .section, .list { display: grid; gap: var(--space-2); }
.investor-workspace, .investor-workspace__context { display: grid; gap: var(--space-4); }
.input-field { min-height: 44px; border-radius: var(--radius-md); border: 1px solid var(--color-border-default); background: var(--color-bg-primary); color: var(--color-text-primary); padding: 0 var(--space-3); font-size: var(--text-sm); }
.primary-btn, .copy-btn { min-height: 42px; display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2); border-radius: var(--radius-md); font-weight: var(--font-semibold); }
.primary-btn { background: var(--color-brand-500); color: var(--color-text-inverse); }
.primary-btn:disabled { opacity: .65; }
.copy-btn { padding: 0 var(--space-3); border: 1px solid var(--color-border-default); color: var(--color-text-primary); }
.row-item { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); min-height: 64px; border-bottom: 1px solid var(--color-border-subtle); }
.row-item strong { display: block; color: var(--color-text-primary); font-size: var(--text-sm); }
.status { border-radius: var(--radius-full); padding: 3px var(--space-2); font-size: var(--text-xs); font-weight: var(--font-semibold); }
.status.active { color: var(--color-success); background: var(--color-success-bg); }
.note-row { display: flex; align-items: center; gap: var(--space-2); margin-top: 0; }
.error-box { border-radius: var(--radius-md); border: 1px solid var(--color-error); background: var(--color-error-bg); color: var(--color-error); padding: var(--space-3); font-size: var(--text-sm); }
@media (min-width:768px) {
  .content { max-width:1120px; margin:0 auto; padding:var(--space-6); padding-bottom:var(--space-8); }
  .invite-panel { grid-template-columns:minmax(220px, .7fr) minmax(0, 1.3fr); align-items:start; }
  .invite-form { grid-template-columns:repeat(2, minmax(0, 1fr)); }
  .invite-form .primary-btn { grid-column:1 / -1; justify-self:end; padding-inline:var(--space-5); }
}
@media (min-width:1024px) {
  .content { max-width:none; margin:0; padding-inline:var(--space-8); }
  .invite-panel { grid-template-columns:minmax(220px, .75fr) minmax(0, 1.65fr); }
  .invite-form { grid-template-columns:minmax(0, 1fr) minmax(0, 1fr) auto; align-items:center; }
  .invite-form .primary-btn { grid-column:auto; justify-self:stretch; padding-inline:var(--space-4); }
  .investor-workspace { grid-template-columns:minmax(0, 2fr) minmax(280px, 1fr); align-items:start; gap:var(--space-6); }
  .investor-workspace__relations { min-width:0; }
  .investor-workspace__context { align-content:start; gap:var(--space-4); }
  .section--pending { border-left:1px solid var(--color-border-subtle); padding-left:var(--space-6); }
  .section--note { border-left:1px solid var(--color-border-subtle); padding-left:var(--space-6); }
}
@media (min-width:1280px) {
  .investors-page { background:transparent; }
}
</style>
