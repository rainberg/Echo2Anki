import { createApp } from 'vue'
import { createPinia } from 'pinia'
import naive from 'naive-ui'
import App from './App.vue'
import router from './router'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(naive)
app.mount('#app')

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then((regs) => {
    regs.forEach((reg) => reg.unregister())
  })
}

const style = document.createElement('style')
style.textContent = `
  @media (max-width: 640px) {
    .n-layout-header { font-size: 14px !important; }
    .n-card { font-size: 14px; }
    .n-list-item { padding: 8px 4px !important; }
    .n-modal { margin: 8px; width: calc(100vw - 16px) !important; }
    .n-page-header { padding: 0 !important; }
    body { padding: 0; margin: 0; }
  }
`
document.head.appendChild(style)
