import { createApp } from 'vue'
import { createPinia } from 'pinia'

import App from './App.vue'
import { router } from './router'
import './assets/styles/reset.css'
import './assets/styles/tokens.css'
import './assets/styles/typography.css'
import './assets/styles/animations.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.mount('#app')
