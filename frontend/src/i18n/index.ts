import { createI18n } from 'vue-i18n'
import ru from './locales/ru'
import uz from './locales/uz'
import en from './locales/en'
import { fallbackLocale, isLocale, type Locale } from './keys'

export const messages = {
  ru,
  uz,
  en,
}

export type MessageSchema = typeof ru

export function getStoredLocale(): Locale {
  const stored = localStorage.getItem('microposs_locale')
  return isLocale(stored) ? stored : fallbackLocale
}

export const i18n = createI18n<[MessageSchema], Locale>({
  legacy: false,
  locale: getStoredLocale(),
  fallbackLocale,
  messages,
  missingWarn: import.meta.env.DEV,
  fallbackWarn: false,
})

export function setI18nLocale(locale: Locale): void {
  const globalComposer = i18n.global as unknown as { locale: { value: Locale } | Locale }
  if (typeof globalComposer.locale === 'object' && globalComposer.locale !== null && 'value' in globalComposer.locale) {
    globalComposer.locale.value = locale
  } else {
    globalComposer.locale = locale
  }
  document.documentElement.setAttribute('lang', locale)
}

export function translateNow(key: string, params?: Record<string, unknown>): string {
  return i18n.global.t(key, params ?? {})
}
