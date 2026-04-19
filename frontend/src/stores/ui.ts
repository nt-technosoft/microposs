import { ref } from 'vue'
import { defineStore } from 'pinia'

export const useUiStore = defineStore('ui', () => {
  const isBusy = ref(false)
  const toastMessage = ref('')

  function setBusy(value: boolean) {
    isBusy.value = value
  }

  function showToast(message: string) {
    toastMessage.value = message
  }

  function clearToast() {
    toastMessage.value = ''
  }

  return {
    isBusy,
    toastMessage,
    setBusy,
    showToast,
    clearToast,
  }
})
