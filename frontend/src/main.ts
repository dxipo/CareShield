import { createApp } from 'vue'
import { ElButton, ElIcon, ElMenu, ElMenuItem, ElTag } from 'element-plus'
import 'element-plus/dist/index.css'

import App from './App.vue'
import router from './router'
import './style.css'

createApp(App)
  .use(router)
  .use(ElButton)
  .use(ElIcon)
  .use(ElMenu)
  .use(ElMenuItem)
  .use(ElTag)
  .mount('#app')
