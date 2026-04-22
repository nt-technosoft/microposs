<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Copy, Link, RefreshCcw, Send } from 'lucide-vue-next'
import {
  createInvestorInvite,
  fetchInvestorInvites,
  fetchInvestorRelations,
  type InvestorInvite,
  type InvestorRelation,
} from '@/api/core'
import { useToast } from '@/composables/useToast'

const router = useRouter()
const toast = useToast()

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
  toast.success('Ссылка скопирована')
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
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось загрузить инвесторов'
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
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось создать приглашение'
  } finally {
    isCreating.value = false
  }
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

onMounted(loadData)
</script>

<template>
  <div class="investors-page">
    <header class="page-header">
      <button class="icon-btn" type="button" aria-label="Назад" @click="router.back()">
        <ArrowLeft :size="18" :stroke-width="2" />
      </button>
      <h1 class="page-title">Инвесторы</h1>
      <button class="icon-btn" type="button" aria-label="Обновить" @click="loadData">
        <RefreshCcw :size="16" :stroke-width="1.75" />
      </button>
    </header>

    <main class="content">
      <section class="invite-panel">
        <div class="panel-copy">
          <h2>Пригласить инвестора</h2>
          <p>Ссылка прикрепит инвестора к этому бизнесу. После принятия он появится в договорах прихода.</p>
        </div>
        <div class="invite-form">
          <input v-model="displayName" class="input-field" placeholder="Имя инвестора" />
          <input v-model="email" class="input-field" type="email" placeholder="Email, если есть" />
          <button class="primary-btn" type="button" :disabled="isCreating" @click="createInvite">
            <Send :size="16" :stroke-width="2" />
            <span>{{ isCreating ? 'Создание...' : 'Создать ссылку' }}</span>
          </button>
        </div>
      </section>

      <div v-if="errorMessage" class="error-box">{{ errorMessage }}</div>

      <section class="section">
        <h2 class="section-title">Связанные инвесторы</h2>
        <div v-if="isLoading" class="muted">Загрузка...</div>
        <div v-else-if="activeRelations.length === 0" class="muted">Пока нет активных инвесторов.</div>
        <div v-else class="list">
          <article v-for="relation in activeRelations" :key="relation.id" class="row-item">
            <div>
              <strong>{{ relation.partner_name }}</strong>
              <span>{{ relation.source === 'INVITE' ? 'По приглашению' : 'Добавлен вручную' }}</span>
            </div>
            <span class="status active">Активен</span>
          </article>
        </div>
      </section>

      <section class="section">
        <h2 class="section-title">Ожидают принятия</h2>
        <div v-if="pendingInvites.length === 0" class="muted">Нет активных приглашений.</div>
        <div v-else class="list">
          <article v-for="invite in pendingInvites" :key="invite.id" class="row-item">
            <div>
              <strong>{{ invite.display_name || invite.email || 'Инвестор' }}</strong>
              <span>Истекает {{ formatDate(invite.expires_at) }}</span>
            </div>
            <button class="copy-btn" type="button" @click="copyInvite(invite)">
              <Copy :size="15" :stroke-width="2" />
              <span>Скопировать</span>
            </button>
          </article>
        </div>
      </section>

      <section class="section">
        <div class="note-row">
          <Link :size="16" :stroke-width="1.75" />
          <span>Инвестор получает доступ только к своим отчётам и договорам.</span>
        </div>
      </section>
    </main>
  </div>
</template>

<style scoped>
.investors-page { min-height: 100%; background: var(--color-bg-primary); }
.page-header { position: sticky; top: 0; z-index: var(--z-sticky); display: grid; grid-template-columns: 40px 1fr 40px; align-items: center; gap: var(--space-3); min-height: var(--header-height); padding: 0 var(--space-4); border-bottom: 1px solid var(--color-border-subtle); background: var(--color-bg-primary); }
.page-title { text-align: center; font-size: var(--text-lg); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.icon-btn { width: 40px; height: 40px; display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radius-md); color: var(--color-text-primary); }
.content { display: grid; gap: var(--space-4); padding: var(--space-4); padding-bottom: calc(var(--bottom-nav-height) + var(--space-8)); }
.invite-panel { display: grid; gap: var(--space-4); padding: var(--space-4); border-radius: var(--radius-lg); background: var(--color-bg-elevated); border: 1px solid var(--color-border-subtle); }
.panel-copy h2, .section-title { font-size: var(--text-base); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.panel-copy p, .muted, .row-item span, .note-row { margin-top: 4px; font-size: var(--text-sm); color: var(--color-text-secondary); line-height: var(--leading-normal); }
.invite-form, .section, .list { display: grid; gap: var(--space-2); }
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
</style>
