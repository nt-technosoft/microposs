/**
 * POS session store — manages the active open session for a location.
 */

import { defineStore } from 'pinia'
import type { PosSession, Location } from '../types/models'
import {
  fetchSessions,
  openSession as apiOpenSession,
  closeSession as apiCloseSession,
} from '../api/sales'
import { getApiErrorMessage } from '@/utils/errors'

interface SessionState {
  currentSession: PosSession | null
  location: Location | null
  isLoading: boolean
  error: string | null
}

export const useSessionStore = defineStore('session', {
  state: (): SessionState => ({
    currentSession: null,
    location: null,
    isLoading: false,
    error: null,
  }),

  getters: {
    isOpen: (state): boolean => state.currentSession?.status === 'open',
    sessionId: (state): number | null => state.currentSession?.id ?? null,
  },

  actions: {
    normalizeLocation(session: PosSession): Location | null {
      const rawLocation = session.location as unknown

      if (rawLocation && typeof rawLocation === 'object' && 'id' in rawLocation) {
        const location = rawLocation as Location
        const normalizedKind = String(location.kind ?? '').toUpperCase() === 'STORAGE'
          ? 'storage'
          : 'shop'
        return {
          ...location,
          kind: normalizedKind,
          location_type: location.location_type ?? (normalizedKind === 'storage' ? 'warehouse' : 'store'),
        }
      }

      if (typeof rawLocation === 'number') {
        const fallbackName = (session as PosSession & { location_name?: string }).location_name
        return {
          id: rawLocation,
          name: fallbackName ?? `Локация #${rawLocation}`,
          kind: 'shop',
          location_type: 'store',
          is_active: true,
          created_at: '',
          updated_at: '',
        }
      }

      return null
    },

    async loadCurrentSession(locationId?: number): Promise<void> {
      this.isLoading = true
      this.error = null

      try {
        const params = locationId
          ? { status: 'open' as const, location: locationId }
          : { status: 'open' as const }

        const response = await fetchSessions(params)
        const sessions = response.results

        if (sessions.length > 0) {
          const normalizedLocation = this.normalizeLocation(sessions[0])
          this.currentSession = {
            ...sessions[0],
            ...(normalizedLocation ? { location: normalizedLocation } : {}),
          }
          this.location = normalizedLocation
        } else {
          this.currentSession = null
          this.location = null
        }
      } catch (error: unknown) {
        this.error = getApiErrorMessage(error, 'Не удалось загрузить смену')
      } finally {
        this.isLoading = false
      }
    },

    async openSession(locationId: number, openingCash: number): Promise<PosSession> {
      this.isLoading = true
      this.error = null

      try {
        const session = await apiOpenSession({ location_id: locationId, opening_cash: openingCash })
        const normalizedLocation = this.normalizeLocation(session)
        this.currentSession = {
          ...session,
          ...(normalizedLocation ? { location: normalizedLocation } : {}),
        }
        this.location = normalizedLocation
        return session
      } catch (error: unknown) {
        this.error = getApiErrorMessage(error, 'Не удалось открыть смену')
        throw error
      } finally {
        this.isLoading = false
      }
    },

    async closeSession(actualCash: number): Promise<void> {
      if (!this.currentSession) {
        this.error = 'Нет активной сессии для закрытия'
        return
      }

      this.isLoading = true
      this.error = null

      try {
        await apiCloseSession(this.currentSession.id, { actual_cash: actualCash })
        this.currentSession = null
        this.location = null
      } catch (error: unknown) {
        this.error = getApiErrorMessage(error, 'Не удалось закрыть смену')
        throw error
      } finally {
        this.isLoading = false
      }
    },

    clearSession(): void {
      this.currentSession = null
      this.location = null
      this.isLoading = false
      this.error = null
    },
  },
})
