/**
 * Toast notification composable.
 *
 * Usage:
 *   const toast = useToast()
 *   toast.success('Saved')
 *   toast.error('Something went wrong')
 *
 * Mount <AppToastContainer /> once in App.vue to display toasts.
 */

import { ref, readonly } from 'vue'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface ToastItem {
  id: number
  message: string
  type: ToastType
  duration: number
}

// Module-level reactive state — shared across all composable instances
const toasts = ref<ToastItem[]>([])
let nextId = 1

function addToast(message: string, type: ToastType, duration: number): void {
  const id = nextId++
  const item: ToastItem = { id, message, type, duration }

  toasts.value = [...toasts.value, item]

  const timeout = type === 'error' ? Math.max(duration, 5000) : duration
  setTimeout(() => removeToast(id), timeout + 300) // +300ms to allow exit animation
}

function removeToast(id: number): void {
  toasts.value = toasts.value.filter((t) => t.id !== id)
}

export interface ToastController {
  success: (message: string, duration?: number) => void
  error: (message: string, duration?: number) => void
  warning: (message: string, duration?: number) => void
  info: (message: string, duration?: number) => void
  dismiss: (id: number) => void
}

export function useToast(): ToastController {
  return {
    success(message, duration = 3000) {
      addToast(message, 'success', duration)
    },
    error(message, duration = 5000) {
      addToast(message, 'error', duration)
    },
    warning(message, duration = 4000) {
      addToast(message, 'warning', duration)
    },
    info(message, duration = 3000) {
      addToast(message, 'info', duration)
    },
    dismiss(id) {
      removeToast(id)
    },
  }
}

/**
 * Read-only access to the current toast list.
 * Used internally by AppToastContainer.
 */
export function useToastState() {
  return {
    toasts: readonly(toasts),
    removeToast,
  }
}
