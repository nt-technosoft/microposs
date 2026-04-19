<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import BaseButton from '@/components/base/BaseButton.vue'
import BaseCard from '@/components/base/BaseCard.vue'
import BaseInput from '@/components/base/BaseInput.vue'
import { useAuthStore } from '@/stores/auth'
import { useSessionStore } from '@/stores/session'

const router = useRouter()
const authStore = useAuthStore()
const sessionStore = useSessionStore()

const fullName = ref('Owner Demo')
const role = ref<'owner' | 'cashier' | 'warehouse' | 'investor'>('owner')
const isDemoMode = import.meta.env.DEV

function startDemoSession() {
  if (!isDemoMode) {
    return
  }

  authStore.setSession({
    token: 'demo-token',
    user: {
      id: 1,
      fullName: fullName.value,
      role: role.value,
    },
  })
  sessionStore.setRole(role.value)
  void router.push(sessionStore.roleHomeRoute)
}
</script>

<template>
  <main class="page page--centered">
    <BaseCard class="login-card">
      <div class="login-card__header">
        <h1>MicroPOS</h1>
        <p>Clean-slate frontend bootstrap is live.</p>
      </div>

      <div class="login-card__form">
        <template v-if="isDemoMode">
          <BaseInput v-model="fullName" label="Display name" placeholder="Owner Demo" />

          <label class="role-field">
            <span>Role</span>
            <select v-model="role" class="role-field__select">
              <option value="owner">Owner</option>
              <option value="cashier">Cashier</option>
              <option value="warehouse">Warehouse</option>
              <option value="investor">Investor</option>
            </select>
          </label>

          <BaseButton label="Start demo session" @click="startDemoSession" />
        </template>

        <p v-else class="login-card__note">
          Production login wiring should use backend auth endpoints instead of demo role selection.
        </p>
      </div>
    </BaseCard>
  </main>
</template>

<style scoped>
.page {
  min-height: 100vh;
  padding: var(--space-6);
}

.page--centered {
  display: grid;
  place-items: center;
}

.login-card {
  width: min(100%, 28rem);
}

.login-card__header,
.login-card__form {
  display: grid;
  gap: var(--space-4);
}

.login-card__form {
  margin-top: var(--space-6);
}

.role-field {
  display: grid;
  gap: var(--space-2);
  color: var(--color-text-secondary);
}

.login-card__note {
  color: var(--color-text-secondary);
}

.role-field__select {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-surface);
  padding: 0.875rem 1rem;
}
</style>
