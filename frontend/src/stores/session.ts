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
          this.currentSession = { ...sessions[0] }
          this.location = { ...sessions[0].location }
        } else {
          this.currentSession = null
          this.location = null
        }
      } catch (error: unknown) {
        this.error = error instanceof Error
          ? error.message
          : 'Не удалось загрузить сессию'
      } finally {
        this.isLoading = false
      }
    },

    async openSession(locationId: number, openingCash: number): Promise<PosSession> {
      this.isLoading = true
      this.error = null

      try {
        const session = await apiOpenSession({ location_id: locationId, opening_cash: openingCash })
        this.currentSession = { ...session }
        this.location = { ...session.location }
        return session
      } catch (error: unknown) {
        this.error = error instanceof Error
          ? error.message
          : 'Не удалось открыть сессию'
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
        this.error = error instanceof Error
          ? error.message
          : 'Не удалось закрыть сессию'
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
