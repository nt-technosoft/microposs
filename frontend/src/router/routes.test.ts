import { describe, expect, it } from 'vitest'

import { routes } from './routes'

describe('routes', () => {
  it('uses canonical procurements routes', () => {
    const paths = routes.map((route) => route.path)

    expect(paths).toContain('/procurements')
    expect(paths).toContain('/procurements/:id')
    expect(paths).not.toContain('/intake')
  })

  it('includes investor procurement cabinet routes', () => {
    const paths = routes.map((route) => route.path)

    expect(paths).toContain('/investor')
    expect(paths).toContain('/investor/procurements')
    expect(paths).toContain('/investor/procurements/:id')
  })
})
