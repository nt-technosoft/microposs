<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Sprout, User, Lock, Eye, EyeOff, Building2, ArrowRight } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
import { useSessionStore } from '@/stores/session'
import BaseButton from '@/components/base/BaseButton.vue'

// ── State ──────────────────────────────────────────────────────────────────
const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const sessionStore = useSessionStore()

const username = ref('owner')
const password = ref('Owner123!')
const showPassword = ref(false)
const isLoading = ref(false)
const apiError = ref('')
const mounted = ref(false)

// Validation
const usernameError = ref('')
const passwordError = ref('')

// ── Computed ───────────────────────────────────────────────────────────────
const isFormDirty = computed(() => username.value.length > 0 || password.value.length > 0)

// ── Validation ─────────────────────────────────────────────────────────────
function validateUsername(): boolean {
  if (!username.value.trim()) {
    usernameError.value = 'Введите имя пользователя'
    return false
  }
  usernameError.value = ''
  return true
}

function validatePassword(): boolean {
  if (!password.value) {
    passwordError.value = 'Введите пароль'
    return false
  }
  if (password.value.length < 4) {
    passwordError.value = 'Пароль должен содержать не менее 4 символов'
    return false
  }
  passwordError.value = ''
  return true
}

function validateForm(): boolean {
  const usernameOk = validateUsername()
  const passwordOk = validatePassword()
  return usernameOk && passwordOk
}

// ── Handlers ───────────────────────────────────────────────────────────────
function onUsernameInput(event: Event) {
  username.value = (event.target as HTMLInputElement).value
  if (usernameError.value) validateUsername()
  if (apiError.value) apiError.value = ''
}

function onPasswordInput(event: Event) {
  password.value = (event.target as HTMLInputElement).value
  if (passwordError.value) validatePassword()
  if (apiError.value) apiError.value = ''
}

function openBusinessRegistration() {
  router.push('/register-business')
}

async function handleSubmit() {
  if (!validateForm()) return
  if (isLoading.value) return

  isLoading.value = true
  apiError.value = ''

  try {
    await authStore.login(username.value.trim(), password.value)
    if (authStore.role === 'owner' || authStore.role === 'cashier') {
      await sessionStore.loadCurrentSession()
    }
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : ''
    if (redirect) {
      await router.push(redirect)
      return
    }
    const role = authStore.role
    if (role === 'warehouse') {
      await router.push('/procurements')
    } else if (role === 'platform_admin') {
      await router.push('/platform-admin')
    } else if (role === 'investor') {
      await router.push('/investor')
    } else {
      await router.push('/sales')
    }
  } catch (error: unknown) {
    const axiosError = error as { response?: { status?: number, data?: { detail?: string } } }
    const detail = axiosError?.response?.data?.detail
    if (typeof detail === 'string' && detail.trim()) {
      apiError.value = detail
    } else if (axiosError?.response?.status === 401 || axiosError?.response?.status === 400) {
      apiError.value = 'Неверный логин или пароль'
    } else {
      apiError.value = 'Ошибка сети. Проверьте подключение и попробуйте снова.'
    }
  } finally {
    isLoading.value = false
  }
}

// ── Lifecycle ──────────────────────────────────────────────────────────────
onMounted(() => {
  // Trigger mount animations on next frame so CSS transitions fire
  requestAnimationFrame(() => {
    mounted.value = true
  })
})
</script>

<template>
  <div class="login-page">
    <!-- Brand area: top 40% -->
    <div class="brand-area" :class="{ 'brand-area--visible': mounted }">
      <div class="brand-content">
        <div class="logo-mark">
          <Sprout :size="40" stroke-width="1.5" />
        </div>
        <h1 class="brand-name">MicroPOS</h1>
        <p class="brand-tagline">Умный учёт для вашего бизнеса</p>
      </div>

      <!-- Decorative circles -->
      <div class="deco-circle deco-circle--lg" aria-hidden="true" />
      <div class="deco-circle deco-circle--sm" aria-hidden="true" />
    </div>

    <!-- Form card: bottom 60% -->
    <div class="form-card" :class="{ 'form-card--visible': mounted }" role="main">
      <div class="form-card__inner">
        <h2 class="form-title">Войти в систему</h2>

        <form class="form" novalidate @submit.prevent="handleSubmit">
          <!-- Username field -->
          <div class="field-group" :class="{ 'field-group--error': usernameError }">
            <label class="field-label" for="username">Имя пользователя</label>
            <div class="field-input-wrap">
              <span class="field-icon field-icon--left" aria-hidden="true">
                <User :size="18" stroke-width="1.75" />
              </span>
              <input
                id="username"
                class="field-input"
                type="text"
                autocomplete="username"
                autocapitalize="none"
                placeholder="Введите логин"
                :value="username"
                :disabled="isLoading"
                :aria-describedby="usernameError ? 'username-error' : undefined"
                :aria-invalid="!!usernameError"
                @input="onUsernameInput"
                @blur="validateUsername"
              />
            </div>
            <Transition name="field-error">
              <span v-if="usernameError" id="username-error" class="field-error" role="alert">
                {{ usernameError }}
              </span>
            </Transition>
          </div>

          <!-- Password field -->
          <div class="field-group" :class="{ 'field-group--error': passwordError }">
            <label class="field-label" for="password">Пароль</label>
            <div class="field-input-wrap">
              <span class="field-icon field-icon--left" aria-hidden="true">
                <Lock :size="18" stroke-width="1.75" />
              </span>
              <input
                id="password"
                class="field-input"
                :type="showPassword ? 'text' : 'password'"
                autocomplete="current-password"
                placeholder="Введите пароль"
                :value="password"
                :disabled="isLoading"
                :aria-describedby="passwordError ? 'password-error' : undefined"
                :aria-invalid="!!passwordError"
                @input="onPasswordInput"
                @blur="validatePassword"
              />
              <button
                type="button"
                class="field-icon field-icon--right field-icon--btn"
                :aria-label="showPassword ? 'Скрыть пароль' : 'Показать пароль'"
                tabindex="0"
                @click="showPassword = !showPassword"
              >
                <EyeOff v-if="showPassword" :size="18" stroke-width="1.75" />
                <Eye v-else :size="18" stroke-width="1.75" />
              </button>
            </div>
            <Transition name="field-error">
              <span v-if="passwordError" id="password-error" class="field-error" role="alert">
                {{ passwordError }}
              </span>
            </Transition>
          </div>

          <!-- API error message -->
          <Transition name="api-error">
            <div v-if="apiError" class="api-error" role="alert" aria-live="assertive">
              <span class="api-error__text">{{ apiError }}</span>
            </div>
          </Transition>

          <!-- Submit button -->
          <BaseButton
            type="submit"
            variant="primary"
            size="lg"
            :full-width="true"
            :loading="isLoading"
            :disabled="isLoading"
            class="submit-btn"
          >
            {{ isLoading ? 'Выполняется вход…' : 'Войти' }}
          </BaseButton>
        </form>

        <button type="button" class="register-link-card" @click="openBusinessRegistration">
          <span class="register-link-card__icon" aria-hidden="true">
            <Building2 :size="18" stroke-width="1.8" />
          </span>
          <span class="register-link-card__content">
            <span class="register-link-card__title">Подать заявку на подключение бизнеса</span>
            <span class="register-link-card__text">Короткая регистрация, активация после подтверждения в платформе.</span>
          </span>
          <ArrowRight :size="18" stroke-width="1.8" class="register-link-card__arrow" aria-hidden="true" />
        </button>

        <!-- Footer -->
        <p class="form-footer">MicroPOS v0.1</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── Layout ────────────────────────────────────────────────────────────── */
.login-page {
  min-height: 100dvh;
  min-height: 100vh; /* fallback */
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #156B56; /* fallback while gradient loads */
}

/* ── Brand area ─────────────────────────────────────────────────────────── */
.brand-area {
  position: relative;
  flex: 0 0 40%;
  min-height: 220px;
  background: linear-gradient(160deg, #1B8A6F 0%, #156B56 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  opacity: 0;
  transform: translateY(-12px);
  transition:
    opacity 400ms var(--ease-out),
    transform 400ms var(--ease-out);
}

.brand-area--visible {
  opacity: 1;
  transform: translateY(0);
}

.brand-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  position: relative;
  z-index: 1;
  text-align: center;
  padding: var(--space-8) var(--space-6);
}

.logo-mark {
  width: 72px;
  height: 72px;
  border-radius: var(--radius-xl);
  background: rgba(255, 255, 255, 0.15);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.25);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
}

.brand-name {
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  color: #ffffff;
  letter-spacing: -0.02em;
  line-height: var(--leading-tight);
  margin: 0;
}

.brand-tagline {
  font-size: var(--text-sm);
  color: rgba(255, 255, 255, 0.75);
  margin: 0;
  font-weight: var(--font-normal);
  letter-spacing: 0.01em;
}

/* Decorative background circles */
.deco-circle {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.06);
  pointer-events: none;
}

.deco-circle--lg {
  width: 260px;
  height: 260px;
  bottom: -80px;
  right: -60px;
}

.deco-circle--sm {
  width: 140px;
  height: 140px;
  top: -40px;
  left: -30px;
}

/* ── Form card ─────────────────────────────────────────────────────────── */
.form-card {
  flex: 1;
  background: var(--color-bg-elevated);
  border-radius: 24px 24px 0 0;
  box-shadow: 0 -4px 32px rgba(26, 23, 20, 0.12);
  margin-top: -24px; /* overlap the brand area slightly */
  position: relative;
  z-index: 2;
  opacity: 0;
  transform: translateY(32px);
  transition:
    opacity 420ms var(--ease-out) 80ms,
    transform 420ms var(--ease-spring) 80ms;
}

.form-card--visible {
  opacity: 1;
  transform: translateY(0);
}

.form-card__inner {
  padding: var(--space-8) var(--space-6) var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  max-width: 480px;
  margin: 0 auto;
  width: 100%;
}

/* ── Form title ─────────────────────────────────────────────────────────── */
.form-title {
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
  color: var(--color-text-primary);
  margin: 0;
  line-height: var(--leading-tight);
  letter-spacing: -0.02em;
}

/* ── Form layout ─────────────────────────────────────────────────────────── */
.form {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

/* ── Field group ─────────────────────────────────────────────────────────── */
.field-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.field-label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
}

.field-input-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.field-input {
  width: 100%;
  height: 52px;
  padding: 0 var(--space-10) 0 var(--space-10);
  border: 1.5px solid var(--color-border-default);
  border-radius: var(--radius-lg);
  background: var(--color-bg-primary);
  font-size: var(--text-base);
  font-family: var(--font-primary);
  color: var(--color-text-primary);
  outline: none;
  transition:
    border-color var(--duration-fast) var(--ease-out),
    box-shadow var(--duration-fast) var(--ease-out),
    background var(--duration-fast) var(--ease-out);
}

.field-input::placeholder {
  color: var(--color-text-tertiary);
}

.field-input:focus {
  border-color: var(--color-border-focus);
  box-shadow: 0 0 0 3px var(--color-brand-100);
  background: var(--color-bg-elevated);
}

.field-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background: var(--color-bg-sunken);
}

.field-group--error .field-input {
  border-color: var(--color-error);
}

.field-group--error .field-input:focus {
  box-shadow: 0 0 0 3px var(--color-error-bg);
}

/* Field icons */
.field-icon {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-tertiary);
  pointer-events: none;
}

.field-icon--left {
  left: var(--space-3);
}

.field-icon--right {
  right: var(--space-3);
}

.field-icon--btn {
  pointer-events: auto;
  background: none;
  border: none;
  cursor: pointer;
  padding: var(--space-1);
  border-radius: var(--radius-sm);
  transition: color var(--duration-fast) var(--ease-out);
  -webkit-tap-highlight-color: transparent;
}

.field-icon--btn:hover {
  color: var(--color-text-secondary);
}

.field-icon--btn:focus-visible {
  outline: 2px solid var(--color-border-focus);
  outline-offset: 1px;
}

/* Field error text */
.field-error {
  font-size: var(--text-xs);
  color: var(--color-error);
  padding-left: var(--space-1);
}

/* ── API error block ─────────────────────────────────────────────────────── */
.api-error {
  background: var(--color-error-bg);
  border: 1px solid rgba(217, 83, 79, 0.25);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
}

.api-error__text {
  font-size: var(--text-sm);
  color: var(--color-error);
  font-weight: var(--font-medium);
}

/* ── Submit button ─────────────────────────────────────────────────────── */
.submit-btn {
  margin-top: var(--space-2);
  height: 56px !important;
  border-radius: var(--radius-lg) !important;
  font-size: var(--text-base) !important;
  font-weight: var(--font-semibold) !important;
  letter-spacing: 0.01em;
  box-shadow: var(--shadow-float);
  transition:
    background var(--duration-fast) var(--ease-out),
    box-shadow var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-out) !important;
}

.register-link-card {
  width: 100%;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4);
  border-radius: 20px;
  border: 1px solid rgba(21, 107, 86, 0.14);
  background:
    linear-gradient(180deg, rgba(27, 138, 111, 0.05), rgba(27, 138, 111, 0.02)),
    var(--color-bg-primary);
  text-align: left;
  cursor: pointer;
  transition:
    border-color var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-out),
    box-shadow var(--duration-fast) var(--ease-out);
}

.register-link-card:active {
  transform: scale(0.985);
}

.register-link-card__icon {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #156B56;
  background: rgba(21, 107, 86, 0.08);
  border: 1px solid rgba(21, 107, 86, 0.12);
}

.register-link-card__content {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.register-link-card__title {
  font-size: var(--text-sm);
  line-height: 1.35;
  font-weight: var(--font-semibold);
  color: var(--color-text-primary);
}

.register-link-card__text {
  font-size: var(--text-xs);
  line-height: 1.45;
  color: var(--color-text-secondary);
}

.register-link-card__arrow {
  color: var(--color-text-tertiary);
}

/* ── Footer ─────────────────────────────────────────────────────────────── */
.form-footer {
  text-align: center;
  font-size: var(--text-xs);
  color: var(--color-text-tertiary);
  margin: 0;
  padding-bottom: var(--space-2);
}

/* ── Transitions ─────────────────────────────────────────────────────────── */
.field-error-enter-active,
.field-error-leave-active {
  transition:
    opacity var(--duration-fast) var(--ease-out),
    transform var(--duration-fast) var(--ease-out),
    max-height var(--duration-fast) var(--ease-out);
  overflow: hidden;
  max-height: 24px;
}

.field-error-enter-from,
.field-error-leave-to {
  opacity: 0;
  transform: translateY(-4px);
  max-height: 0;
}

.api-error-enter-active,
.api-error-leave-active {
  transition:
    opacity var(--duration-normal) var(--ease-out),
    transform var(--duration-normal) var(--ease-out);
}

.api-error-enter-from,
.api-error-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* ── Responsive ─────────────────────────────────────────────────────────── */

/* Tablet: 768px+ — centre-card layout */
@media (min-width: 768px) {
  .login-page {
    flex-direction: row;
    align-items: stretch;
  }

  .brand-area {
    flex: 0 0 42%;
    min-height: unset;
    border-radius: 0;
    transform: translateX(-12px);
    opacity: 0;
    transition:
      opacity 400ms var(--ease-out),
      transform 400ms var(--ease-out);
  }

  .brand-area--visible {
    opacity: 1;
    transform: translateX(0);
  }

  .form-card {
    flex: 1;
    border-radius: 0;
    margin-top: 0;
    box-shadow: none;
    display: flex;
    align-items: center;
    transform: translateX(32px);
    opacity: 0;
    transition:
      opacity 420ms var(--ease-out) 80ms,
      transform 420ms var(--ease-spring) 80ms;
  }

  .form-card--visible {
    opacity: 1;
    transform: translateX(0);
  }

  .form-card__inner {
    padding: var(--space-12) var(--space-12);
  }

  .deco-circle--lg {
    width: 360px;
    height: 360px;
    bottom: -120px;
    right: -80px;
  }
}

/* Desktop: 1024px+ */
@media (min-width: 1024px) {
  .form-card__inner {
    padding: var(--space-16) var(--space-16);
  }

  .brand-name {
    font-size: var(--text-4xl);
  }

  .logo-mark {
    width: 84px;
    height: 84px;
  }
}

/* Reduced motion */
@media (prefers-reduced-motion: reduce) {
  .brand-area,
  .brand-area--visible,
  .form-card,
  .form-card--visible,
  .field-error-enter-active,
  .field-error-leave-active,
  .api-error-enter-active,
  .api-error-leave-active {
    transition: none !important;
    animation: none !important;
    opacity: 1 !important;
    transform: none !important;
  }
}
</style>
