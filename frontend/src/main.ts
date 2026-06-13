import { createApp } from 'vue'
import { VueQueryPlugin } from '@tanstack/vue-query'
import { createPinia } from 'pinia'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/tag/style/css'
import './styles/main.css'
import App from './App.vue'
import router from './router'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(VueQueryPlugin)
app.mount('#app')
