/**
 * UI store — theme, locale, layout state.
 */

import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

type Theme = 'light' | 'dark'
type Locale = 'ru' | 'uz' | 'en'

export const useUIStore = defineStore('ui', () => {
  const theme = ref<Theme>(loadTheme())
  const locale = ref<Locale>(loadLocale())
  const isBottomSheetOpen = ref(false)
  const bottomSheetComponent = ref<string | null>(null)

  // Apply theme to DOM
  watch(theme, (newTheme) => {
    document.documentElement.setAttribute('data-theme', newTheme)
    localStorage.setItem('microposs_theme', newTheme)
  }, { immediate: true })

  watch(locale, (newLocale) => {
    localStorage.setItem('microposs_locale', newLocale)
  })

  function toggleTheme() {
    theme.value = theme.value === 'light' ? 'dark' : 'light'
  }

  function setLocale(newLocale: Locale) {
    locale.value = newLocale
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
    return (localStorage.getItem('microposs_locale') as Locale) || 'ru'
  }

  return {
    theme,
    locale,
    isBottomSheetOpen,
    bottomSheetComponent,
    toggleTheme,
    setLocale,
    openBottomSheet,
    closeBottomSheet,
  }
})
