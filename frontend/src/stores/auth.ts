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
  role: UserRole
  active_tenant_id: number
  tenant_name: string
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('access_token'))

  const isAuthenticated = computed(() => !!token.value)
  const role = computed(() => user.value?.role ?? null)
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
    await fetchUser()
  }

  async function fetchUser() {
    // Will be implemented with user profile endpoint
  }

  function logout() {
    user.value = null
    token.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  return {
    user,
    token,
    isAuthenticated,
    role,
    tenantId,
    isCashierMode,
    isOwner,
    login,
    fetchUser,
    logout,
  }
})
