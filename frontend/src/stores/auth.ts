import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

export type UserRole = 'owner' | 'cashier' | 'warehouse' | 'investor'

type SessionUser = {
  id: number
  fullName: string
  role: UserRole
}

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(null)
  const currentUser = ref<SessionUser | null>(null)

  const isAuthenticated = computed(() => Boolean(accessToken.value))

  function setSession(payload: { token: string; user: SessionUser }) {
    accessToken.value = payload.token
    currentUser.value = { ...payload.user }
  }

  function clearSession() {
    accessToken.value = null
    currentUser.value = null
  }

  return {
    accessToken,
    currentUser,
    isAuthenticated,
    setSession,
    clearSession,
  }
})
