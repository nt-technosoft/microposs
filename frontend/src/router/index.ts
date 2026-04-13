/**
 * Vue Router instance with auth guards.
 */

import { createRouter, createWebHistory } from 'vue-router'
import routes from './routes'

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(_to, _from, savedPosition) {
    return savedPosition || { top: 0 }
  },
})

// Auth guard
router.beforeEach((to) => {
  const requiresAuth = to.meta.requiresAuth !== false
  const token = localStorage.getItem('access_token')

  if (requiresAuth && !token) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.name === 'login' && token) {
    return { name: 'sales-catalog' }
  }
})

export default router
