/**
 * Auth store — user session, role, tenant.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api/client'
import { UserRole } from '@/types/enums'

interface User {
  id: number
  username: string
  role: UserRole | null
  active_tenant_id: number | null
  tenant_name: string
}

interface CurrentUserResponse {
  id: number
  username: string
  role: string | null
  active_tenant_id: number | null
  tenant_name: string
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('access_token'))
  const userLoaded = ref(false)

  const isAuthenticated = computed(() => !!token.value)
  const role = computed<UserRole | null>(() => user.value?.role ?? null)
  const tenantId = computed(() => user.value?.active_tenant_id ?? null)
  const isCashierMode = computed(() => role.value === UserRole.CASHIER)
  const isOwner = computed(() => role.value === UserRole.OWNER)

  async function login(username: string, password: string) {
    const { data } = await api.post('/api/v1/auth/token/', {
      username,
      password,
    })
    token.value = data.access
    localStorage.setItem('access_token', data.access)
    localStorage.setItem('refresh_token', data.refresh)
    userLoaded.value = false
    await fetchUser()
  }

  async function fetchUser() {
    if (!token.value) {
      user.value = null
      userLoaded.value = false
      return
    }

    const { data } = await api.get<CurrentUserResponse>('/api/v1/auth/me/')
    const rawRole = typeof data.role === 'string' ? data.role : null
    const normalizedRole = (Object.values(UserRole) as string[]).includes(rawRole ?? '')
      ? (rawRole as UserRole)
      : null

    user.value = {
      id: data.id,
      username: data.username,
      role: normalizedRole,
      active_tenant_id: data.active_tenant_id ?? null,
      tenant_name: data.tenant_name ?? '',
    }
    userLoaded.value = true
  }

  async function ensureUserLoaded() {
    if (!token.value || userLoaded.value) {
      return
    }

    try {
      await fetchUser()
    } catch (error) {
      logout()
      throw error
    }
  }

  function logout() {
    user.value = null
    token.value = null
    userLoaded.value = false
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  return {
    user,
    token,
    userLoaded,
    isAuthenticated,
    role,
    tenantId,
    isCashierMode,
    isOwner,
    login,
    fetchUser,
    ensureUserLoaded,
    logout,
  }
})
