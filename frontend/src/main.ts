/**
 * MicroPOS — Application Entry Point
 */

import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import router from './router'

// Styles (order matters)
import './assets/styles/tokens.css'
import './assets/styles/reset.css'
import './assets/styles/typography.css'
import './assets/styles/animations.css'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

app.mount('#app')
