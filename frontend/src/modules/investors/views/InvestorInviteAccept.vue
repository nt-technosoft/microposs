<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CheckCircle2, LogIn, UserPlus } from 'lucide-vue-next'
import {
  acceptInvestorInvite,
  fetchInvestorInvitePreview,
  registerInvestorFromInvite,
  type InvestorInvitePreview,
} from '@/api/core'
import { useAuthStore } from '@/stores/auth'
import { useToast } from '@/composables/useToast'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const toast = useToast()

const invite = ref<InvestorInvitePreview | null>(null)
const username = ref('')
const password = ref('')
const displayName = ref('')
const email = ref('')
const isLoading = ref(true)
const isSubmitting = ref(false)
const errorMessage = ref('')

const token = computed(() => String(route.params.token || ''))
const canAccept = computed(() =>
  invite.value?.status === 'PENDING' && !invite.value?.is_expired,
)

async function loadInvite(): Promise<void> {
  isLoading.value = true
  errorMessage.value = ''
  try {
    invite.value = await fetchInvestorInvitePreview(token.value)
    displayName.value = invite.value.display_name
    email.value = invite.value.email
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'Приглашение не найдено'
  } finally {
    isLoading.value = false
  }
}

async function acceptExistingAccount(): Promise<void> {
  if (!auth.isAuthenticated) {
    await router.push({ name: 'login', query: { redirect: route.fullPath } })
    return
  }
  isSubmitting.value = true
  errorMessage.value = ''
  try {
    await acceptInvestorInvite(token.value, displayName.value.trim())
    await auth.fetchUser()
    toast.success('Приглашение принято')
    await router.push({ name: 'investor-dashboard' })
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось принять приглашение'
  } finally {
    isSubmitting.value = false
  }
}

async function registerAndAccept(): Promise<void> {
  if (!username.value.trim() || !password.value) {
    errorMessage.value = 'Введите логин и пароль'
    return
  }
  isSubmitting.value = true
  errorMessage.value = ''
  try {
    const response = await registerInvestorFromInvite(token.value, {
      username: username.value.trim(),
      password: password.value,
      display_name: displayName.value.trim(),
      email: email.value.trim(),
    })
    localStorage.setItem('access_token', response.access)
    localStorage.setItem('refresh_token', response.refresh)
    auth.token = response.access
    await auth.fetchUser()
    toast.success('Аккаунт инвестора создан')
    await router.push({ name: 'investor-dashboard' })
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'Не удалось создать аккаунт'
  } finally {
    isSubmitting.value = false
  }
}

onMounted(loadInvite)
</script>

<template>
  <div class="invite-page">
    <main class="invite-shell">
      <div v-if="isLoading" class="state">Загрузка приглашения...</div>

      <section v-else-if="invite" class="invite-panel">
        <div class="mark">
          <CheckCircle2 :size="28" :stroke-width="1.75" />
        </div>
        <h1>Приглашение инвестора</h1>
        <p class="lead">
          {{ invite.business_name }} приглашает вас подключиться к отчётности бизнеса.
        </p>

        <div v-if="!canAccept" class="error-box">
          Приглашение уже использовано, отозвано или истекло.
        </div>
        <template v-else>
          <div class="form-grid">
            <input v-model="displayName" class="input-field" placeholder="Ваше имя" />
            <input v-model="email" class="input-field" type="email" placeholder="Email" />
          </div>

          <button class="secondary-btn" type="button" :disabled="isSubmitting" @click="acceptExistingAccount">
            <LogIn :size="16" :stroke-width="2" />
            <span>{{ auth.isAuthenticated ? 'Принять через текущий аккаунт' : 'Войти и принять' }}</span>
          </button>

          <div class="divider">или создать аккаунт</div>

          <div class="form-grid">
            <input v-model="username" class="input-field" placeholder="Логин" />
            <input v-model="password" class="input-field" type="password" placeholder="Пароль" />
          </div>
          <button class="primary-btn" type="button" :disabled="isSubmitting" @click="registerAndAccept">
            <UserPlus :size="16" :stroke-width="2" />
            <span>{{ isSubmitting ? 'Подключение...' : 'Создать и подключиться' }}</span>
          </button>
        </template>

        <div v-if="errorMessage" class="error-box">{{ errorMessage }}</div>
      </section>

      <div v-else class="error-box">{{ errorMessage }}</div>
    </main>
  </div>
</template>

<style scoped>
.invite-page { min-height: 100%; display: grid; place-items: center; background: var(--color-bg-primary); padding: var(--space-4); }
.invite-shell { width: min(100%, 420px); }
.invite-panel { display: grid; gap: var(--space-4); border: 1px solid var(--color-border-subtle); border-radius: var(--radius-lg); background: var(--color-bg-elevated); padding: var(--space-5); }
.mark { width: 52px; height: 52px; display: inline-flex; align-items: center; justify-content: center; border-radius: var(--radius-full); color: var(--color-success); background: var(--color-success-bg); }
h1 { font-size: var(--text-xl); font-weight: var(--font-semibold); color: var(--color-text-primary); }
.lead, .state { font-size: var(--text-sm); line-height: var(--leading-normal); color: var(--color-text-secondary); }
.form-grid { display: grid; gap: var(--space-2); }
.input-field { min-height: 44px; border-radius: var(--radius-md); border: 1px solid var(--color-border-default); background: var(--color-bg-primary); color: var(--color-text-primary); padding: 0 var(--space-3); font-size: var(--text-sm); }
.primary-btn, .secondary-btn { min-height: 44px; display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2); border-radius: var(--radius-md); font-weight: var(--font-semibold); }
.primary-btn { color: var(--color-text-inverse); background: var(--color-brand-500); }
.secondary-btn { color: var(--color-text-primary); border: 1px solid var(--color-border-default); }
.divider { display: flex; align-items: center; gap: var(--space-2); color: var(--color-text-tertiary); font-size: var(--text-xs); }
.divider::before, .divider::after { content: ""; height: 1px; flex: 1; background: var(--color-border-subtle); }
.error-box { border-radius: var(--radius-md); border: 1px solid var(--color-error); background: var(--color-error-bg); color: var(--color-error); padding: var(--space-3); font-size: var(--text-sm); }
</style>
