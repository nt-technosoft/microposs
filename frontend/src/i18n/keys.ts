export type Locale = 'ru' | 'uz' | 'en'

export interface LocaleOption {
  value: Locale
  label: string
  shortLabel: string
}

export const supportedLocales: LocaleOption[] = [
  { value: 'ru', label: 'Русский', shortLabel: 'RU' },
  { value: 'uz', label: 'O‘zbekcha', shortLabel: 'UZ' },
  { value: 'en', label: 'English', shortLabel: 'EN' },
]

export const fallbackLocale: Locale = 'ru'

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string'
    && supportedLocales.some((locale) => locale.value === value)
}
