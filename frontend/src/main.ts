/**
 * MicroPOS — Application Entry Point
 */

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'
import { getStoredLocale, i18n, setI18nLocale } from './i18n'

// Styles (order matters)
import './assets/styles/tokens.css'
import './assets/styles/reset.css'
import './assets/styles/tailwind.css'
import './assets/styles/typography.css'
import './assets/styles/animations.css'
import './assets/styles/badges.css'
import './assets/styles/investor-cabinet.css'

function installNumberInputGuard(): void {
  if (typeof window === 'undefined' || typeof document === 'undefined') return

  document.addEventListener('wheel', (event) => {
    const target = event.target
    if (!(target instanceof HTMLInputElement) || target.type !== 'number') return
    if (document.activeElement !== target) return

    event.preventDefault()
    target.blur()
  }, { passive: false, capture: true })
}

installNumberInputGuard()

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(i18n)
app.use(router)

setI18nLocale(getStoredLocale())

app.mount('#app')
