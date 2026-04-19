import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import { resolveRoleHomePath, useSessionStore } from '@/stores/session'

import { routes } from './routes'

export const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const authStore = useAuthStore()
  const sessionStore = useSessionStore()

  const role = authStore.currentUser?.role ?? sessionStore.activeRole
  const roleHomeRoute = resolveRoleHomePath(role)

  const isPublicRoute = to.meta.public === true
  if (isPublicRoute && authStore.isAuthenticated) {
    return roleHomeRoute
  }

  if (!isPublicRoute && !authStore.isAuthenticated) {
    return '/login'
  }

  const allowedRoles = Array.isArray(to.meta.roles)
    ? (to.meta.roles as string[])
    : []

  if (!allowedRoles.length) {
    return true
  }

  if (role && allowedRoles.includes(role)) {
    return true
  }

  return roleHomeRoute
})
