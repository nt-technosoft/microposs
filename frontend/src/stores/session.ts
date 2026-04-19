import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import type { UserRole } from './auth'

export function resolveRoleHomePath(role: UserRole | null): string {
  if (role === 'investor') return '/investor'
  if (role === 'warehouse') return '/procurements'
  if (role === 'owner') return '/sales'
  if (role === 'cashier') return '/sales'
  return '/login'
}

export const useSessionStore = defineStore('session', () => {
  const activeRole = ref<UserRole | null>(null)

  const roleHomeRoute = computed(() => resolveRoleHomePath(activeRole.value))

  function setRole(role: UserRole | null) {
    activeRole.value = role
  }

  return {
    activeRole,
    roleHomeRoute,
    setRole,
  }
})
