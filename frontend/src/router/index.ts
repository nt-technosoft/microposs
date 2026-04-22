/**
 * Vue Router instance with auth guards.
 */

import { createRouter, createWebHistory } from 'vue-router'
import routes from './routes'
import { useAuthStore } from '@/stores/auth'
import { useUIStore } from '@/stores/ui'
import { useSessionStore } from '@/stores/session'

function getRoleHomeRoute(role?: string | null) {
  switch (role) {
    case 'investor':
      return { name: 'investor-dashboard' as const }
    case 'warehouse':
      return { name: 'procurement-list' as const }
    case 'owner':
    case 'cashier':
      return { name: 'sales-catalog' as const }
    default:
      return { name: 'login' as const }
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(_to, _from, savedPosition) {
    return savedPosition || { top: 0 }
  },
})

// Auth guard
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  const ui = useUIStore()
  const session = useSessionStore()
  const requiresAuth = to.meta.requiresAuth !== false
  const token = auth.token || localStorage.getItem('access_token')

  if (requiresAuth && !token) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (token && !auth.userLoaded) {
    try {
      await auth.ensureUserLoaded()
    } catch {
      return { name: 'login', query: { redirect: to.fullPath } }
    }
  }

  if (to.name === 'login' && token) {
    return getRoleHomeRoute(auth.role)
  }

  const allowedRoles = Array.isArray(to.meta.roles)
    ? to.meta.roles.filter((role): role is string => typeof role === 'string')
    : []
  if (token && allowedRoles.length > 0) {
    const role = auth.role
    if (!role || !allowedRoles.includes(role)) {
      return getRoleHomeRoute(role)
    }
  }

  if (token && to.meta.layout !== 'blank' && to.meta.layout !== 'investor') {
    if (
      (auth.role === 'owner' || auth.role === 'cashier')
      && !session.currentSession
      && !session.isLoading
    ) {
      try {
        await session.loadCurrentSession()
      } catch {
        // non-blocking: sales UI handles "no open session" state.
      }
    }

    if (
      ui.simpleSellerMode
      && (auth.role === 'owner' || auth.role === 'cashier')
      && !to.path.startsWith('/sales')
    ) {
      return { name: 'sales-catalog' }
    }
  }
})

export default router
