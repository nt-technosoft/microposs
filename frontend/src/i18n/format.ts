import type { Locale } from './keys'

export function intlLocale(locale: Locale | string | unknown): string {
  if (locale === 'en') return 'en-US'
  if (locale === 'uz') return 'uz-Latn-UZ'
  return 'ru-RU'
}
