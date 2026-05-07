<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, Building2, Lock, Phone, Store, User2 } from 'lucide-vue-next'
import BaseButton from '@/components/base/BaseButton.vue'
import { createBusinessRegistrationRequest } from '@/api/core'

const router = useRouter()
const { t } = useI18n()

const form = reactive({
  first_name: '',
  last_name: '',
  phone: '',
  business_name: '',
  username: '',
  password: '',
})

const isSubmitting = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

function goBack() {
  router.push('/login')
}

function validateForm(): string {
  if (!form.first_name.trim()) return t('auth.firstNameRequired')
  if (!form.last_name.trim()) return t('auth.lastNameRequired')
  if (!form.phone.trim()) return t('auth.phoneRequired')
  if (!form.business_name.trim()) return t('auth.businessNameRequired')
  if (!form.username.trim()) return t('auth.loginRequired')
  if (form.password.length < 6) return t('auth.passwordMin6')
  return ''
}

async function handleSubmit() {
  if (isSubmitting.value) return

  errorMessage.value = ''
  const validationError = validateForm()
  if (validationError) {
    errorMessage.value = validationError
    return
  }

  isSubmitting.value = true

  try {
    await createBusinessRegistrationRequest({
      first_name: form.first_name.trim(),
      last_name: form.last_name.trim(),
      phone: form.phone.trim(),
      business_name: form.business_name.trim(),
      username: form.username.trim(),
      password: form.password,
    })
    successMessage.value = t('auth.registrationSent')
    form.first_name = ''
    form.last_name = ''
    form.phone = ''
    form.business_name = ''
    form.username = ''
    form.password = ''
  } catch (error: unknown) {
    const axiosError = error as { response?: { data?: { detail?: string } } }
    errorMessage.value = axiosError?.response?.data?.detail || t('auth.registrationFailed')
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <div class="registration-page">
    <div class="registration-shell">
      <button type="button" class="back-button" @click="goBack">
        <ArrowLeft :size="18" stroke-width="1.9" />
        <span>{{ t('auth.backToLogin') }}</span>
      </button>

      <section class="hero-panel">
        <span class="hero-panel__eyebrow">{{ t('auth.businessConnection') }}</span>
        <h1 class="hero-panel__title">{{ t('auth.registrationRequestTitle') }}</h1>
        <p class="hero-panel__text">
          {{ t('auth.registrationRequestText') }}
        </p>
      </section>

      <section class="form-panel">
        <form class="request-form" @submit.prevent="handleSubmit">
          <label class="field">
            <span class="field__label">{{ t('auth.firstName') }}</span>
            <span class="field__control">
              <User2 :size="18" stroke-width="1.8" class="field__icon" />
              <input v-model="form.first_name" type="text" class="field__input" :placeholder="t('auth.ownerFirstNamePlaceholder')" />
            </span>
          </label>

          <label class="field">
            <span class="field__label">{{ t('auth.lastName') }}</span>
            <span class="field__control">
              <User2 :size="18" stroke-width="1.8" class="field__icon" />
              <input v-model="form.last_name" type="text" class="field__input" :placeholder="t('auth.ownerLastNamePlaceholder')" />
            </span>
          </label>

          <label class="field">
            <span class="field__label">{{ t('customers.phone') }}</span>
            <span class="field__control">
              <Phone :size="18" stroke-width="1.8" class="field__icon" />
              <input v-model="form.phone" type="tel" class="field__input" placeholder="+998 __ ___ __ __" />
            </span>
          </label>

          <label class="field">
            <span class="field__label">{{ t('auth.businessName') }}</span>
            <span class="field__control">
              <Store :size="18" stroke-width="1.8" class="field__icon" />
              <input v-model="form.business_name" type="text" class="field__input" :placeholder="t('auth.businessNamePlaceholder')" />
            </span>
          </label>

          <label class="field">
            <span class="field__label">{{ t('auth.username') }}</span>
            <span class="field__control">
              <Building2 :size="18" stroke-width="1.8" class="field__icon" />
              <input v-model="form.username" type="text" class="field__input" :placeholder="t('auth.loginPlaceholder')" />
            </span>
          </label>

          <label class="field">
            <span class="field__label">{{ t('auth.password') }}</span>
            <span class="field__control">
              <Lock :size="18" stroke-width="1.8" class="field__icon" />
              <input v-model="form.password" type="password" class="field__input" :placeholder="t('auth.passwordCreatePlaceholder')" />
            </span>
          </label>

          <p v-if="errorMessage" class="message message--error">{{ errorMessage }}</p>
          <p v-if="successMessage" class="message message--success">{{ successMessage }}</p>

          <BaseButton
            type="submit"
            size="lg"
            variant="primary"
            :loading="isSubmitting"
            :disabled="isSubmitting"
            :full-width="true"
          >
            {{ isSubmitting ? t('auth.registrationSubmitting') : t('auth.submitRegistration') }}
          </BaseButton>
        </form>
      </section>
    </div>
  </div>
</template>

<style scoped>
.registration-page {
  min-height: 100dvh;
  padding: var(--space-4);
  background:
    radial-gradient(circle at top right, rgba(27, 138, 111, 0.14), transparent 32%),
    linear-gradient(180deg, #f5f7f4 0%, #eef2ee 100%);
}

.registration-shell {
  max-width: 560px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.back-button {
  width: fit-content;
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

.hero-panel,
.form-panel {
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(20, 37, 31, 0.08);
  border-radius: 28px;
  box-shadow: 0 10px 28px rgba(20, 37, 31, 0.06);
}

.hero-panel {
  padding: var(--space-6);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.hero-panel__eyebrow {
  font-size: 11px;
  line-height: 1.1;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #156B56;
  font-weight: var(--font-semibold);
}

.hero-panel__title {
  margin: 0;
  font-size: clamp(1.9rem, 6vw, 2.4rem);
  line-height: 0.98;
  letter-spacing: -0.04em;
  color: #1d2520;
}

.hero-panel__text {
  margin: 0;
  font-size: var(--text-sm);
  line-height: 1.55;
  color: var(--color-text-secondary);
}

.form-panel {
  padding: var(--space-5);
}

.request-form {
  display: grid;
  gap: var(--space-4);
}

.field {
  display: grid;
  gap: var(--space-2);
}

.field__label {
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
  color: var(--color-text-secondary);
}

.field__control {
  position: relative;
  display: flex;
  align-items: center;
}

.field__icon {
  position: absolute;
  left: var(--space-3);
  color: var(--color-text-tertiary);
}

.field__input {
  width: 100%;
  min-height: 54px;
  padding: 0 var(--space-4) 0 calc(var(--space-8) + var(--space-2));
  border-radius: 18px;
  border: 1px solid rgba(20, 37, 31, 0.1);
  background: #f9fbf8;
  color: var(--color-text-primary);
  font-size: var(--text-base);
  outline: none;
  transition:
    border-color var(--duration-fast) var(--ease-out),
    box-shadow var(--duration-fast) var(--ease-out),
    background var(--duration-fast) var(--ease-out);
}

.field__input:focus {
  border-color: rgba(21, 107, 86, 0.35);
  background: #ffffff;
  box-shadow: 0 0 0 4px rgba(21, 107, 86, 0.08);
}

.message {
  margin: 0;
  padding: var(--space-3) var(--space-4);
  border-radius: 16px;
  font-size: var(--text-sm);
  line-height: 1.45;
}

.message--error {
  background: rgba(217, 83, 79, 0.08);
  color: var(--color-error);
  border: 1px solid rgba(217, 83, 79, 0.16);
}

.message--success {
  background: rgba(21, 107, 86, 0.08);
  color: #156B56;
  border: 1px solid rgba(21, 107, 86, 0.16);
}

@media (min-width: 768px) {
  .registration-page {
    padding: var(--space-8);
  }

  .registration-shell {
    gap: var(--space-5);
  }

  .hero-panel,
  .form-panel {
    border-radius: 32px;
  }

  .hero-panel {
    padding: var(--space-8);
  }

  .form-panel {
    padding: var(--space-6);
  }
}
</style>
