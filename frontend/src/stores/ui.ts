/**
 * UI store — theme, locale, layout state.
 */

import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { fallbackLocale, isLocale, type Locale } from '@/i18n/keys'
import { setI18nLocale } from '@/i18n'

type Theme = 'light' | 'dark'

export const useUIStore = defineStore('ui', () => {
  const theme = ref<Theme>(loadTheme())
  const locale = ref<Locale>(loadLocale())
  const simpleSellerMode = ref(loadSimpleSellerMode())
  const isBottomSheetOpen = ref(false)
  const bottomSheetComponent = ref<string | null>(null)

  // Apply theme to DOM
  watch(theme, (newTheme) => {
    document.documentElement.setAttribute('data-theme', newTheme)
    localStorage.setItem('microposs_theme', newTheme)
  }, { immediate: true })

  watch(locale, (newLocale) => {
    localStorage.setItem('microposs_locale', newLocale)
    setI18nLocale(newLocale)
  }, { immediate: true })

  watch(simpleSellerMode, (enabled) => {
    localStorage.setItem('microposs_simple_seller_mode', String(enabled))
  })

  function toggleTheme() {
    theme.value = theme.value === 'light' ? 'dark' : 'light'
  }

  function setLocale(newLocale: Locale) {
    locale.value = newLocale
  }

  function setSimpleSellerMode(enabled: boolean) {
    simpleSellerMode.value = enabled
  }

  function openBottomSheet(component: string) {
    bottomSheetComponent.value = component
    isBottomSheetOpen.value = true
  }

  function closeBottomSheet() {
    isBottomSheetOpen.value = false
    bottomSheetComponent.value = null
  }

  function loadTheme(): Theme {
    const stored = localStorage.getItem('microposs_theme') as Theme | null
    if (stored) return stored
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }

  function loadLocale(): Locale {
    const stored = localStorage.getItem('microposs_locale')
    return isLocale(stored) ? stored : fallbackLocale
  }

  function loadSimpleSellerMode(): boolean {
    return localStorage.getItem('microposs_simple_seller_mode') === 'true'
  }

  return {
    theme,
    locale,
    simpleSellerMode,
    isBottomSheetOpen,
    bottomSheetComponent,
    toggleTheme,
    setLocale,
    setSimpleSellerMode,
    openBottomSheet,
    closeBottomSheet,
  }
})
