import { readonly, shallowReactive } from 'vue'

export type PageChromeStatusTone = 'neutral' | 'positive' | 'warning' | 'negative'

export interface PageChromeConfig {
  title: string
  eyebrow?: string
  status?: string
  statusTone?: PageChromeStatusTone
}

interface PageChromeState extends PageChromeConfig {
  owner: symbol | null
}

const state = shallowReactive<PageChromeState>({
  owner: null,
  title: '',
  eyebrow: '',
  status: '',
  statusTone: 'neutral',
})

const registrations: Array<{ owner: symbol; config: PageChromeConfig }> = []

function syncActiveRegistration(): void {
  const active = registrations.at(-1)
  state.owner = active?.owner ?? null
  state.title = active?.config.title ?? ''
  state.eyebrow = active?.config.eyebrow ?? ''
  state.status = active?.config.status ?? ''
  state.statusTone = active?.config.statusTone ?? 'neutral'
}

export const pageChromeState = readonly(state)

export function registerPageChrome(owner: symbol, config: PageChromeConfig): void {
  const existing = registrations.find((registration) => registration.owner === owner)
  if (existing) existing.config = config
  else registrations.push({ owner, config })
  syncActiveRegistration()
}

export function clearPageChrome(owner: symbol): void {
  const index = registrations.findIndex((registration) => registration.owner === owner)
  if (index === -1) return
  registrations.splice(index, 1)
  syncActiveRegistration()
}
