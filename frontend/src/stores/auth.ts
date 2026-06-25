/**
 * Auth store — user session, role, tenant.
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/api/client'
import { UserRole } from '@/types/enums'
import { isLocale, type Locale } from '@/i18n/keys'
import { useSessionStore } from './session'
import { useUIStore } from './ui'

interface User {
  id: number
  username: string
  full_name: string
  role: UserRole | null
  active_tenant_id: number | null
  tenant_name: string
  active_business: { id: number; name: string; currency: string } | null
  owned_businesses: Array<{ id: number; name: string; currency: string }>
  partner_profiles: Array<{ id: number; tenant_id: number; role: 'INVESTOR' | 'OPERATOR'; display_name: string }>
  investor_relations: Array<{ id: number; tenant_id: number; tenant_name: string; partner_id: number; partner_name: string; status: string }>
  tenant_issue: string
  locale: Locale
}

interface CurrentUserResponse {
  id: number
  username: string
  full_name?: string
  role: string | null
  active_tenant_id: number | null
  tenant_name: string
  active_business?: { id: number; name: string; currency: string } | null
  owned_businesses?: Array<{ id: number; name: string; currency: string }>
  partner_profiles?: Array<{ id: number; tenant_id: number; role: 'INVESTOR' | 'OPERATOR'; display_name: string }>
  investor_relations?: Array<{ id: number; tenant_id: number; tenant_name: string; partner_id: number; partner_name: string; status: string }>
  tenant_issue?: string
  locale?: string
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
      full_name: data.full_name ?? '',
      role: normalizedRole,
      active_tenant_id: data.active_tenant_id ?? null,
      tenant_name: data.tenant_name ?? '',
      active_business: data.active_business ?? null,
      owned_businesses: data.owned_businesses ?? [],
      partner_profiles: data.partner_profiles ?? [],
      investor_relations: data.investor_relations ?? [],
      tenant_issue: data.tenant_issue ?? '',
      locale: isLocale(data.locale) ? data.locale : 'ru',
    }
    const ui = useUIStore()
    if (isLocale(data.locale) && ui.locale !== data.locale) {
      ui.setLocale(data.locale)
    }
    if (data.active_tenant_id !== null && data.active_tenant_id !== undefined) {
      localStorage.setItem('active_tenant_id', String(data.active_tenant_id))
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
    const sessionStore = useSessionStore()
    sessionStore.clearSession()
    user.value = null
    token.value = null
    userLoaded.value = false
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('active_tenant_id')
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
