import { ref } from 'vue'
import { defineStore } from 'pinia'
import { fetchCredentials, revokeCredential, type IntegrationCredential } from '@/api/integrations'

export const useIntegrationsStore = defineStore('integrations', () => {
  const credentials = ref<IntegrationCredential[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  let abortController: AbortController | null = null

  async function load(): Promise<void> {
    abortController?.abort()
    abortController = new AbortController()
    isLoading.value = true
    error.value = null
    try {
      credentials.value = await fetchCredentials(abortController.signal)
    } catch (err: any) {
      if (err?.name !== 'CanceledError') error.value = err?.message ?? 'Ошибка загрузки'
    } finally {
      isLoading.value = false
    }
  }

  async function revoke(id: string): Promise<void> {
    await revokeCredential(id)
    const cred = credentials.value.find((c) => c.id === id)
    if (cred) cred.status = 'revoked'
  }

  function cancel(): void {
    abortController?.abort()
  }

  return { credentials, isLoading, error, load, revoke, cancel }
})
