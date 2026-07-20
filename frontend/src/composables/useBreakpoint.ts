/**
 * Reactive breakpoint detection.
 */

import { ref, onMounted, onUnmounted } from 'vue'

const BREAKPOINTS = {
  mobile: 375,
  tablet: 768,
  desktop: 1024,
  shell: 1280,
  wide: 1440,
} as const

export function useBreakpoint() {
  const width = ref(typeof window !== 'undefined' ? window.innerWidth : 375)

  const isMobile = ref(true)
  const isTablet = ref(false)
  const isDesktop = ref(false)
  const isWideDesktop = ref(false)

  function update() {
    width.value = window.innerWidth
    isMobile.value = width.value < BREAKPOINTS.tablet
    isTablet.value = width.value >= BREAKPOINTS.tablet && width.value < BREAKPOINTS.desktop
    isDesktop.value = width.value >= BREAKPOINTS.desktop
    isWideDesktop.value = width.value >= BREAKPOINTS.shell
  }

  onMounted(() => {
    update()
    window.addEventListener('resize', update, { passive: true })
  })

  onUnmounted(() => {
    window.removeEventListener('resize', update)
  })

  return { width, isMobile, isTablet, isDesktop, isWideDesktop }
}
