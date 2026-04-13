/**
 * Vue Router instance with auth guards.
 */

import { createRouter, createWebHistory } from 'vue-router'
import routes from './routes'
import { useAuthStore } from '@/stores/auth'
import { useUIStore } from '@/stores/ui'

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
    if (auth.role === 'investor') {
      return { name: 'investor-dashboard' }
    }
    return { name: 'sales-catalog' }
  }

  const allowedRoles = Array.isArray(to.meta.roles)
    ? to.meta.roles.filter((role): role is string => typeof role === 'string')
    : []
  if (token && allowedRoles.length > 0) {
    const role = auth.role
    if (!role || !allowedRoles.includes(role)) {
      if (role === 'investor') {
        return { name: 'investor-dashboard' }
      }
      return { name: 'sales-catalog' }
    }
  }

  if (token && to.meta.layout !== 'blank' && to.meta.layout !== 'investor') {
    if (ui.simpleSellerMode && !to.path.startsWith('/sales')) {
      return { name: 'sales-catalog' }
    }
  }
})

export default router
