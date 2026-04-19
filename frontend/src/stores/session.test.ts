import { setActivePinia, createPinia } from 'pinia'
import { describe, expect, it, beforeEach } from 'vitest'

import { useSessionStore } from './session'

describe('session store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('resolves owner home route', () => {
    const store = useSessionStore()
    store.setRole('owner')

    expect(store.roleHomeRoute).toBe('/sales')
  })

  it('resolves warehouse home route', () => {
    const store = useSessionStore()
    store.setRole('warehouse')

    expect(store.roleHomeRoute).toBe('/procurements')
  })

  it('falls back to login when role is absent', () => {
    const store = useSessionStore()

    expect(store.roleHomeRoute).toBe('/login')
  })
})
